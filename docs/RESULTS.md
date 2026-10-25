# Measured results

Everything below was **measured on simulated data** on one Windows development machine (local PostgreSQL via `pgserver`
or SQLite; Python 3.12). Nothing is hard-coded in the app: the UI reads these values from the database/API.
PRD targets are demo goals, not guarantees. Reproduce with the commands shown.

## 0. Simulation calendar

The simulated year runs 23 Jan 2026 - 22 Jan 2027; the system snapshot ("today") is **25 Oct 2026** (day 275), the first day of the
90-day held-out window. Festivals sit on their 2026 dates (Holi 4 Mar, Eid 20 Mar / 27 May, Diwali 8 Nov - the last falls in the test
window). All numbers below were re-measured after this calendar was set (an earlier 2025-based calendar gave very similar results).

## 1. Forecast accuracy (held-out 90-day window, 12 weekly rolling origins)

| profile | series | weekly MAPE mean (min-max) | WAPE | P10-P90 coverage | PRD target MAPE < 20% |
|---|---|---|---|---|---|
| Aditya (60 stores x 60 SKUs) | 1,800 | 30.3% (27.5-33.6) | 19.9% | 76.5% | **not met** |
| Full (400 x 300, sparse assortment) | 14,400 | 28.8% (28.7-28.9, mean over replay seeds) | n/a here | n/a here | **not met** |

Context (`python -m scripts.noise_floor`, Aditya data): an **oracle that knows the true expected demand** scores weekly MAPE 28.1%
(26.3-29.9%) and WAPE 17.4%. The simulated demand is noisy at the store-SKU-week level (gamma-Poisson, ~15 units/week median),
so the PRD's <20% weekly MAPE target cannot be reached on this dataset by any forecaster of the expected value. The LightGBM model
is within ~2 MAPE points of that floor. The generator was not retuned to make the target pass. Interval coverage is below the
nominal 80%, i.e. the P10-P90 band is a little too narrow.
Training mode `fast` (120 trees, origins every 14 days) with `fixed` evaluation (model fitted once on days before the window,
features refreshed at each weekly origin from earlier data only).

## 2. Baseline vs optimised replay (5 seeds, 90 days, Aditya profile)

Optimised policy: LP re-planned **daily**, 7-day horizon, alpha 0.7. Baseline: reorder point, nearest warehouse, proportional
allocation, FIFO. Same demand realisation for both policies per seed (seeds 11-15). `python -m scripts.run_compare`.

| KPI | baseline mean [min-max] | optimised mean [min-max] | relative | PRD target | met? |
|---|---|---|---|---|---|
| Stockout rate | 1.82% [1.79-1.87] | 0.47% [0.42-0.56] | -74.1% | -30% or better | yes |
| Fill rate | 98.27% [98.19-98.36] | 99.54% [99.50-99.57] | +1.3% | >= 95% | yes |
| Transport cost | 337,651 [336,458-338,228] | 357,180 [355,590-358,824] | **+5.8%** | -10% to -15% | **no (worse)** |
| Expiry wastage, stores (PRD definition) | 2.87% [2.83-2.93] | 2.00% [1.98-2.03] | -30.1% | -25% or better | yes |
| Expiry wastage, warehouses (info) | 0.58% [0.55-0.60] | 2.53% [2.51-2.54] | **+335%** | - | worse |
| Expiry wastage, system-wide (info) | 2.88% [2.85-2.92] | 3.96% [3.95-3.97] | **+37%** | - | worse |
| Weekly MAPE | 30.15% [29.77-30.51] | 30.15% [29.77-30.51] | same model | < 20% | **no** |
| Plan time (mean per LP solve) | n/a | 1.11 s [0.96-1.22] | - | < 10 s | yes |
| Constraint violations (all plans, all seeds) | n/a | 0 | - | 0 | yes |
| Explanation coverage | n/a | 100% | - | 100% | yes |

Reading it honestly:
* Service levels improve clearly. Transport cost goes **up** ~6%: when home-warehouse batches fail the shelf-life rule or run
  out, the LP uses the next-cheapest lane, while the baseline always ships from the nearest warehouse regardless of shelf life.
* Store-level expiry falls 30%, but expiry **at warehouses rises sharply** and system-wide expiry is worse. The PRD's shelf-life
  rule (`x = 0` if remaining life after lead time < the store's minimum) keeps short-dated batches from being shipped, so they
  expire in the warehouse; the baseline ships them (some sell, some expire at stores). The PRD has no clearance/transfer step
  (the P2 transfers feature is not implemented), so this loss is not mitigated.
* The headline expiry KPI follows the PRD definition (units expired / units received at stores); both views are shown in the app.
* Results depend on my cost assumptions (freight about 1-3% of unit price) and on the generator; different assumptions change
  the numbers. An earlier configuration with freight costs comparable to cheap-SKU margins and a weekly plan produced a
  *worse* optimised policy (fill 93.5% vs 98.1%); the daily cadence is the PRD's journey J1, and the freight calibration is documented.

### 2b. Same replay at PRD scale (14,400 series, 5 seeds, LP re-planned every 3 days, horizon 7)

| KPI | baseline | optimised | relative | PRD target met? |
|---|---|---|---|---|
| Stockout rate | 1.63% | 0.82% | -49.8% | yes (-30%) |
| Fill rate | 97.90% | 98.95% | +1.1% | yes (>=95%) |
| Transport cost | 3,189,614 | 3,234,037 | **+1.4%** | **no** |
| Expiry wastage, stores | 3.28% | 1.73% | -47.2% | yes (-25%) |
| Expiry wastage, warehouses (info) | 0.79% | 3.48% | +343% | worse |
| Expiry wastage, system-wide (info) | 3.45% | 4.61% | +33.7% | worse |
| Weekly MAPE | 28.79% | 28.79% | same model | **no** |
| Plan time per LP solve (mean) | n/a | 7.98 s [7.26-8.93] | - | yes (<10 s) |
| Violations / explanation coverage | n/a | 0 / 100% | - | yes |

Same pattern as the Aditya profile, with a smaller stockout gain (3-day plan cadence instead of daily) and transport roughly flat.
The cadence differs between 2 and 2b, so they are not directly comparable. Run took ~23 minutes (`run_compare --plan-every 3`).

## 3. Timings (PRD scale: 5 warehouses x 400 stores x 300 SKUs, 14,400 series, 4.53 M sales rows, local PostgreSQL)

`python -m scripts.bench_full`. Two runs on the same machine; the second ran while other jobs (a replay, a build, headless
browser tests) were competing for CPU, so it is a pessimistic bound:

| Operation | quiet machine | under CPU contention | PRD budget |
|---|---|---|---|
| GET /inventory (cold cache) | 151 ms | 204 ms | < 1.5 s |
| GET /forecast (50 rows) | 154 ms | 306 ms | < 1 s |
| POST /plan (14-day horizon, ~13k shipment lines, ~89k LP variables, 5 warehouse-group solves) | 6.1 s | 8.45 s | < 10 s |
| POST /simulate (warehouse closure) | 6.5 s | 9.07 s | < 10 s |
| PATCH override (validate + save) | 100 ms | 172 ms | < 0.5 s |
| PATCH approve (~13k log rows) | 669 ms | **1,017 ms (misses the 1 s budget)** | < 1 s |

Before optimising model construction, rounding and FEFO normalisation, POST /plan took 11.2 s. Rounding at this scale loses ~0.14% of
LP units; no capacity trimming and no FEFO fallback pools were needed. Plans at this scale are solved per warehouse group (a
heuristic, not the global LP optimum). Seeding the full dataset into PostgreSQL takes 3-5 minutes. These timings are for this machine;
Render's free tier has far less CPU/RAM and has **not** been measured.

## 4. What was not verified

* No deployment to Vercel or Render was performed.
* The frontend build, typecheck and lint pass and the pages were loaded in a headless browser against the live API, but
  applying an override and approving a plan through the UI, and the Trade-off, Simulator, Assistant, Overrides pages' interactions
  were not exercised in a browser (their API calls are covered by the backend tests and the smoke script).
* The P2 items: transfers are not implemented. The assistant is intent-matching (RapidFuzz), not an LLM; the PRD's 20-question test is automated and passes (15/15 in scope matched to the database, 5/5 out of scope refused) on the small test dataset.
