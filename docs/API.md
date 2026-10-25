# API contract

JSON over REST. Interactive OpenAPI docs: `GET /docs`. Exact Pydantic models: `backend/app/schemas/api.py`.
Errors: `{"detail": "..."}` or `{"detail": {"message": "...", "violations": [...]}}`; validation errors use FastAPI's
`detail: [...]` list (HTTP 422). `503` means the database has not been seeded yet.

All requests come from the frontend through `NEXT_PUBLIC_API_BASE_URL`. The frontend never talks to the database or solver.

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /health` | liveness + DB check | `{status, database, environment, as_of, forecast_run_id, version}` |
| `GET /meta` | generator settings, cost assumptions, festivals, thresholds, warehouses, categories | shown on the *Data & Assumptions* page |
| `GET /overview` | dashboard aggregates | totals, alert counts, replay KPIs (if a replay is stored), forecast accuracy, latest plan, chart series |
| `GET /inventory` | stock with flags | see below |
| `GET /inventory/batches` | warehouse batches, earliest expiry first | `warehouse_id, product, date, only_risk, page, page_size` |
| `GET /forecast` | P10/P50/P90 for 7/14/30 days + predicted stockout | see below |
| `GET /alerts` | stockout prediction, low stock, rising demand, near expiry, delayed shipment | `region, type, limit` |
| `POST /plan` | run the optimiser and persist a pending plan | see below |
| `PATCH /plan/{id}` | override line quantities and/or approve | see below |
| `GET /plans` | recent plans (summary) | |
| `GET /plans/{id}` | plan with paginated lines | `page, page_size, warehouse_id, store_id, q` |
| `GET /plans/{id}/pick-list` | batch pick list (FEFO) + lane utilisation | `409` until the plan is approved; `warehouse_id` filter |
| `POST /simulate` | re-plan under a scenario and diff against a base plan | see below |
| `GET /compare` | stored replay (baseline vs optimised, 5 seeds) | `{available:false, message}` when no replay was run |
| `GET /overrides` | override/approval log | `plan_id, action=override|approve, page, page_size` |
| `POST /assistant` | intent-matching assistant (RapidFuzz, no LLM) | answers only from stored data and curated PRD text; out-of-scope questions are refused with suggestions |

## GET /inventory

Query: `level` (`store_sku` default, `store`, `sku`, `region`, `distributor`, `warehouse`, `warehouse_sku`), `product`
(SKU id/code or category), `region`, `date` (as-of date for expiry maths, default = system as-of), `search`,
`flag` (`low_stock|excess|expiry_risk`), `warehouse_id`, `store_id`, `page`, `page_size` (<=500), `sort` (`-col` for descending).

Row: `on_hand, reserved, available (= on_hand - reserved), incoming, avg_daily_demand, days_of_cover, nearest_expiry,
qty_expiry_at_risk, low_stock, excess_stock, expiry_risk` (+ `n_series, n_low_stock, ...` on aggregated levels).
`summary` holds totals, flag counts and the thresholds that define the flags:

* store: low stock < 3 days of cover, excess > 30 days; warehouse: low < 7 days, excess > 60 days
* expiry risk: units that FEFO consumption at the average daily rate cannot sell before expiry; expired batches are fully at risk

## GET /forecast

Query: `store_id, sku_id, region, category, horizon (7|14|30), page, page_size, sort (days_of_cover|p50_7|uncertainty|safety_stock; "-" prefix = desc), include_series`.
Item: `horizons[{horizon_days, p10, p50, p90, safety_stock}]`, `available_stock`, `days_of_cover`, `predicted_stockout_date`
(cumulative P50 demand reaches available stock; `null` if beyond 30 days; in-transit stock excluded), `uncertainty_ratio_7d`
((P90-P10)/P50), `safety_stock_explanation`. `series` (only with `store_id+sku_id+include_series`) = weekly history,
held-out actuals (simulated future, for backtest comparison) and forecast bands. `accuracy` = the latest run's rolling-origin
metrics (weekly MAPE mean/min/max, WAPE, P10-P90 coverage, per-week rows, `target_met`, plain-language `note`).

## POST /plan

Body: `{"horizon_days": 14, "alphas": {"Dairy": 0.3}, "default_alpha": 0.7}` (alpha in [0,1], per category).
Response (`PlanOut`): `id, status (pending|overridden|approved), solver_status, solve_seconds, total_cost, cost_breakdown
{transport, shortage, expiry, total}, kpis, validation {valid, n_violations, checked[], violation_counts}, notes
{relaxation, rounding, timing{inputs, solve, validate, persist, wall_clock, target_met}}, lines[]`.
Line: `sku, warehouse, batch_code, batch_expiry, days_to_expiry, store, qty, original_qty, transport_cost, reason, status, override_reason`.
`kpis` are a **static projection over the planning horizon**, not the replay. `baseline_kpis` references the measured replay.
A plan the validator rejects is stored with `solver_status = "INVALID (validator rejected)"` and cannot be approved.

## PATCH /plan/{id}

Body: `{"actor": "priya", "overrides": [{"line_id": 1, "qty": 40, "reason": "store full"}], "approve": false, "validate_only": false}`.
At least one override or `approve: true`. A reason (3-500 chars) is required per override. Overrides are checked against
supply, batch stock, lane/store capacity, shelf-life, candidate lanes and closed warehouses; an infeasible override
returns **422** with `detail.violations` and **nothing is saved**. FEFO deviations are returned as warnings
(`severity: "warning"`). `validate_only: true` runs the checks without saving. `approve: true` sets `approved`, logs one
`approve` entry per line (plus `override` entries for edited lines) and enables the pick list. Approved plans are immutable (409).

## POST /simulate

Body: `{"scenario": {...}, "base_plan_id": 3}` (a base plan is created when omitted). Scenario types and required fields:

| type | fields | modelled as |
|---|---|---|
| `demand_spike` | `pct`, optional `category`, `sku_ids` | multiplies horizon demand and safety stock for the selected series |
| `warehouse_closure` | `warehouse_id`, `days` | the warehouse is removed from the candidate lanes (plan dispatches during the closure) |
| `transport_cost_change` | `pct`, optional `warehouse_id` | scales lane cost per unit |
| `supplier_delay` | `delay_days`, optional `warehouse_id` | adds days to that warehouse's lead time (shelf-life check) and pushes confirmed in-transit ETAs out |

Response: `new_plan` (full `PlanOut`), `comparison {shipment_diff, additional_shortage_units, cost_delta{total,transport,shortage,expiry}, kpi_deltas, kpis_base, kpis_new, changed_lines[]}`.

## GET /compare

`replay` (when stored): per KPI `baseline` and `optimized` `{mean, min, max, values[]}`, `abs_diff`, `rel_diff_pct`, and
`target_status {target, met}` computed from the measured numbers; plus `extra` (violations, explanation coverage, plans,
units, expiry value), `per_seed`, `seeds`, `config`. KPIs: `stockout_rate, fill_rate, transport_cost, expiry_wastage_pct,
weekly_mape, plan_seconds_mean` and informational `expiry_wastage_warehouse_pct, expiry_wastage_total_pct`.
Everything is **simulated** and `labels` says so; targets are goals, not guarantees.

## POST /assistant

Body `{"question": "..."}` (2-300 chars). The question is normalised (contractions, spelling correction against the assistant's own
vocabulary), entities are extracted (SKU code or "Dairy item 4", store, warehouse/WH-n, region, category, plan id, 7/14/30-day horizon) and
the best of 16 intents is chosen by RapidFuzz similarity to example phrasings plus keyword evidence. Unknown ids return `no data`.
Response: `{mode: "intent_matching", label, answer, in_scope, intent, confidence (0-1), sources[{tool,args,rows}], suggestions[]}`.
Intents: greeting, about, snapshot date, counts/overview, stock (store-SKU, store, SKU, category, warehouse, region), forecast, stockout risk,
low stock, excess, near expiry, delayed shipments, plan summary/KPIs, baseline-vs-optimised results, forecast accuracy, glossary (FEFO, alpha,
safety stock, P10/P50/P90, MAPE/WAPE, reserved, days of cover, ...), how-to (generate/override/approve/simulate/trade-off).
It is **not an LLM**: it never generates free text beyond its templates and stored values. `tests/test_assistant.py` implements the PRD's
20-question check (15 in-scope answers compared with the database, 5 out-of-scope refused) plus typo/paraphrase cases.
