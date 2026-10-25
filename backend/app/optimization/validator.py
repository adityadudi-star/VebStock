"""Independent plan validator. Re-derives every PRD 7.1 constraint from raw inputs and the final
integer shipment lines; it shares no code with the LP builder.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from app.optimization.types import PlanInputs

CHECKS = ["integrality", "known_batch", "candidate_lane", "closed_warehouse", "supply", "batch_stock",
          "lane_capacity", "store_capacity", "shelf_life", "fefo", "coverage_accounting"]


def validate_plan(inp: PlanInputs, lines: pd.DataFrame, series: pd.DataFrame | None = None, tol: float = 1e-6) -> dict:
    v: list[dict] = []

    def bad(kind, msg, **kw):
        v.append(dict(type=kind, message=msg, **kw))

    sku = inp.skus
    batches = {int(r.id): (int(r.wh_id), int(r.sku_id), int(r.qty), int(r.exp_days)) for r in inp.batches.itertuples()}
    lane = {(int(r.wh_id), int(r.store_id)): (float(r.cost), int(r.lead) + int(inp.extra_lead.get(int(r.wh_id), 0)), float(r.cap))
            for r in inp.lanes.itertuples()}
    by_pool = defaultdict(list)
    for bid, (wh, s, q, e) in batches.items():
        by_pool[(wh, s)].append((e, bid, q))
    for k in by_pool:
        by_pool[k].sort()

    pool_ship = defaultdict(int)
    batch_ship = defaultdict(int)
    lane_vol = defaultdict(float)
    store_vol = defaultdict(float)
    for r in lines.itertuples():
        wh, st, bid, s, q = int(r.wh_id), int(r.store_id), int(r.batch_id), int(r.sku_id), r.qty
        if q != int(q) or q < 1:
            bad("integrality", f"line qty {q} is not a positive integer", batch_id=bid, store_id=st)
            continue
        q = int(q)
        if bid not in batches or batches[bid][0] != wh or batches[bid][1] != s:
            bad("known_batch", f"batch {bid} does not belong to warehouse {wh} / sku {s}", batch_id=bid)
            continue
        if (wh, st) not in lane:
            bad("candidate_lane", f"lane {wh}->{st} is not a candidate lane", store_id=st)
            continue
        if wh in inp.closed_warehouses:
            bad("closed_warehouse", f"warehouse {wh} is closed in this scenario", store_id=st)
        pool_ship[(wh, s)] += q
        batch_ship[bid] += q
        vol = float(sku.at[s, "unit_volume"]) * q
        lane_vol[(wh, st)] += vol
        store_vol[st] += vol
        _c, lead, _cap = lane[(wh, st)]
        if batches[bid][3] - lead < int(sku.at[s, "min_shelf_life_days"]):
            bad("shelf_life", f"batch {bid} has {batches[bid][3]} d left, lead {lead} d, minimum "
                              f"{int(sku.at[s, 'min_shelf_life_days'])} d", batch_id=bid, store_id=st)

    for (wh, s), q in pool_ship.items():
        total = sum(x[2] for x in by_pool.get((wh, s), []))
        cap = max(0, total - int(inp.wh_reserved.get((wh, s), 0)))
        if q > cap:
            bad("supply", f"warehouse {wh} sku {s}: shipping {q} > available {cap} after reserved stock", warehouse_id=wh, sku_id=s)
    for bid, q in batch_ship.items():
        if q > batches[bid][2]:
            bad("batch_stock", f"batch {bid}: shipping {q} > batch qty {batches[bid][2]}", batch_id=bid)
    for key, vol in lane_vol.items():
        if vol > lane[key][2] + 1e-6:
            bad("lane_capacity", f"lane {key[0]}->{key[1]} load {vol:.1f} > capacity {lane[key][2]:.1f}")
    for st, vol in store_vol.items():
        if vol > inp.store_cap.get(st, 1e18) + 1e-6:
            bad("store_capacity", f"store {st} load {vol:.1f} > capacity {inp.store_cap.get(st):.1f}", store_id=st)

    # FEFO: if a batch is shipped to a lane, every earlier eligible batch must have nothing left over
    for r in lines.itertuples():
        wh, st, bid, s = int(r.wh_id), int(r.store_id), int(r.batch_id), int(r.sku_id)
        if bid not in batches or (wh, st) not in lane:
            continue
        e_b = batches[bid][3]
        lead = lane[(wh, st)][1]
        m_s = int(sku.at[s, "min_shelf_life_days"])
        for e, b2, q2 in by_pool[(wh, s)]:
            if e >= e_b:
                break
            if e - lead >= m_s and q2 - batch_ship.get(b2, 0) >= 1:
                bad("fefo", f"batch {bid} (exp {e_b} d) shipped to store {st} while earlier eligible batch {b2} "
                            f"(exp {e} d) still has {q2 - batch_ship.get(b2, 0)} units", batch_id=bid, store_id=st)
                break

    if series is not None and len(series):
        ship = series["shipped"].to_numpy()
        recomputed = (inp.DH + inp.SS - inp.I - inp.R - ship).clip(min=0)
        diff = abs(recomputed - series["shortage"].to_numpy())
        if (diff > 1e-4).any():
            bad("coverage_accounting", f"{int((diff > 1e-4).sum())} series report a shortage that does not match demand+SS accounting")
        line_ship = lines.groupby("series_idx")["qty"].sum() if len(lines) else pd.Series(dtype=float)
        mism = (line_ship.reindex(range(inp.n)).fillna(0).to_numpy() != ship).sum()
        if mism:
            bad("coverage_accounting", f"{int(mism)} series shipped totals differ from line totals")
    counts = defaultdict(int)
    for x in v:
        counts[x["type"]] += 1
    return dict(valid=len(v) == 0, n_violations=len(v), checked=CHECKS, violation_counts=dict(counts),
                violations=v[:50])
