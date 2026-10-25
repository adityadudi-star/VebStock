"""Dashboard aggregates (GET /overview) plus /meta, /overrides and the rule-based assistant."""
from __future__ import annotations

import json
import re
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import models as m
from app.services import alerts as al
from app.services import forecast as fs
from app.services import inventory as inv
from app.services.inputs import asof_date, get_meta, latest_forecast_run
from app.simulation import demand as dm


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def _daily_totals(db: Session) -> np.ndarray:
    def build():
        rows = db.execute(text("select day_idx, sum(qty) from sales_daily group by day_idx")).fetchall()
        arr = np.zeros(dm.N_DAYS)
        for d, q in rows:
            arr[int(d)] = float(q)
        return arr
    return inv._cached(("daily_totals",), build)


def overview(db: Session) -> dict:
    as_of = asof_date(db)
    t0 = get_meta(db, "as_of")["day_idx"]
    summ = inv.get_inventory(db, level="region", page_size=1)["summary"]
    sdf, wdf = inv.store_frame(db, as_of), inv.warehouse_frame(db, as_of)
    a = al.get_alerts(db, limit=1)
    by_wh = wdf.groupby("warehouse")[["on_hand", "reserved", "available"]].sum().reset_index()
    by_cat = sdf.groupby("category")[["on_hand", "reserved", "available"]].sum().reset_index()
    daily = _daily_totals(db)
    trend = []
    for w in range(26, 0, -1):
        s = t0 - 7 * w
        if s >= 0:
            trend.append(dict(week_start=(dm.START_DATE + timedelta(s)).isoformat(), units=float(daily[s:s + 7].sum()), kind="history"))
    for w in range((dm.N_DAYS - t0) // 7):
        s = t0 + 7 * w
        trend.append(dict(week_start=(dm.START_DATE + timedelta(s)).isoformat(), units=float(daily[s:s + 7].sum()),
                          kind="actual_held_out"))
    run = latest_forecast_run(db)
    fc = pd.read_sql(text("select horizon, sum(p10) p10, sum(p50) p50, sum(p90) p90 from forecasts where run_id = :r group by horizon"),
                     db.connection(), params={"r": run}).set_index("horizon")
    inc = [(7, fc.loc[7]), (14, fc.loc[14] - fc.loc[7]), (30, (fc.loc[30] - fc.loc[14]) * 7 / 16)]
    for w, (_h, r) in enumerate([inc[0], inc[1], inc[2], inc[2]]):
        s = t0 + 7 * w
        trend.append(dict(week_start=(dm.START_DATE + timedelta(s)).isoformat(), units=float(r["p50"]), kind="forecast",
                          p10=float(r["p10"]), p90=float(r["p90"])))
    plan = db.execute(text("select id, status, created_at, kpis, solver_status, total_cost from plans order by id desc limit 1")).first()
    plan_d = None
    if plan:
        plan_d = dict(id=plan[0], status=plan[1], created_at=str(plan[2]), kpis=_j(plan[3]), solver_status=plan[4], total_cost=plan[5])
    cmp_row = db.execute(text("select result from comparison_runs order by id desc limit 1")).first()
    cmp_d = _j(cmp_row[0]) if cmp_row else None
    ob = None
    kpi_cards = None
    if cmp_d:
        ob = [dict(kpi=k, baseline=v["baseline"]["mean"], optimized=v["optimized"]["mean"]) for k, v in cmp_d["kpis"].items()
              if k in ("stockout_rate", "fill_rate", "expiry_wastage_pct", "transport_cost")]
        kpi_cards = {k: dict(baseline=v["baseline"]["mean"], optimized=v["optimized"]["mean"], rel_diff_pct=v["rel_diff_pct"])
                     for k, v in cmp_d["kpis"].items()}
    return dict(
        as_of=as_of, inventory=summ, alert_counts=a["counts"],
        kpis_replay=kpi_cards, kpis_replay_label="Measured in the simulated 5-seed replay (optimized vs baseline means)" if cmp_d else None,
        forecast_accuracy=fs.accuracy(db, run), latest_plan=plan_d,
        charts=dict(inventory_by_warehouse=by_wh.to_dict("records"), inventory_by_category=by_cat.to_dict("records"),
                    demand_trend=trend, optimized_vs_baseline=ob))


def meta(db: Session) -> dict:
    rows = {r[0]: _j(r[1]) for r in db.execute(text("select key, value from meta")).fetchall()}
    run = latest_forecast_run(db)
    cmp_row = db.execute(text("select id, created_at, config from comparison_runs order by id desc limit 1")).first()
    cats = pd.read_sql(text("select category, avg(unit_price) avg_price, avg(lost_margin) lost_margin_per_unit, "
                            "avg(writeoff_cost) writeoff_per_unit, min(shelf_life_days) shelf_life_days, "
                            "min(min_shelf_life_days) min_remaining_shelf_life_days, count(*) skus from skus group by category"),
                       db.connection())
    for col in cats.columns:
        if col != "category":
            cats[col] = cats[col].astype(float)
    return dict(
        generator_settings=rows.get("generator_settings"), as_of=rows.get("as_of"), counts=rows.get("counts"),
        festivals=rows.get("festivals"), notes=rows.get("notes"), categories=cats.round(2).to_dict("records"),
        cost_assumptions=dict(
            transport="lane cost per unit = base + per_km x distance (generator settings)",
            lost_margin="pi_s = unit price x category margin %",
            writeoff="eps_s = unit price x category write-off %",
            alpha="objective = c.x + alpha*pi*unmet + (1-alpha)*eps*expiring (PRD 7.1); default alpha 0.7",
            baseline="reorder point = avg lead-time demand + 2 days avg demand; order-up-to + 7 days; nearest warehouse; "
                     "proportional allocation; FIFO"),
        forecast_run_id=run, comparison=dict(run_id=cmp_row[0], created_at=str(cmp_row[1]), config=_j(cmp_row[2])) if cmp_row else None,
        thresholds=inv.THRESHOLDS,
        warehouses=[dict(id=r[0], name=r[1], region=r[2]) for r in db.execute(text("select id, name, region from warehouses order by id")).fetchall()],
        categories_list=[r[0] for r in db.execute(text("select distinct category from skus order by category")).fetchall()])


def overrides(db: Session, plan_id=None, action=None, page=1, page_size=50) -> dict:
    where, p = " where 1=1", {}
    if plan_id:
        where += " and o.plan_id = :p"
        p["p"] = plan_id
    if action:
        where += " and o.action = :a"
        p["a"] = action
    total = db.execute(text("select count(*) from override_log o" + where), p).scalar()
    rows = db.execute(text(
        "select o.id, o.plan_id, o.line_id, o.action, o.actor, o.ts, o.original_qty, o.new_qty, o.reason, "
        "k.code as sku_code, s.name as store, w.name as warehouse from override_log o "
        "left join plan_lines l on l.id = o.line_id left join skus k on k.id = l.sku_id "
        "left join stores s on s.id = l.store_id left join warehouses w on w.id = l.warehouse_id" + where +
        " order by o.id desc limit :n offset :o"), {**p, "n": page_size, "o": (page - 1) * page_size}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d["ts"], str):
            d["ts"] = pd.Timestamp(d["ts"]).to_pydatetime()
        out.append(d)
    return dict(total=int(total), page=page, page_size=page_size, rows=out)
