# Architecture, PRD extraction and modelling decisions

Source PRD: "Distribution Intelligence & Inventory Optimization Engine" (team Longshot), the version titled
*TEAM NAME - LONG SHOT*. Several PRD variants existed on the author's machine; this one was used.

## 1. What the PRD requires (extracted)

* **Data (simulated)**: 12 months of daily sales, 5 warehouses, 400 stores, 300 SKUs, expiry batches, lane costs,
  lead times, promotions, festivals (Diwali/Holi/Eid), supplier delays; generator settings and cost assumptions visible in the app.
* **API**: `GET /inventory`, `GET /forecast`, `POST /plan` (+ `PATCH /plan/{id}`), `POST /simulate`, `GET /compare`, optional `POST /assistant`.
* **Forecast**: LightGBM quantile P10/P50/P90, 7/14/30 days, per SKU-store; safety stock = P90 - P50 over the lead time; rolling-origin
  validation; weekly MAPE (A>0) with WAPE alongside; 9 months train / last 90 days test.
* **Optimiser (7.1)**: LP in PuLP/CBC. Variables `x[s,i,b,j]`, `u[s,j]`, `w[s,j]`. Objective
  `sum (c_ij + delta*r_b) x + alpha*sum pi_s u + (1-alpha)*sum eps_s w`. Constraints: supply (on-hand minus warehouse safety stock),
  batch stock, lane and store capacity, demand + safety stock, expiry, shelf-life (`x = 0` if `e_b - tau_ij < m_s`).
  Scale controls: 3 cheapest lanes per store, per-region solves, continuous relaxation + rounding.
* **Explanations**: one reason per shipment built from LP cost terms and binding constraints (100% coverage).
* **Baseline + replay (9)**: reorder-point baseline (average lead-time demand + fixed margin, nearest warehouse, proportional
  allocation, FIFO) vs the plan, day by day, same held-out demand, 5 seeds, mean and range.
* **KPIs / targets** (goals, not guarantees): stockout -30%+, fill >= 95%, transport -10..-15%, expiry -25%+, weekly MAPE < 20%,
  POST /plan < 10 s, 0 constraint violations, 100% explanation coverage.
* **Journeys**: J1 approve daily plan (P0), J2 alpha slider (P1), J3 disruption simulator (P1), J4 compare view (P1), J5 dispatch pick list (P0).
* **Non-goals**: ERP integration, live ingestion, procurement, multitenant auth.

## 2. System

```
generator (seeded)  --seed-->  PostgreSQL  <--reads/writes--  FastAPI  <--JSON-->  Next.js (Vercel)
                                   ^                              ^
        offline jobs: train_forecast (LightGBM), run_compare (replay)  |  solver runs inside POST /plan
```
The frontend never touches the database, model files or solver. Forecasts are pre-computed into PostgreSQL by an offline job, so the
API process needs neither LightGBM nor model files (important on Render's ephemeral filesystem).

## 3. Decisions and approximations (all deliberate, none hidden)

| Topic | Decision |
|---|---|
| "Today" | The system as-of date is the first day of the 90-day held-out window (2026-10-25). Inventory is a snapshot there; live forecasts use only earlier sales. |
| Scale | `full` = 5 x 400 x 300 with a **sparse assortment** (~12% of SKUs per store -> ~14.4k series, ~4.5 M non-zero sales rows). Dense 120k series x 365 days would be ~44 M rows. |
| Demand model | Seeded expected-demand model (weekday, month seasonality per category, festival uplift, promotions, store size, growth) with gamma-Poisson noise. Replay seeds redraw the **test window** around the same expected demand. |
| Forecast target | Sum of demand over the next h days (h in 7/14/30 as a feature), normalised by recent run-rate; three LightGBM quantile models cover all series and horizons. Festival features are generic "festival days" (Holi and Eid are seen in training, Diwali on 8 Nov 2026 falls in the test window and is not). |
| Evaluation | 12 full weekly rolling origins in the test window; model trained once on days < T0 (`fixed`), or refit per origin (`--eval retrain`, slower). Features at an origin use only earlier sales (tested). |
| Safety stock | 7-day P90-P50 gap rescaled by sqrt(LT/7) to the lane lead time (independent-days assumption). |
| `D_L` (demand over remaining life) | `rate x` stock-weighted mean remaining sellable days of the candidate batches (capped at 90), not a per-batch term. Existing store stock is assumed to share that window. |
| Warehouse "reserved" | `SSW` = 10% of on-hand per warehouse-SKU is held back (not shippable). Store "reserved" = committed stock; available = on-hand - reserved. |
| Rounding | Continuous LP; largest-remainder rounding inside each batch keeps `sum <= batch qty` and supply; lane/store capacity is repaired if rounding exceeds it; batches are then re-assigned earliest-expiry-first per warehouse-SKU pool. Deltas are reported in `notes` (e.g. 543,586 units rounded vs 544,366 LP units at full scale). |
| Decomposition | Above ~60k LP variables the problem is solved per home warehouse, sequentially, passing remaining supply and lane/store capacity forward. This is a heuristic, not the global optimum. |
| FEFO | Modelled by the delta*rank tie-break plus a final per-pool re-assignment; validated independently. |
| Validator | Separate module re-deriving integrality, batch ownership, candidate lanes, closed warehouses, supply, batch stock, lane/store capacity, shelf-life, FEFO and shortage accounting. Run on every plan and on every override (touched pools/lanes/stores). |
| Overrides | Hard constraints must hold or the override is rejected with 422 (nothing saved); FEFO deviations are allowed but returned as warnings. |
| Scenarios | `warehouse_closure` removes the warehouse from the candidate lanes for a same-day dispatch (days is recorded, not time-stepped). `supplier_delay` adds lead-time days and pushes confirmed incoming ETAs out. |
| Plan KPIs | Static projection over the horizon on today's snapshot. They are **not** comparable with a reorder-point baseline (which re-orders daily), so baseline comparison uses only the replay. |
| Replay baseline | ROP = avg 28-day demand x lead time + 2 days of average demand; order-up-to adds 7 days; nearest (cheapest) warehouse; proportional allocation when a warehouse is short; FIFO by received date; no shelf-life rule. Reviewed daily. |
| Replay optimised | LP re-planned every `plan_every_days` (default 1 = a daily plan), horizon 7 days, alpha 0.7, forecasts re-made at each origin from that seed's history. |
| Expiry KPI | Headline (PRD definition): units expired at stores / (units received at stores + opening store stock). Warehouse and system-wide expiry are reported alongside because the shelf-life rule shifts expiry from stores to warehouses. |
| Stockout KPI | Store-SKU-days whose on-hand is zero at the start of the selling day (after receipts) / all store-SKU-days. |
| Cost assumptions | Lane cost = 0.15 + 0.0016 x km per unit (about 1-3% of unit price, a calibration for realism, not tuned to KPIs); `pi_s` = price x category margin; `eps_s` = price x category write-off %. All shown in the app. |
| OR-Tools | Not implemented (documented fallback only; not installed). |
| Assistant (P2) | Intent-matching assistant (RapidFuzz fuzzy matching + entity extraction) over read-only lookups and a curated glossary; no LLM, refuses out-of-scope questions, every number carries its source. The PRD's 20-question test is automated (15 in-scope matched to the DB, 5 refused). An LLM-backed variant (the PRD's Claude tool-calling design) is not implemented. |
| Transfers (P2-2) | Not implemented. |

## 4. Build plan followed

1. Inspect environment/PRD (Node 24, npm 11, Python 3.12, Git 2.55; PRD read via `pypdf` in a throw-away venv).
2. Scaffold two independent projects; backend venv + pinned `requirements.txt`; frontend with npm.
3. Generator, schema, demand model, replay simulator. 4. Forecast + rolling-origin evaluation. 5. Optimiser, FEFO, explanations, validator.
6. API + tests. 7. Frontend screens. 8. End-to-end journey (P0), then P1 (alpha, simulate, alerts, 5-seed compare, override log).
9. Full-scale and PostgreSQL verification, performance profiling and optimisation. 10. Deployment configs and docs.

Library note: PuLP 4.x removed the classic `PULP_CBC_CMD` API used by the PRD's reference approach, so PuLP is pinned to 3.3.2 (bundled CBC).
