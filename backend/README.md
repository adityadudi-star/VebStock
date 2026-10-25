# VebStock backend (FastAPI)

Python API for forecasting, FEFO allocation, plan approval and policy comparison.
Deployed independently to **Render** with **Root Directory = `backend/`**. The frontend never touches the
database, model files or solver; this API is the only door.

## Layout

```
app/
  main.py            FastAPI app, CORS, error logging
  config.py          environment-driven settings
  api/routes.py      thin HTTP layer
  schemas/api.py     Pydantic request/response contracts
  services/          inventory, forecast, plans, simulate, compare, alerts, overview
  forecasting/       LightGBM quantile model (training/evaluation only) + safety-stock rule
  optimization/      PuLP/CBC LP, rounding + FEFO normalisation, explanations, independent validator
  simulation/        seeded generator, demand model, day-by-day replay (baseline vs optimised)
  database/          SQLAlchemy models + session
scripts/             init_db, seed, train_forecast, run_compare, setup_all, smoke_api, try_plan
tests/               pytest suite (isolated temp SQLite dataset)
render.yaml          Render blueprint (web service + Postgres)
```

## Local setup (Windows PowerShell shown; macOS/Linux: `source .venv/bin/activate`)

Prerequisites: Python 3.12 (3.11+ should work), pip. Tested here with Python 3.12.10, Node 24 (frontend), Git 2.55.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt          # runtime + pytest/httpx
copy .env.example .env                       # defaults to a local SQLite file; no edits needed

python -m scripts.setup_all --profile aditya    # schema + seed + LightGBM forecasts   (~10 s)
python -m scripts.setup_all --profile aditya --force --compare   # optional: also the 5-seed replay (minutes)

uvicorn app.main:app --reload --port 8000    # http://localhost:8000/docs
pytest -q
```

Individual steps: `python -m scripts.init_db`, `python -m scripts.seed --profile aditya|full --seed 42`,
`python -m scripts.train_forecast --mode fast|full --eval fixed|retrain`,
`python -m scripts.run_compare --seeds 11 12 13 14 15`.

### Data profiles

| profile | warehouses | stores | SKUs | assortment per store | series | daily sales rows (non-zero) |
|---|---|---|---|---|---|---|
| `aditya` (default, the demo dataset) | 5 | 60 | 60 | 50% | 1,800 | ~0.55 M |
| `full` (PRD scale) | 5 | 400 | 300 | 12% | ~14,400 | ~4-5 M |

The PRD scale (400 stores x 300 SKUs) is generated with a sparse assortment (each store stocks ~12% of the SKUs),
so the store-SKU series count stays at ~14k rather than 120k. This is a documented simplification.
Only non-zero daily sales are stored (zeros are implied). Everything is reproducible from `--seed`.

### The "as-of" date

The simulated year starts 2026-01-23 (so that day 275 is 2026-10-25). The first 275 days (9 months) train the forecaster; the last 90 days are the
held-out test window. The system's "today" is the **first day of the test window (2026-10-25)**: inventory is a
snapshot at that date, live forecasts use only earlier sales, and the held-out days are used only for evaluation
(weekly MAPE/WAPE) and for the replay.

### SQLite vs PostgreSQL

* Local: SQLite file at `backend/data/dev.db` (gitignored). Fine for development and tests.
* Production: PostgreSQL via `DATABASE_URL`. `postgres://` / `postgresql://` URLs are rewritten to the `psycopg`
  (v3) driver automatically. **Never rely on a SQLite file in production**: Render's filesystem is ephemeral.

## Endpoints (details in `docs/API.md`)

`GET /health`, `GET /inventory`, `GET /forecast`, `POST /plan`, `PATCH /plan/{id}`, `GET /plans/{id}`,
`GET /plans/{id}/pick-list`, `POST /simulate`, `GET /compare`, `GET /overrides`, `POST /assistant` (intent matching, no LLM)
plus helpers `/meta`, `/overview`, `/alerts`, `/plans`, `/inventory/batches`. Interactive docs at `/docs`.

## Method summary

* **Forecast**: three stacked LightGBM quantile models (P10/P50/P90) cover all series and the 7/14/30-day horizons
  (horizon is a feature; the target is the h-day demand sum, normalised by the recent run-rate). Features: lagged/rolling
  sales, day-of-week mix, month, festival days (Holi, Eid, Diwali), promo days, price ratio, store cluster, category,
  region. Tests assert that no feature uses sales on/after the forecast origin. **Rolling-origin evaluation**: 12 full
  weekly origins in the held-out window; each week is forecast using only earlier data. Weekly MAPE (A>0) and WAPE are
  reported as measured.
* **Safety stock**: P90 - P50 demand gap over the lead time. The 7-day gap is rescaled by sqrt(LT/7) (assumes
  independent daily demand; an approximation).
* **Optimiser**: continuous LP in PuLP/CBC exactly as PRD 7.1 (transport + FEFO tie-break, alpha-weighted unmet demand
  and expiry). Only series with a coverage deficit get variables; only the 3 cheapest eligible lanes per store are
  candidates; large problems are solved per home-warehouse group with remaining supply/capacity passed forward.
  Quantities are rounded with a supply-preserving largest-remainder rule, capacity is repaired, and batches are
  re-assigned in earliest-expiry-first order. The rounding/repair deltas are reported in each plan's `notes`.
* **Validator** (`optimization/validator.py`): independent re-derivation of supply, batch, lane/store capacity,
  shelf-life, FEFO, candidate-lane, closed-warehouse and accounting checks. Run on every plan and every override.
* **Reasons**: assembled from the model's own numbers (cover days, forecast, batch rank/expiry, lane cost rank, which
  cheaper alternative was saturated, alpha-weighted cost vs lane cost). No language model is involved.
* **OR-Tools fallback**: *not implemented* (not installed). The documented fallbacks are the per-warehouse-group
  decomposition and a solver time limit; the LP stays PuLP/CBC.

## Production notes

* Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health check: `GET /health`.
* CORS: explicit origins from `CORS_ORIGINS` (no wildcard, credentials disabled). Optional `CORS_ORIGIN_REGEX` for previews.
* Logging: unhandled exceptions are logged with stack traces and return a generic 500; slow (>1 s) and 5xx requests are logged.
* The API process does not import LightGBM (forecasts are pre-computed into PostgreSQL); training and replay are offline jobs.
* The replay (`run_compare`) takes minutes and must not run inside a web request: run it as a job, results are stored.
* See `../docs/DEPLOYMENT.md` for Render/Vercel/PostgreSQL steps and free-tier limitations.
