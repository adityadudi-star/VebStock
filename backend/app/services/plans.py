"""Plan lifecycle: generate (POST /plan), read, override + approve (PATCH /plan/{id}), pick list."""
from __future__ import annotations

import time
from collections import OrderedDict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.database import models as m
from app.optimization.model import _series_table, _costs, series_context, solve
from app.optimization.types import PlanInputs
from app.optimization.validator import validate_plan
from app.services.inputs import asof_date, build_inputs

_INPUT_CACHE: "OrderedDict[int, tuple]" = OrderedDict()


class PlanError(Exception):
    def __init__(self, status: int, message: str, extra: dict | None = None):
        self.status, self.message, self.extra = status, message, extra or {}
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ KPIs
def kpis_from(inp: PlanInputs, series: pd.DataFrame, lines: pd.DataFrame, cost: dict, violations: int,
              wall_seconds: float) -> dict:
    ship = series["shipped"].to_numpy()
    unmet = np.clip(inp.DH - (inp.I + inp.R + ship), 0, None)
    eps = inp.skus["writeoff_cost"].reindex(inp.sku_id).to_numpy()
    expiring = series["expiring"].to_numpy()
    n = len(lines)
    cov = 100.0 * float((lines["reason"].astype(str).str.len() > 0).sum()) / n if n else 100.0
    return dict(
        projected_fill_rate_pct=round(100.0 * (1 - unmet.sum() / max(inp.DH.sum(), 1e-9)), 2),
        unmet_demand_units=round(float(unmet.sum()), 1),
        shortage_vs_target_units=round(float(series["shortage"].sum()), 1),
        expected_expiring_units=round(float(expiring.sum()), 1),
        expected_expiry_value=round(float((expiring * eps).sum()), 2),
        transport_cost=cost["transport"], shortage_cost=cost["shortage"], expiry_cost=cost["expiry"],
        shipments=int(n), units_shipped=int(lines["qty"].sum()) if n else 0,
        stores_served=int(lines["store_id"].nunique()) if n else 0,
        explanation_coverage_pct=round(cov, 1), constraint_violations=int(violations),
        solve_seconds=round(wall_seconds, 3))


# ------------------------------------------------------------------ generate
def create_plan(db: Session, *, horizon: int, alphas: dict, default_alpha: float, scenario: dict | None = None,
                parent_id: int | None = None) -> int:
    t_all = time.time()
    inp = build_inputs(db, horizon, alphas, scenario, default_alpha)
    t_in = time.time() - t_all
    res = solve(inp)
    t_v = time.time()
    val = validate_plan(inp, res.lines, res.series)
    t_val = time.time() - t_v
    DL, alpha = series_context_from_series(res.series)
    wall_pre = time.time() - t_all
    kp = kpis_from(inp, res.series, res.lines, res.cost, val["n_violations"], wall_pre)
    status = res.solver_status if val["valid"] else "INVALID (validator rejected)"
    t_p = time.time()
    plan = m.Plan(status="pending", created_at=_now(), horizon_days=horizon,
                  alphas=dict(by_category=alphas, default=default_alpha), scenario=scenario, parent_plan_id=parent_id,
                  solver_status=status, solve_seconds=res.solve_seconds, total_cost=res.cost["total"], kpis=kp,
                  validation=val, notes={})
    db.add(plan)
    db.flush()
    rows = []
    if len(res.lines):
        for r in res.lines.itertuples():
            rows.append(dict(plan_id=plan.id, sku_id=int(r.sku_id), warehouse_id=int(r.wh_id), batch_id=int(r.batch_id),
                             store_id=int(r.store_id), qty=int(r.qty), original_qty=int(r.qty),
                             transport_cost=round(float(r.qty * r.cost_per_unit), 2), reason=r.reason, status="planned"))
        for i in range(0, len(rows), 5000):
            db.execute(insert(m.PlanLine), rows[i:i + 5000])
    wall = time.time() - t_all
    kp["solve_seconds"] = round(wall, 3)
    plan.kpis = kp
    plan.notes = dict(res.notes, cost_breakdown=res.cost,
                      timing=dict(inputs_seconds=round(t_in, 3), solve_seconds=res.solve_seconds,
                                  validate_seconds=round(t_val, 3), persist_seconds=round(time.time() - t_p, 3),
                                  wall_clock_seconds=round(wall, 3), target_seconds=10.0,
                                  target_met=bool(wall < 10.0)))
    db.commit()
    _cache_put(plan.id, inp, res.series["DL"].to_numpy(), res.series["alpha"].to_numpy())
    return plan.id


def series_context_from_series(series: pd.DataFrame):
    return series["DL"].to_numpy(), series["alpha"].to_numpy()


def _cache_put(pid: int, inp: PlanInputs, DL, alpha) -> None:
    _INPUT_CACHE[pid] = (inp, DL, alpha)
    while len(_INPUT_CACHE) > 6:
        _INPUT_CACHE.popitem(last=False)


def _get_ctx(db: Session, plan: m.Plan):
    if plan.id in _INPUT_CACHE:
        return _INPUT_CACHE[plan.id]
    a = plan.alphas
    inp = build_inputs(db, plan.horizon_days, a.get("by_category", {}), plan.scenario, a.get("default", 0.7))
    DL, alpha = series_context(inp)
    _cache_put(plan.id, inp, DL, alpha)
    return inp, DL, alpha


# ------------------------------------------------------------------ read
LINE_SQL = (
    "select l.id, l.sku_id, k.code as sku_code, k.name as sku_name, k.category, l.warehouse_id, w.name as warehouse, "
    "l.batch_id, b.batch_code, b.expiry_date as batch_expiry, l.store_id, s.name as store, l.qty, l.original_qty, "
    "l.transport_cost, l.reason, l.status, l.override_reason "
    "from plan_lines l join skus k on k.id = l.sku_id join warehouses w on w.id = l.warehouse_id "
    "join warehouse_batches b on b.id = l.batch_id join stores s on s.id = l.store_id where l.plan_id = :p")


def _line_rows(db: Session, plan_id: int, asof, where: str = "", params: dict | None = None, limit=None, offset=0):
    q = LINE_SQL + where + " order by b.expiry_date, l.id"
    p = {"p": plan_id, **(params or {})}
    if limit is not None:
        q += " limit :lim offset :off"
        p.update(lim=limit, off=offset)
    out = []
    for r in db.execute(text(q), p).mappings():
        d = dict(r)
        be = pd.Timestamp(d["batch_expiry"]).date()
        d["batch_expiry"] = be
        d["days_to_expiry"] = (be - asof).days
        out.append(d)
    return out


def get_plan(db: Session, plan_id: int, *, page=1, page_size=100, warehouse_id=None, store_id=None, q=None) -> dict:
    plan = db.get(m.Plan, plan_id)
    if plan is None:
        raise PlanError(404, f"plan {plan_id} not found")
    asof = asof_date(db)
    where, params = "", {}
    if warehouse_id:
        where += " and l.warehouse_id = :wh"
        params["wh"] = warehouse_id
    if store_id:
        where += " and l.store_id = :st"
        params["st"] = store_id
    if q:
        where += " and (lower(k.code) like :q or lower(k.name) like :q or lower(s.name) like :q)"
        params["q"] = f"%{q.lower()}%"
    total = db.execute(text("select count(*) from plan_lines l join skus k on k.id = l.sku_id join stores s on s.id = l.store_id "
                            "where l.plan_id = :p" + where), {"p": plan_id, **params}).scalar()
    lines = _line_rows(db, plan_id, asof, where, params, page_size, (page - 1) * page_size)
    a = plan.alphas
    return dict(id=plan.id, status=plan.status, created_at=plan.created_at, approved_at=plan.approved_at,
                approved_by=plan.approved_by, as_of=asof, horizon_days=plan.horizon_days,
                alphas=a.get("by_category", {}), default_alpha=a.get("default", 0.7), scenario=plan.scenario,
                parent_plan_id=plan.parent_plan_id, solver_status=plan.solver_status, solve_seconds=plan.solve_seconds,
                total_cost=plan.total_cost, cost_breakdown=plan.notes.get("cost_breakdown", {}), kpis=plan.kpis,
                baseline_kpis=_replay_baseline(db), validation=plan.validation, notes=plan.notes,
                total_lines=int(total), page=page, page_size=page_size, lines=lines)


def _replay_baseline(db: Session):
    """Reference values from the stored MEASURED replay (a different basis from the plan's static projection)."""
    import json
    row = db.execute(text("select result from comparison_runs order by id desc limit 1")).first()
    if not row:
        return None
    r = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    return dict(basis="measured replay, mean across seeds (not directly comparable to a static plan projection)",
                kpis={k: dict(baseline=v["baseline"]["mean"], optimized=v["optimized"]["mean"]) for k, v in r["kpis"].items()})


def list_plans(db: Session, limit=20) -> list[dict]:
    rows = db.execute(text("select id, status, created_at, horizon_days, solver_status, total_cost, kpis, scenario, "
                           "parent_plan_id from plans order by id desc limit :n"), {"n": limit}).mappings()
    import json
    out = []
    for r in rows:
        d = dict(r)
        for k in ("kpis", "scenario"):
            if isinstance(d[k], str):
                d[k] = json.loads(d[k])
        out.append(d)
    return out


# ------------------------------------------------------------------ edit / approve
def _lines_df(db: Session, plan_id: int, inp: PlanInputs) -> pd.DataFrame:
    rows = pd.read_sql(text("select id as line_id, sku_id, warehouse_id as wh_id, batch_id, store_id, qty from plan_lines "
                            "where plan_id = :p"), db.connection(), params={"p": plan_id})
    key = pd.Series(np.arange(inp.n), index=pd.MultiIndex.from_arrays([inp.store_id, inp.sku_id]))
    rows["series_idx"] = key.reindex(pd.MultiIndex.from_arrays([rows["store_id"], rows["sku_id"]])).to_numpy()
    lanes = inp.lanes.set_index(["wh_id", "store_id"])
    ci = lanes.reindex(pd.MultiIndex.from_arrays([rows["wh_id"], rows["store_id"]]))
    rows["cost_per_unit"] = ci["cost"].fillna(0).to_numpy()
    rows["lead"] = ci["lead"].fillna(0).astype(int).to_numpy()
    return rows


def _touched_validation(inp: PlanInputs, live: pd.DataFrame, changed: list[int]) -> tuple[list, list]:
    """Re-check only what an edit can affect: every line sharing a batch, warehouse-SKU pool, lane or store with
    a changed line is validated with the full validator (hard constraints), and FEFO is re-checked for the
    changed pools. Untouched pools/lanes/stores were valid before and cannot change."""
    ch = live[live["line_id"].isin(changed)]
    if ch.empty:
        return [], []
    pool = live["wh_id"] * 100000 + live["sku_id"]
    lane = live["wh_id"] * 100000 + live["store_id"]
    c_pool = set((ch["wh_id"] * 100000 + ch["sku_id"]).tolist())
    c_lane = set((ch["wh_id"] * 100000 + ch["store_id"]).tolist())
    mask = (live["batch_id"].isin(set(ch["batch_id"]))) | pool.isin(c_pool) | lane.isin(c_lane) | live["store_id"].isin(set(ch["store_id"]))
    hard = [v for v in validate_plan(inp, live[mask])["violations"] if v["type"] != "fefo"]
    fefo = [v for v in validate_plan(inp, live[pool.isin(c_pool)])["violations"] if v["type"] == "fefo"]
    return hard, fefo


def patch_plan(db: Session, plan_id: int, body) -> dict:
    t = time.time()
    plan = db.get(m.Plan, plan_id)
    if plan is None:
        raise PlanError(404, f"plan {plan_id} not found")
    if plan.status == "approved":
        raise PlanError(409, "plan is already approved and can no longer be changed")
    inp, DL, alpha = _get_ctx(db, plan)
    df = _lines_df(db, plan_id, inp)
    asof = asof_date(db)
    ids = set(df["line_id"])
    for o in body.overrides:
        if o.line_id not in ids:
            raise PlanError(404, f"line {o.line_id} does not belong to plan {plan_id}")
    orig = dict(zip(df["line_id"], df["qty"]))
    new_qty = {o.line_id: o for o in body.overrides}
    new_df = df.copy()
    for lid, o in new_qty.items():
        new_df.loc[new_df["line_id"] == lid, "qty"] = o.qty
    live = new_df[new_df["qty"] > 0]
    changed_ids = [lid for lid, o in new_qty.items() if o.qty != orig[lid]]
    # FEFO is a planning preference a planner may knowingly override; every hard constraint must hold.
    hard, fefo_warn = _touched_validation(inp, live, changed_ids)
    if body.approve and not changed_ids and not plan.validation.get("valid", False):
        hard = hard or [dict(type="plan_invalid", message="the plan failed validation when it was generated")]
    valid = len(hard) == 0
    base = dict(plan_id=plan_id, valid=valid, violations=hard, elapsed_ms=0.0)
    if not valid:
        base.update(status=plan.status, applied=False, updated_lines=[], pick_list_ready=False,
                    elapsed_ms=round((time.time() - t) * 1000, 1))
        return base
    warnings = [dict(v, severity="warning") for v in fefo_warn]
    if body.validate_only:
        base.update(status=plan.status, applied=False, updated_lines=[], pick_list_ready=False, violations=warnings,
                    elapsed_ms=round((time.time() - t) * 1000, 1))
        return base
    now = _now()
    cost_u = dict(zip(new_df["line_id"], new_df["cost_per_unit"]))
    for lid in changed_ids:
        o = new_qty[lid]
        db.execute(text("update plan_lines set qty = :q, transport_cost = :c, status = 'overridden', "
                        "override_reason = :r where id = :i"),
                   {"q": o.qty, "c": round(o.qty * float(cost_u[lid]), 2), "r": o.reason, "i": lid})
        db.add(m.OverrideLog(plan_id=plan_id, line_id=lid, action="override", actor=body.actor, ts=now,
                             original_qty=int(orig[lid]), new_qty=o.qty, reason=o.reason))
    new_status = "overridden" if (changed_ids and plan.status == "pending") else plan.status
    if body.approve:
        new_status = "approved"
        plan.approved_at, plan.approved_by = now, body.actor
        # lines keep override_reason / original_qty, so overridden lines stay identifiable after approval
        db.execute(text("update plan_lines set status = 'approved' where plan_id = :p"), {"p": plan_id})
        chg = set(changed_ids)
        logrows = [dict(plan_id=plan_id, line_id=int(lid), action="approve", actor=body.actor, ts=now,
                        original_qty=int(orig[lid]), new_qty=int(q),
                        reason=("approved with planner override" if lid in chg else "approved as generated"))
                   for lid, q in zip(new_df["line_id"].tolist(), new_df["qty"].tolist()) if q > 0]
        for i in range(0, len(logrows), 5000):
            db.execute(insert(m.OverrideLog), logrows[i:i + 5000])
    plan.status = new_status
    if changed_ids:                                   # re-score only when quantities changed
        series = _series_table(inp, live, DL, alpha, inp.skus.to_dict("index"))
        cost = _costs(live, series, inp.skus.to_dict("index"), inp)
        plan.kpis = kpis_from(inp, series, live.assign(reason=_reason_series(db, plan_id, live)), cost, 0,
                              plan.kpis.get("solve_seconds", 0.0))
        plan.total_cost = cost["total"]
        plan.notes = dict(plan.notes, cost_breakdown=cost, edited=True)
        plan.validation = dict(plan.validation, valid=True, n_violations=0, violations=[],
                               fefo_overridden_warnings=len(fefo_warn),
                               note="re-validated after override (touched pools, lanes and stores)")
    db.commit()
    updated = []
    if changed_ids:
        updated = _line_rows(db, plan_id, asof, " and l.id in (" + ",".join(str(int(i)) for i in changed_ids) + ")")
    base.update(status=new_status, applied=True, updated_lines=updated, kpis=plan.kpis, total_cost=plan.total_cost,
                pick_list_ready=new_status == "approved", violations=warnings,
                elapsed_ms=round((time.time() - t) * 1000, 1))
    return base


def _reason_series(db: Session, plan_id: int, live: pd.DataFrame) -> pd.Series:
    r = pd.read_sql(text("select id, reason from plan_lines where plan_id = :p"), db.connection(), params={"p": plan_id})
    return live["line_id"].map(r.set_index("id")["reason"]).fillna("").to_numpy()


# ------------------------------------------------------------------ pick list
def pick_list(db: Session, plan_id: int, warehouse_id: int | None = None) -> dict:
    plan = db.get(m.Plan, plan_id)
    if plan is None:
        raise PlanError(404, f"plan {plan_id} not found")
    if plan.status != "approved":
        raise PlanError(409, "pick lists are generated after approval; plan status is " + plan.status)
    asof = asof_date(db)
    where, params = "", {}
    if warehouse_id:
        where, params = " and l.warehouse_id = :wh", {"wh": warehouse_id}
    lines = _line_rows(db, plan_id, asof, where + " and l.qty > 0", params)
    lead = {(int(r[0]), int(r[1])): (int(r[2]), float(r[3]))
            for r in db.execute(text("select warehouse_id, store_id, lead_time_days, capacity_volume from lanes")).fetchall()}
    vol = {int(r[0]): float(r[1]) for r in db.execute(text("select id, unit_volume from skus")).fetchall()}
    batches: dict = {}
    lanes: dict = {}
    for l in lines:
        k = l["batch_id"]
        b = batches.setdefault(k, dict(warehouse_id=l["warehouse_id"], warehouse=l["warehouse"], batch_id=k,
                                       batch_code=l["batch_code"], sku_code=l["sku_code"], sku_name=l["sku_name"],
                                       expiry_date=l["batch_expiry"], days_to_expiry=l["days_to_expiry"], qty=0,
                                       destinations=[]))
        b["qty"] += l["qty"]
        b["destinations"].append(dict(store=l["store"], qty=l["qty"],
                                      lead_time_days=lead.get((l["warehouse_id"], l["store_id"]), (0, 0))[0]))
        lk = (l["warehouse_id"], l["store_id"])
        ln = lanes.setdefault(lk, dict(warehouse_id=lk[0], warehouse=l["warehouse"], store_id=lk[1], store=l["store"],
                                       units=0, volume=0.0,
                                       capacity=lead.get(lk, (0, 0.0))[1]))
        ln["units"] += l["qty"]
        ln["volume"] += l["qty"] * vol[l["sku_id"]]
    for ln in lanes.values():
        ln["volume"] = round(ln["volume"], 1)
        ln["utilization_pct"] = round(100.0 * ln["volume"] / ln["capacity"], 1) if ln["capacity"] else 0.0
    return dict(plan_id=plan_id, status=plan.status, warehouse_id=warehouse_id,
                batches=sorted(batches.values(), key=lambda b: (b["expiry_date"], b["batch_id"])),
                lanes=sorted(lanes.values(), key=lambda x: -x["utilization_pct"]))
