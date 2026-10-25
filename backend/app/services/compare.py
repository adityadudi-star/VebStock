"""GET /compare: stored replay (baseline vs optimised, 5 seeds) + per-plan static projection."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import models as m

TARGETS = {
    "stockout_rate": "down 30% or better vs baseline",
    "fill_rate": ">= 95%",
    "transport_cost": "down 10% to 15% vs baseline",
    "expiry_wastage_pct": "down 25% or better vs baseline",
    "weekly_mape": "< 20%",
    "plan_seconds_mean": "< 10 s per plan",
}
LABELS = {
    "replay": "MEASURED on simulated data: day-by-day replay of both policies on identical held-out demand "
              "(one demand realisation per seed). Mean and min-max across seeds.",
    "targets": "PRD targets are demo goals, not guarantees. Status below is computed from the measured replay, never assumed.",
    "plan_projection": "Static projection over the planning horizon on today's snapshot; not the replay.",
}


def _status(k: str, e: dict) -> dict:
    opt = e["optimized"]["mean"]
    rd = e["rel_diff_pct"]
    if k == "stockout_rate":
        ok = rd is not None and rd <= -30
    elif k == "fill_rate":
        ok = opt >= 95
    elif k == "transport_cost":
        ok = rd is not None and rd <= -10
    elif k == "expiry_wastage_pct":
        ok = rd is not None and rd <= -25
    elif k == "weekly_mape":
        ok = opt < 20
    else:
        ok = opt < 10
    return dict(target=TARGETS[k], met=bool(ok))


def get_compare(db: Session, plan_id: int | None) -> dict:
    row = db.execute(text("select id, created_at, result from comparison_runs order by id desc limit 1")).first()
    replay = None
    msg = None
    if row:
        r = json.loads(row[2]) if isinstance(row[2], str) else row[2]
        for k in TARGETS:
            if k in r["kpis"]:
                r["kpis"][k]["target_status"] = _status(k, r["kpis"][k])
        r["run_id"], r["created_at"] = row[0], str(row[1])
        replay = r
    else:
        msg = "No replay stored yet. Run `python -m scripts.run_compare` in backend/ (takes minutes; it is an offline job)."
    proj = None
    if plan_id is not None:
        p = db.get(m.Plan, plan_id)
        if p is None:
            raise LookupError(f"plan {plan_id} not found")
        k = p.kpis
        proj = dict(plan_id=plan_id, optimized=dict(
            projected_fill_rate_pct=k["projected_fill_rate_pct"], unmet_demand_units=k["unmet_demand_units"],
            expected_expiring_units=k["expected_expiring_units"], expected_expiry_value=k["expected_expiry_value"],
            transport_cost=k["transport_cost"], units_shipped=k["units_shipped"]),
            note="A static one-snapshot projection has no like-for-like baseline (a reorder-point policy re-orders daily), "
                 "so baseline comparison uses the measured replay only.")
    return dict(available=replay is not None, message=msg, replay=replay, plan_projection=proj, targets=TARGETS, labels=LABELS)
