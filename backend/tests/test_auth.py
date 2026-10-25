"""Role-based access: login, token checks, per-role endpoint access, retail store scoping, finance/retail read models."""
import pytest
from sqlalchemy import text

from app import auth
from app.config import get_settings
from app.database import models as m
from app.database.session import SessionLocal

PW = "correct-horse-1"
USERS = [("mfg1", "manufacturer", None), ("fin1", "finance", None), ("wh1", "warehouse", None),
         ("shop1", "retail", 1), ("shop2", "retail", 2)]


@pytest.fixture(scope="module")
def secured(world):
    s = get_settings()
    s.auth_required = True
    with SessionLocal() as db:
        m.AppUser.__table__.create(db.get_bind(), checkfirst=True)
        for u, r, st in USERS:
            db.add(m.AppUser(username=u, password_hash=auth.hash_password(PW), role=r, store_id=st))
        db.commit()
    yield
    s.auth_required = False


def _login(client, user, role=None):
    r = client.post("/auth/login", json=dict(username=user, password=PW, role=role))
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_open_mode_keeps_existing_behaviour(client):
    assert client.get("/overview").status_code == 200


def test_requires_token(client, secured):
    assert client.get("/overview").status_code == 401
    assert client.get("/inventory").status_code == 401
    assert client.get("/overview", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/health").status_code == 200       # liveness stays public


def test_login_failures_are_uniform(client, secured):
    a = client.post("/auth/login", json=dict(username="nobody", password=PW))
    b = client.post("/auth/login", json=dict(username="fin1", password="wrong-password"))
    c = client.post("/auth/login", json=dict(username="fin1", password=PW, role="retail"))   # right password, wrong portal
    assert a.status_code == b.status_code == c.status_code == 401
    assert a.json() == b.json() == c.json()


def test_login_throttle(client, secured):
    for _ in range(5):
        client.post("/auth/login", json=dict(username="thr", password="x"))
    assert client.post("/auth/login", json=dict(username="thr", password="x")).status_code == 429
    auth.clear_failures("thr")


def test_tampered_and_expired_tokens_rejected(client, secured):
    h = _login(client, "fin1")
    body, sig = h["Authorization"][7:].split(".")
    forged = auth._b64(auth._unb64(body).replace(b'"finance"', b'"warehouse"')) + "." + sig
    assert client.get("/overview", headers={"Authorization": "Bearer " + forged}).status_code == 401
    s = get_settings()
    s.auth_token_hours = -1
    try:
        old = _login(client, "fin1")
    finally:
        s.auth_token_hours = 12
    assert client.get("/overview", headers=old).status_code == 401


def test_deactivated_user_loses_access(client, secured):
    h = _login(client, "mfg1")
    assert client.get("/overview", headers=h).status_code == 200
    with SessionLocal() as db:
        db.query(m.AppUser).filter_by(username="mfg1").update(dict(active=0))
        db.commit()
    assert client.get("/overview", headers=h).status_code == 401
    with SessionLocal() as db:
        db.query(m.AppUser).filter_by(username="mfg1").update(dict(active=1))
        db.commit()


@pytest.mark.parametrize("who,path,code", [
    ("mfg1", "/overview", 200), ("mfg1", "/compare", 200), ("mfg1", "/forecast", 200), ("mfg1", "/finance/summary", 403),
    ("mfg1", "/overrides", 403),
    ("fin1", "/finance/summary", 200), ("fin1", "/overrides", 200), ("fin1", "/compare", 200),
    ("wh1", "/inventory/batches", 200), ("wh1", "/finance/summary", 403), ("wh1", "/compare", 403),
    ("shop1", "/overview", 403), ("shop1", "/meta", 403), ("shop1", "/finance/summary", 403), ("shop1", "/plans", 403),
    ("shop1", "/compare", 403), ("shop1", "/inventory/batches", 403), ("shop1", "/overrides", 403),
    ("shop1", "/plans/1", 403), ("shop1", "/retail/deliveries", 200), ("fin1", "/retail/deliveries", 403),
])
def test_role_matrix(client, secured, who, path, code):
    assert client.get(path, headers=_login(client, who)).status_code == code


def test_writes_limited_to_planners(client, secured):
    assert client.post("/plan", json={}, headers=_login(client, "mfg1")).status_code == 403
    assert client.post("/plan", json={}, headers=_login(client, "shop1")).status_code == 403
    assert client.post("/simulate", json={"scenario": {"type": "demand_spike", "pct": 10}},
                       headers=_login(client, "shop1")).status_code == 403
    assert client.patch("/plan/1", json={"approve": True}, headers=_login(client, "mfg1")).status_code == 403


def test_override_log_records_authenticated_actor(client, secured):
    h = _login(client, "wh1")
    plan = client.post("/plan", json={"horizon_days": 7}, headers=h)
    assert plan.status_code == 200
    pid = plan.json()["id"]
    r = client.patch(f"/plan/{pid}", json={"approve": True, "actor": "someone.else"}, headers=h)
    assert r.status_code == 200, r.text
    log = client.get(f"/overrides?plan_id={pid}", headers=h).json()
    assert log["rows"] and {i["actor"] for i in log["rows"]} == {"wh1"}


def test_retail_is_confined_to_own_store(client, secured):
    h = _login(client, "shop1")
    own = client.get("/inventory?level=store", headers=h).json()["rows"]
    other = client.get("/inventory?level=store", headers=_login(client, "shop2")).json()["rows"]
    assert len(own) == 1 and len(other) == 1 and own[0]["name"] != other[0]["name"]
    rows = client.get("/inventory?page_size=500", headers=h).json()["rows"]
    assert rows and {r["store"] for r in rows} == {own[0]["name"]}
    # asking for another store, or any aggregate, is refused rather than silently widened
    assert client.get("/inventory?store_id=2", headers=h).status_code == 403
    for level in ("sku", "warehouse", "region", "distributor", "warehouse_sku"):
        assert client.get(f"/inventory?level={level}", headers=h).status_code == 403
    assert client.get("/forecast?store_id=2", headers=h).status_code == 403
    assert client.get("/retail/deliveries?store_id=2", headers=h).status_code == 403
    fc = client.get("/forecast?page_size=500", headers=h).json()["items"]
    assert fc and {i["store_id"] for i in fc} == {1}


def test_retail_alerts_only_own_store(client, secured):
    a = client.get("/alerts", headers=_login(client, "shop1")).json()
    assert {x["store"] for x in a["alerts"]} <= {"Store 001"}
    assert a["total"] == sum(a["counts"].values())


def test_retail_without_store_is_denied(client, secured):
    with SessionLocal() as db:
        db.add(m.AppUser(username="orphan", password_hash=auth.hash_password(PW), role="retail", store_id=None))
        db.commit()
    assert client.get("/inventory", headers=_login(client, "orphan")).status_code == 403


def test_finance_summary_is_derived_from_existing_data(client, secured, db):
    j = client.get("/finance/summary", headers=_login(client, "fin1")).json()
    expected = db.execute(text(
        "select sum(s.on_hand * k.unit_price) from store_stock s join skus k on k.id = s.sku_id")).scalar()
    assert j["inventory_value"]["by_tier"]["store"]["value"] == pytest.approx(float(expected))
    assert j["inventory_value"]["total"] > 0 and j["sales"]["total"] > 0
    assert any("profit" in x.lower() for x in j["limitations"])      # profit is explicitly not fabricated
    assert "profit" not in {k.lower() for k in j}


def test_retail_deliveries_shape(client, secured):
    j = client.get("/retail/deliveries", headers=_login(client, "shop1")).json()
    assert j["store"]["id"] == 1 and isinstance(j["incoming"], list) and isinstance(j["planned_lines"], list)


def test_me(client, secured):
    j = client.get("/auth/me", headers=_login(client, "shop1")).json()
    assert j == dict(username="shop1", role="retail", store_id=1, store_name="Store 001")
