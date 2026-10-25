from pathlib import Path

import pytest

from app.config import Settings


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/health", headers={"Origin": "https://vebstock.vercel.app", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://vebstock.vercel.app"
    assert ok.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    dev = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert dev.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_patch_method_allowed(client):
    r = client.options("/plan/1", headers={"Origin": "https://vebstock.vercel.app", "Access-Control-Request-Method": "PATCH"})
    assert r.status_code == 200 and "PATCH" in r.headers.get("access-control-allow-methods", "")


def test_settings_parse_origins_and_db_url():
    s = Settings(cors_origins="https://a.app/, http://localhost:3000", database_url="postgres://u:p@h/db")
    assert s.cors_origin_list == ["https://a.app", "http://localhost:3000"]
    assert s.normalized_db_url.startswith("postgresql+psycopg://")
    assert Settings(database_url="postgresql://u:p@h/db").normalized_db_url.startswith("postgresql+psycopg://")


def test_health_reports_database(client):
    j = client.get("/health").json()
    assert j["status"] == "ok" and j["database"] is True and j["forecast_run_id"]


def test_unknown_route_and_error_shape(client):
    assert client.get("/nope").status_code == 404


FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@pytest.mark.skipif(not (FRONTEND / "lib" / "api.ts").exists(), reason="frontend not present")
def test_frontend_uses_env_api_base_url_and_no_secrets():
    api = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_API_BASE_URL" in api
    env = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_API_BASE_URL" in env
    names = [l.split("=", 1)[0].upper() for l in env.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert names == ["NEXT_PUBLIC_API_BASE_URL"]       # the only public variable; comments may mention "secrets"
    assert not any(w in n for n in names for w in ("SECRET", "PASSWORD", "API_KEY", "TOKEN"))
    # localhost may only appear as a development fallback, never as the only configured value
    for p in FRONTEND.rglob("*.ts*"):
        if "node_modules" in p.parts or ".next" in p.parts or p.name == "api.ts":
            continue
        assert "localhost:8000" not in p.read_text(encoding="utf-8", errors="ignore"), p
