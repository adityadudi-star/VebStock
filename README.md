# VebStock

**The right stock. The right place. The right time.**

A distribution-intelligence and inventory-optimisation web app for an FMCG distributor, built from the PRD
*Distribution Intelligence & Inventory Optimization Engine* (team Longshot). For every SKU and store it forecasts demand
(LightGBM P10/P50/P90), sets uncertainty-driven safety stock, allocates warehouse batches with a linear program
(PuLP/CBC, earliest-expiry-first), explains every shipment from the solver's own inputs, lets a planner override and
approve, and compares the plan with a reorder-point baseline in a day-by-day replay.

> **All data is simulated.** Every KPI in the app is either *measured on simulated data* (the replay) or an explicit
> PRD *target*, and the two are always shown separately. Targets are goals, not guarantees. See `docs/RESULTS.md` for
> the measured numbers, including the ones that miss their targets.

## Repository

```
frontend/   Next.js + TypeScript + Tailwind + Recharts      -> deploy to Vercel   (root directory: frontend)
backend/    FastAPI + LightGBM + PuLP/CBC + SQLAlchemy      -> deploy to Render   (root directory: backend)
docs/       API contract, architecture/decisions, results, deployment
```
The two projects are independent: they share nothing but the HTTP API. The frontend never touches the database, model files
or solver.

## Run locally (two terminals)

Prerequisites: Node 20+ (tested 24), Python 3.11+ (tested 3.12), Git. No database software is needed locally (SQLite fallback).

```powershell
# 1) backend  (http://localhost:8000, docs at /docs)
cd backend
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python -m scripts.setup_all --profile aditya          # schema + simulated data + LightGBM forecasts (~10-30 s)
python -m scripts.run_compare                      # optional, minutes: 5-seed baseline-vs-optimised replay
uvicorn app.main:app --reload --port 8000

# 2) frontend  (http://localhost:3000)
cd frontend
npm install
copy .env.example .env.local                       # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```
If port 8000 is taken, run the API on another port and set `NEXT_PUBLIC_API_BASE_URL` accordingly.

Tests: `cd backend ; pytest -q` (isolated temp database; covers schemas, forecasts, inventory flags, optimiser constraints,
FEFO, explanations, overrides/approval, replay, simulation, CORS). Frontend: `npm run typecheck ; npm run lint ; npm run build`.

## Production

Vercel (frontend) + Render (backend + PostgreSQL). Step-by-step instructions, environment variables, database seeding and
free-tier limitations: **`docs/DEPLOYMENT.md`**. Nothing in this repository has been deployed by its author; the
checklist at the end of that document is how you verify your own deployment.

## Documents

* `docs/ARCHITECTURE.md` - PRD requirements extracted, system design, every modelling decision/approximation
* `docs/API.md` - endpoint contract
* `docs/RESULTS.md` - measured accuracy, replay KPIs and timings (and what was *not* achieved)
* `docs/DEPLOYMENT.md` - Vercel / Render / PostgreSQL
* `backend/README.md`, `frontend/README.md` - per-project setup
