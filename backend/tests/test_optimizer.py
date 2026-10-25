"""Optimiser constraints are re-checked here with independent code (not only via the validator)."""
from collections import defaultdict

import pandas as pd
import pytest

from app.optimization.model import solve
from app.optimization.validator import validate_plan
from app.services.inputs import build_inputs


@pytest.fixture(scope="module")
def solved(world):
    from app.database.session import SessionLocal
    with SessionLocal() as db:
        inp = build_inputs(db, 14, {"Dairy": 0.3}, default_alpha=0.7)
    return inp, solve(inp)


def test_plan_is_valid_and_nonempty(solved):
    inp, res = solved
    assert len(res.lines) > 0
    v = validate_plan(inp, res.lines, res.series)
    assert v["valid"], v["violations"][:3]
    assert res.solver_status in ("Optimal", "Feasible (time limit)")


def test_integer_positive_quantities(solved):
    _, res = solved
    assert (res.lines["qty"] >= 1).all()
    assert (res.lines["qty"] == res.lines["qty"].astype(int)).all()


def test_supply_and_batch_limits(solved):
    inp, res = solved
    batches = inp.batches.set_index("id")
    shipped_batch = res.lines.groupby("batch_id")["qty"].sum()
    assert (shipped_batch <= batches.loc[shipped_batch.index, "qty"]).all()
    pool_total = inp.batches.groupby(["wh_id", "sku_id"])["qty"].sum()
    shipped_pool = res.lines.groupby(["wh_id", "sku_id"])["qty"].sum()
    for k, q in shipped_pool.items():
        assert q <= pool_total[k] - inp.wh_reserved.get(k, 0)


def test_lane_and_store_capacity(solved):
    inp, res = solved
    vol = inp.skus["unit_volume"]
    l = res.lines.assign(v=res.lines["qty"] * res.lines["sku_id"].map(vol))
    lane_caps = inp.lanes.set_index(["wh_id", "store_id"])["cap"]
    for k, v in l.groupby(["wh_id", "store_id"])["v"].sum().items():
        assert v <= lane_caps[k] + 1e-6
    for st, v in l.groupby("store_id")["v"].sum().items():
        assert v <= inp.store_cap[st] + 1e-6


def test_shelf_life_after_lead_time(solved):
    inp, res = solved
    exp = inp.batches.set_index("id")["exp_days"]
    m_s = inp.skus["min_shelf_life_days"]
    for r in res.lines.itertuples():
        assert exp[r.batch_id] - r.lead >= m_s[r.sku_id]


def test_candidate_lanes_are_three_cheapest(solved):
    inp, res = solved
    assert inp.lanes.groupby("store_id").size().max() <= 3
    cand = set(zip(inp.lanes["wh_id"], inp.lanes["store_id"]))
    assert all((w, s) in cand for w, s in zip(res.lines["wh_id"], res.lines["store_id"]))


def test_fefo_within_each_warehouse_sku_pool(solved):
    inp, res = solved
    exp = inp.batches.set_index("id")["exp_days"]
    qty = inp.batches.set_index("id")["qty"]
    shipped = res.lines.groupby("batch_id")["qty"].sum()
    m_s = inp.skus["min_shelf_life_days"]
    pools = defaultdict(list)
    for bid, r in inp.batches.set_index("id").iterrows():
        pools[(r.wh_id, r.sku_id)].append(bid)
    for r in res.lines.itertuples():
        for b2 in pools[(r.wh_id, r.sku_id)]:
            if exp[b2] < exp[r.batch_id] and exp[b2] - r.lead >= m_s[r.sku_id]:
                assert qty[b2] - shipped.get(b2, 0) < 1, "earlier eligible batch left unused while later batch shipped"


def test_every_shipment_has_a_grounded_reason(solved):
    inp, res = solved
    assert res.lines["reason"].astype(str).str.len().min() > 20
    r = res.lines.iloc[0]
    assert str(int(inp.batches.set_index("id").loc[r.batch_id, "exp_days"])) in r.reason     # actual batch expiry
    assert "lane" in r.reason and "cover" in r.reason or "safety" in r.reason


def test_alpha_moves_outcomes_in_expected_direction(world):
    from app.database.session import SessionLocal
    out = {}
    with SessionLocal() as db:
        for a in (0.05, 0.95):
            inp = build_inputs(db, 14, {}, default_alpha=a)
            res = solve(inp)
            out[a] = (res.series["shortage"].sum(), res.series["expiring"].sum())
    assert out[0.95][0] <= out[0.05][0] + 1e-6     # stockout-averse -> less shortage
    assert out[0.95][1] >= out[0.05][1] - 1e-6     # ... at the price of more expiry exposure


def test_validator_catches_injected_violations(solved):
    inp, res = solved
    lines = res.lines.copy()
    # oversupply
    bad = lines.copy()
    bad.loc[bad.index[0], "qty"] = 10 ** 6
    assert not validate_plan(inp, bad)["valid"]
    # shelf-life: a shipped batch that (in the validator's independent data) is about to expire
    import dataclasses
    b2 = inp.batches.copy()
    b2.loc[b2["id"] == lines.iloc[0]["batch_id"], "exp_days"] = 0
    types = {v["type"] for v in validate_plan(dataclasses.replace(inp, batches=b2), lines)["violations"]}
    assert "shelf_life" in types
    # closed warehouse in the validator's data
    closed = dataclasses.replace(inp, closed_warehouses={int(lines.iloc[0]["wh_id"])})
    assert any(v["type"] == "closed_warehouse" for v in validate_plan(closed, lines)["violations"])
    # non-candidate lane
    row = lines.iloc[0].copy()
    row["store_id"] = 99999
    bad = pd.concat([lines, row.to_frame().T], ignore_index=True)
    assert any(v["type"] == "candidate_lane" for v in validate_plan(inp, bad)["violations"])
    # FEFO: drop an earlier batch's shipment but keep a later one
    assert validate_plan(inp, lines)["valid"]


def test_closed_warehouse_is_never_used(world):
    from app.database.session import SessionLocal
    with SessionLocal() as db:
        inp = build_inputs(db, 14, {}, {"type": "warehouse_closure", "warehouse_id": 1, "days": 3})
    res = solve(inp)
    assert 1 not in set(res.lines["wh_id"])
    assert validate_plan(inp, res.lines, res.series)["valid"]
