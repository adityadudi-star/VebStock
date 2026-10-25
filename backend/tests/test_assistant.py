"""PRD P2-1 acceptance: 20 scripted questions - 15 in-scope answers must match the database, 5 out-of-scope must be refused.
Plus paraphrase / typo robustness and the grounding guarantees."""
import re

import pytest
from sqlalchemy import text

from app.services import assistant as A

REFUSAL = "I can only answer from this system's data."


def ask(client, q):
    r = client.post("/assistant", json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def facts(world):
    from app.database.session import SessionLocal
    with SessionLocal() as db:
        row = db.execute(text(
            "select s.store_id, k.code, s.on_hand, s.reserved, s.incoming from store_stock s join skus k on k.id = s.sku_id "
            "where s.on_hand > 5 order by s.store_id, s.sku_id limit 1")).first()
        store = row[0]
        f = dict(store=store, sku=row[1], on_hand=row[2], reserved=row[3], incoming=row[4],
                 sku_id=db.execute(text("select id from skus where code = :c"), {"c": row[1]}).scalar())
        f["store_on_hand"] = db.execute(text("select sum(on_hand) from store_stock where store_id = :s"), {"s": store}).scalar()
        f["n_stores"] = db.execute(text("select count(*) from stores")).scalar()
        f["n_skus"] = db.execute(text("select count(*) from skus")).scalar()
        f["n_wh"] = db.execute(text("select count(*) from warehouses")).scalar()
        f["p50_14"] = db.execute(text("select p50 from forecasts where store_id=:s and sku_id=:k and horizon=14 order by run_id desc limit 1"),
                                 {"s": store, "k": f["sku_id"]}).scalar()
        import json
        m = db.execute(text("select metrics from forecast_runs order by id desc limit 1")).scalar()
        f["mape"] = (json.loads(m) if isinstance(m, str) else m)["mape_mean"]
        f["asof"] = db.execute(text("select value from meta where key='as_of'")).scalar()
        f["asof"] = (json.loads(f["asof"]) if isinstance(f["asof"], str) else f["asof"])["date"]
    return f


# ----------------------------------------------------------------- 15 in-scope, answers must match the DB
def test_in_scope_01_store_sku_stock(client, facts):
    a = ask(client, f"How much stock of {facts['sku']} is at Store {facts['store']:03d}?")
    assert a["in_scope"] and a["intent"] == "stock"
    assert f"{facts['on_hand']} on hand" in a["answer"] and f"{facts['reserved']} held back" in a["answer"]
    assert a["sources"] and a["sources"][0]["rows"] == 1


def test_in_scope_02_store_total(client, facts):
    a = ask(client, f"what is the inventory of store {facts['store']}")
    assert f"{facts['store_on_hand']:,}" in a["answer"]


def test_in_scope_03_store_count(client, facts):
    a = ask(client, "How many stores do we have?")
    assert f"{facts['n_stores']} stores" in a["answer"] and f"{facts['n_skus']} SKUs" in a["answer"]


def test_in_scope_04_warehouse_count(client, facts):
    assert f"{facts['n_wh']} warehouses" in ask(client, "give me an overview of the network")["answer"]


def test_in_scope_05_forecast(client, facts):
    a = ask(client, f"what is the forecast for {facts['sku']} at store {facts['store']} for 14 days")
    assert a["intent"] == "forecast" and "next 14 days" in a["answer"]
    assert f"expected {facts['p50_14']:.0f}" in a["answer"]


def test_in_scope_06_accuracy(client, facts):
    a = ask(client, "what is the forecast accuracy")
    assert f"{facts['mape']:.1f}%" in a["answer"] and "target" in a["answer"]


def test_in_scope_07_fefo(client):
    assert "first-expired" in ask(client, "What is FEFO?")["answer"]


def test_in_scope_08_alpha(client):
    assert "trade-off" in ask(client, "what does alpha mean")["answer"]


def test_in_scope_09_approve_howto(client):
    assert "Approve plan" in ask(client, "How do I approve a plan?")["answer"]


def test_in_scope_10_stockout_region(client):
    a = ask(client, "Which stores will run out of stock in the North region?")
    assert a["intent"] == "stockout_risk" and (a["answer"] == "no data" or "North" in a["answer"])


def test_in_scope_11_latest_plan(client):
    pid = client.post("/plan", json={"horizon_days": 7}).json()["id"]
    a = ask(client, "show me the latest plan")
    assert f"Plan {pid}" in a["answer"] and a["intent"] == "plan"
    assert f"Plan {pid}" in ask(client, f"what is the total cost of plan {pid}")["answer"]


def test_in_scope_12_compare_without_replay_says_no_data(client, db):
    from sqlalchemy import delete
    from app.database import models as m
    db.execute(delete(m.ComparisonRun))
    db.commit()
    a = ask(client, "how does the optimized plan compare with the baseline")
    assert a["answer"].startswith("no data") and a["intent"] == "compare"      # never invents numbers


def test_in_scope_13_snapshot_date(client, facts):
    from datetime import date
    d = date.fromisoformat(facts["asof"])
    assert d.strftime("%d %b %Y") in ask(client, "what is the snapshot date")["answer"]


def test_in_scope_14_low_stock_count(client):
    a = ask(client, "which items are low on stock")
    n = client.get("/alerts", params={"type": "low_stock", "limit": 1}).json()["counts"]["low_stock"]
    assert a["intent"] == "low_stock" and (str(n) in a["answer"] or a["answer"] == "no data")


def test_in_scope_15_greeting(client):
    a = ask(client, "hello")
    assert a["in_scope"] and a["suggestions"]


# ----------------------------------------------------------------- 5 out-of-scope must be refused
@pytest.mark.parametrize("q", ["who won the world cup", "what's the weather today in Mumbai", "write me a poem about the sea",
                               "what is the capital of France", "tell me a joke"])
def test_out_of_scope_refused(client, q):
    a = ask(client, q)
    assert a["in_scope"] is False and a["answer"].startswith(REFUSAL)
    assert a["sources"] == [] and a["suggestions"]


# ----------------------------------------------------------------- understanding: typos and paraphrases
@pytest.mark.parametrize("q,intent", [
    ("wat is fefo", "glossary"), ("explain safety stock to me", "glossary"), ("whats p90", "glossary"),
    ("how can i create a plan", "howto"), ("how to run a what-if scenario", "howto"),
    ("stock levels for sku 1 at store 2", "stock"), ("forcast for sku1 at store 2", "forecast"),
    ("anything about to expire?", "expiry"), ("which shipments are late", "delayed"),
    ("is the optimizer better than the baseline", "compare"), ("how accurate are the predictions", "accuracy"),
])
def test_paraphrases_and_typos_are_understood(client, q, intent):
    a = ask(client, q)
    assert a["in_scope"] and a["intent"] == intent, (q, a["intent"], a["confidence"])


def test_entities_are_resolved_not_guessed(client):
    a = ask(client, "stock of sku 99999 at store 99999")
    assert a["answer"] == "no data"                  # unknown ids never produce invented numbers


def test_response_schema(client):
    a = ask(client, "what is fefo")
    assert set(a) >= {"mode", "label", "answer", "in_scope", "intent", "confidence", "sources", "suggestions"}
    assert a["mode"] == "intent_matching" and "no LLM" in a["label"]
    assert 0.0 <= a["confidence"] <= 1.0
    assert client.post("/assistant", json={"question": ""}).status_code == 422


def test_numbers_in_answers_have_sources(client, facts):
    a = ask(client, f"stock of {facts['sku']} at store {facts['store']}")
    assert re.search(r"\d", a["answer"]) and a["sources"]
