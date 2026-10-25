"""FastAPI entry point. Run: uvicorn app.main:app --host 0.0.0.0 --port $PORT"""
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.database import models
from app.database.session import engine

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vebstock")

app = FastAPI(title="VebStock API", version=__version__,
              description="The right stock. The right place. The right time.")

# Explicit origins only (no wildcard). Credentials are not used, so cookies are never sent cross-site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def timing(request: Request, call_next):
    t = time.time()
    response = await call_next(request)
    ms = (time.time() - t) * 1000
    response.headers["X-Process-Time-Ms"] = f"{ms:.1f}"
    if ms > 1000 or response.status_code >= 500:
        log.warning("%s %s -> %s in %.0f ms", request.method, request.url.path, response.status_code, ms)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# Additive: the login table is created on demand so existing databases need no manual migration.
try:
    models.AppUser.__table__.create(engine, checkfirst=True)
except Exception:  # database unreachable at import time: /health reports it
    log.warning("could not ensure app_users table exists", exc_info=True)

app.include_router(router)
