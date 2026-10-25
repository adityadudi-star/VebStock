# Deployment guide

> Nothing here has been deployed or verified on Vercel or Render by the author of this repository. The steps are
> written from the configuration files in the repo and the platforms' documented behaviour; verify each step in your
> own accounts. Free-tier terms change: re-check Render's and Vercel's current pricing/limits pages.

Two independent deployables from one Git repository:

| part | host | root directory | config |
|---|---|---|---|
| `frontend/` Next.js | Vercel | `frontend` | env var `NEXT_PUBLIC_API_BASE_URL` |
| `backend/` FastAPI | Render web service | `backend` | `backend/render.yaml`, env vars below |
| PostgreSQL | Render Postgres (or any PostgreSQL reachable by the service) | - | `DATABASE_URL` |

Deploy order: **database -> backend -> seed -> frontend -> set backend CORS to the frontend URL**.

## 1. Database (PostgreSQL)

Option A (Blueprint): `backend/render.yaml` declares a `vebstock-db` Postgres instance and wires its connection string
into the web service as `DATABASE_URL`. In Render: *New -> Blueprint*, pick the repo, confirm.

Option B (manual): Render -> *New -> PostgreSQL* (name `vebstock-db`, database `vebstock`). Copy the **Internal Database URL**
(used by the web service in the same region) and the **External Database URL** (used from your laptop for seeding).

No credentials are committed. The app accepts `postgres://`, `postgresql://` or `postgresql+psycopg://` URLs.

## 2. Backend on Render

1. Render -> *New -> Web Service* -> connect the repo.
2. **Root Directory: `backend`**. Runtime: Python 3. Build command `pip install -r requirements.txt`.
   Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (binds 0.0.0.0 and the platform-assigned port).
3. Health check path: `/health`.
4. Environment variables (dashboard -> Environment):
   * `DATABASE_URL` - Internal Database URL of the Postgres instance
   * `CORS_ORIGINS` - the exact Vercel origin(s), comma separated, no trailing slash, e.g. `https://vebstock.vercel.app`
     (add `http://localhost:3000` only if you want local frontends to call production)
   * `CORS_ORIGIN_REGEX` (optional) - e.g. `https://vebstock-.*\.vercel\.app` to allow Vercel preview URLs
   * `ENVIRONMENT=production`, `PYTHON_VERSION=3.12.10`, `LOG_LEVEL=INFO`
5. Do **not** put secrets in `render.yaml`; it only references the database and leaves `CORS_ORIGINS` for the dashboard.

### Create schema and seed data (explicit, one-time)

The web service never seeds on startup. Run the setup job once against the production database, either from the
Render *Shell* tab of the service, or from your machine with the **External** URL:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST.render.com/vebstock"     # external URL
python -m scripts.setup_all --profile aditya                  # schema + seed + forecasts; skips if already seeded
python -m scripts.setup_all --profile aditya --force --compare   # reseed (WIPES plans/overrides) and run the replay
```

The replay (`--compare`, 5 seeds) takes minutes; run it from your machine rather than inside a web request.
Schema creation is `Base.metadata.create_all` (idempotent); there are no destructive migrations. If you later change
models, add a migration tool (e.g. Alembic) before altering a populated production database.

Check: `https://<service>.onrender.com/health` returns `{"status":"ok","database":true,"as_of":"2026-10-25",...}` and
`/docs` lists the endpoints.

### Render free-tier limitations (verify current terms)

* Free web services spin down after a period of inactivity; the next request can take on the order of a minute
  to wake the service. Ping `/health` before a demo. The frontend shows a "backend waking up / unreachable" state with retry.
* Free instances have small RAM (512 MB at the time of writing). The `dev` profile fits comfortably (the API
  process does not import LightGBM). The `full` profile data is much larger: keep it for a paid instance and test
  memory and the 10-second plan budget there.
* The instance filesystem is **ephemeral**: it is wiped on redeploy/restart. Do not store SQLite files, model files
  or uploads on it. All state lives in PostgreSQL; forecasts are pre-computed into it.
* Free Postgres instances are time-limited and size-limited at the time of writing (expiry and storage caps apply);
  export data or upgrade if you need persistence beyond that.

## 3. Frontend on Vercel

1. Vercel -> *Add New -> Project* -> import the repo.
2. **Root Directory: `frontend`**. Framework preset: Next.js (build `next build`, output handled automatically).
3. Environment variable (Production and Preview): `NEXT_PUBLIC_API_BASE_URL = https://<your-service>.onrender.com`
   (no trailing slash). Everything prefixed `NEXT_PUBLIC_` is visible to browsers: never put secrets there.
4. Deploy. Changing the variable requires a **redeploy** (it is inlined at build time).
5. Copy the production URL and set it in the backend's `CORS_ORIGINS`, then redeploy/restart the backend.

If `NEXT_PUBLIC_API_BASE_URL` is missing in a production build the app shows a configuration error instead of
silently calling localhost.

## 4. Verification checklist (do these after deploying; nothing is claimed until you do)

- [ ] `GET /health` on Render returns ok and the seeded `as_of`.
- [ ] Browser devtools on the Vercel site: calls go to the Render URL, no CORS errors.
- [ ] Inventory loads; Forecast shows the honest MAPE/WAPE panel; Generate plan returns a plan with 0 violations.
- [ ] Override rejects an infeasible quantity (422) and accepts a feasible one with a reason; Approve then pick list works.
- [ ] Compare shows the stored replay (or an explicit "not run yet" state if you skipped `--compare`).

## 5. Local development against production database (optional)

Use the External URL in `backend/.env` (`DATABASE_URL=...`). Be careful: `seed --force` and `setup_all --force` wipe tables.
