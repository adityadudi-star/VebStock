import numpy as np
import pytest

from app.database.session import engine
from app.simulation.replay import ReplayConfig, run_comparison


@pytest.mark.parametrize("scenario", [
    {"type": "demand_spike", "pct": 40},
    {"type": "warehouse_closure", "warehouse_id": 2, "days": 3},
    {"type": "transport_cost_change", "pct": 30},
    {"type": "supplier_delay", "delay_days": 4},
])
def test_simulate_scenarios(client, scenario):
    r = client.post("/simulate", json={"scenario": scenario, "horizon_days": 14})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["new_plan"]["validation"]["valid"]
    assert j["new_plan"]["parent_plan_id"] == j["base_plan_id"]
    c = j["comparison"]
    for k in ("shipment_diff", "cost_delta", "additional_shortage_units", "kpi_deltas", "changed_lines"):
        assert k in c
    assert set(c["cost_delta"]) == {"total", "transport", "shortage", "expiry"}
    if scenario["type"] == "warehouse_closure":
        names = {l["warehouse_id"] for l in client.get(f"/plans/{j['new_plan']['id']}", params={"page_size": 1000}).json()["lines"]}
        assert scenario["warehouse_id"] not in names
    if scenario["type"] == "demand_spike":
        assert j["comparison"]["kpis_new"]["units_shipped"] >= j["comparison"]["kpis_base"]["units_shipped"]


def test_simulate_validation(client):
    assert client.post("/simulate", json={"scenario": {"type": "warehouse_closure"}}).status_code == 422
    assert client.post("/simulate", json={"scenario": {"type": "demand_spike"}}).status_code == 422
    assert client.post("/simulate", json={"scenario": {"type": "meteor"}}).status_code == 422
    assert client.post("/simulate", json={"scenario": {"type": "demand_spike", "pct": 10}, "base_plan_id": 999999}).status_code == 404


@pytest.fixture(scope="module")
def replay(world):
    cfg = ReplayConfig(plan_every_days=7, plan_horizon=14)
    return run_comparison(engine, world, [11, 12], cfg, models=world.models, progress=lambda *_: None)


def test_replay_same_demand_for_both_policies(replay):
    for row in replay["per_seed"]:
        assert row["baseline"]["units_demanded"] == row["optimized"]["units_demanded"]


def test_replay_reports_mean_and_range_and_all_kpis(replay):
    for k in ("stockout_rate", "fill_rate", "transport_cost", "expiry_wastage_pct", "weekly_mape", "plan_seconds_mean"):
        e = replay["kpis"][k]
        for pol in ("baseline", "optimized"):
            assert e[pol]["min"] <= e[pol]["mean"] <= e[pol]["max"]
            assert len(e[pol]["values"]) == 2
        assert "abs_diff" in e and "rel_diff_pct" in e


def test_replay_plans_valid_and_explained(replay):
    assert sum(replay["extra"]["constraint_violations"]["optimized"]) == 0
    assert all(c == 100.0 for c in replay["extra"]["explanation_coverage_pct"]["optimized"] if c is not None)


def test_replay_is_reproducible(world, replay):
    cfg = ReplayConfig(plan_every_days=7, plan_horizon=14)
    again = run_comparison(engine, world, [11], cfg, models=world.models, progress=lambda *_: None)
    a, b = again["per_seed"][0], replay["per_seed"][0]
    for pol in ("baseline", "optimized"):
        for k in ("fill_rate", "stockout_rate", "transport_cost", "expired_units"):
            assert np.isclose(a[pol][k], b[pol][k])


def test_replay_kpi_definitions_sane(replay):
    for row in replay["per_seed"]:
        for pol in ("baseline", "optimized"):
            r = row[pol]
            assert 0 <= r["fill_rate"] <= 100 and 0 <= r["stockout_rate"] <= 100
            assert r["units_sold"] <= r["units_demanded"] + 1e-6
            assert r["expiry_wastage_pct"] >= 0


def test_compare_endpoint_never_invents_numbers(client, db):
    from sqlalchemy import delete
    from app.database import models as m
    db.execute(delete(m.ComparisonRun))
    db.commit()
    j = client.get("/compare").json()
    assert j["available"] is False and j["replay"] is None and "run_compare" in j["message"]
    assert "targets" in j and "labels" in j
