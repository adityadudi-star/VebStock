import time
from datetime import timedelta

from sqlalchemy import text

from app.services.inputs import asof_date


def test_inventory_schema_and_summary(client):
    r = client.get("/inventory", params={"page_size": 5})
    assert r.status_code == 200
    j = r.json()
    assert {"as_of", "level", "total", "summary", "rows", "elapsed_ms"} <= set(j)
    row = j["rows"][0]
    for k in ("on_hand", "reserved", "available", "incoming", "low_stock", "excess_stock", "expiry_risk"):
        assert k in row
    assert row["available"] == max(row["on_hand"] - row["reserved"], 0)


def test_flag_counts_match_independent_sql(client, db):
    j = client.get("/inventory", params={"page_size": 1}).json()
    s = j["summary"]
    low = db.execute(text(
        "select count(*) from store_stock where (on_hand - reserved) < 3.0 * avg_daily_demand and avg_daily_demand > 0")).scalar()
    low0 = db.execute(text("select count(*) from store_stock where avg_daily_demand <= 0 and on_hand - reserved <= 0")).scalar()
    exc = db.execute(text(
        "select count(*) from store_stock where avg_daily_demand > 0 and (on_hand - reserved) > 30.0 * avg_daily_demand")).scalar()
    assert s["low_stock_series"] == low + low0
    assert s["excess_series"] == exc
    assert s["on_hand"] == db.execute(text("select sum(on_hand) from store_stock")).scalar()
    assert s["reserved"] == db.execute(text("select sum(reserved) from store_stock")).scalar()


def test_filters(client):
    all_ = client.get("/inventory", params={"page_size": 1}).json()["total"]
    reg = client.get("/inventory", params={"region": "North", "page_size": 500}).json()
    assert 0 < reg["total"] < all_
    assert all(r["region"] == "North" for r in reg["rows"])
    prod = client.get("/inventory", params={"product": "SKU0001", "page_size": 500}).json()
    assert all(r["sku_code"] == "SKU0001" for r in prod["rows"])
    low = client.get("/inventory", params={"flag": "low_stock", "page_size": 500}).json()
    assert all(r["low_stock"] for r in low["rows"])
    assert client.get("/inventory", params={"level": "bogus"}).status_code == 422
    assert client.get("/inventory", params={"page": 0}).status_code == 422


def test_expiry_risk_grows_with_later_date(client, db):
    base = asof_date(db)
    a = client.get("/inventory", params={"page_size": 1, "date": base.isoformat()}).json()["summary"]["expiry_risk_series"]
    b = client.get("/inventory", params={"page_size": 1, "date": (base + timedelta(days=60)).isoformat()}).json()["summary"]["expiry_risk_series"]
    assert b >= a


def test_batches_have_expiry_flags(client):
    j = client.get("/inventory/batches", params={"page_size": 200}).json()
    days = [r["days_to_expiry"] for r in j["rows"]]
    assert days == sorted(days)                                     # earliest expiry first
    assert all((r["qty_at_risk"] > 0) == r["expiry_risk"] for r in j["rows"])


def test_levels_and_warehouse(client):
    for lvl in ("store", "sku", "region", "distributor", "warehouse", "warehouse_sku"):
        r = client.get("/inventory", params={"level": lvl, "page_size": 3})
        assert r.status_code == 200 and r.json()["rows"], lvl


def test_response_time_targets(client):
    t = time.time()
    client.get("/inventory", params={"page_size": 50})
    assert time.time() - t < 1.5
    t = time.time()
    client.get("/forecast", params={"page_size": 50})
    assert time.time() - t < 1.0
