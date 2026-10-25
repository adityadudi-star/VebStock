"""POST /simulate: re-plan under a what-if scenario and diff against the base plan."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import models as m
from app.services import plans as ps

KPI_DELTA_KEYS = ["projected_fill_rate_pct", "unmet_demand_units", "shortage_vs_target_units", "expected_expiring_units",
                  "expected_expiry_value", "transport_cost", "shortage_cost", "expiry_cost", "units_shipped", "shipments"]


def _lines(db: Session, plan_id: int) -> pd.DataFrame:
    return pd.read_sql(text(
        "select l.store_id, s.name as store, l.sku_id, k.code as sku_code, l.warehouse_id, w.name as warehouse, "
        "l.batch_id, l.qty from plan_lines l join stores s on s.id = l.store_id join skus k on k.id = l.sku_id "
        "join warehouses w on w.id = l.warehouse_id where l.plan_id = :p"), db.connection(), params={"p": plan_id})


def diff_plans(db: Session, base_id: int, new_id: int) -> dict:
    base, new = db.get(m.Plan, base_id), db.get(m.Plan, new_id)
    a, b = _lines(db, base_id), _lines(db, new_id)
    ka = a.groupby(["store_id", "sku_id", "warehouse_id"], as_index=False).agg(
        qty=("qty", "sum"), store=("store", "first"), sku_code=("sku_code", "first"), warehouse=("warehouse", "first"))
    kb = b.groupby(["store_id", "sku_id", "warehouse_id"], as_index=False).agg(
        qty=("qty", "sum"), store=("store", "first"), sku_code=("sku_code", "first"), warehouse=("warehouse", "first"))
    mg = ka.merge(kb, how="outer", on=["store_id", "sku_id", "warehouse_id"], suffixes=("_base", "_new"))
    mg["qty_base"] = mg["qty_base"].fillna(0).astype(int)
    mg["qty_new"] = mg["qty_new"].fillna(0).astype(int)
    for c in ("store", "sku_code", "warehouse"):
        mg[c] = mg[f"{c}_base"].fillna(mg[f"{c}_new"])
    mg["delta"] = mg["qty_new"] - mg["qty_base"]
    changed = mg[mg["delta"] != 0]
    # rerouted: a store-SKU whose set of source warehouses differs between plans
    sa = a.groupby(["store_id", "sku_id"])["warehouse_id"].apply(lambda s: tuple(sorted(set(s))))
    sb = b.groupby(["store_id", "sku_id"])["warehouse_id"].apply(lambda s: tuple(sorted(set(s))))
    both = pd.concat([sa.rename("a"), sb.rename("b")], axis=1).dropna()
    rerouted = int((both["a"] != both["b"]).sum())
    ka_series = set(sa.index)
    kb_series = set(sb.index)
    kd = {k: round(float(new.kpis.get(k, 0)) - float(base.kpis.get(k, 0)), 2) for k in KPI_DELTA_KEYS}
    cost_delta = dict(total=round(new.total_cost - base.total_cost, 2),
                      transport=round(new.kpis["transport_cost"] - base.kpis["transport_cost"], 2),
                      shortage=round(new.kpis["shortage_cost"] - base.kpis["shortage_cost"], 2),
                      expiry=round(new.kpis["expiry_cost"] - base.kpis["expiry_cost"], 2))
    top = changed.reindex(changed["delta"].abs().sort_values(ascending=False).index).head(150)
    return dict(
        base_plan_id=base_id, new_plan_id=new_id,
        shipment_diff=dict(lines_changed=int(len(changed)), lines_added=int(((mg["qty_base"] == 0) & (mg["qty_new"] > 0)).sum()),
                           lines_removed=int(((mg["qty_base"] > 0) & (mg["qty_new"] == 0)).sum()),
                           store_skus_rerouted=rerouted, store_skus_newly_served=len(kb_series - ka_series),
                           store_skus_no_longer_served=len(ka_series - kb_series),
                           units_base=int(mg["qty_base"].sum()), units_new=int(mg["qty_new"].sum())),
        additional_shortage_units=kd["unmet_demand_units"],
        additional_shortage_vs_target_units=kd["shortage_vs_target_units"],
        cost_delta=cost_delta, kpi_deltas=kd,
        kpis_base={k: base.kpis.get(k) for k in KPI_DELTA_KEYS}, kpis_new={k: new.kpis.get(k) for k in KPI_DELTA_KEYS},
        changed_lines=[dict(store=r.store, sku_code=r.sku_code, warehouse=r.warehouse, qty_base=int(r.qty_base),
                            qty_new=int(r.qty_new), delta=int(r.delta)) for r in top.itertuples()])


def simulate(db: Session, req) -> dict:
    scenario = req.scenario.model_dump(exclude_none=True)
    base_id = req.base_plan_id
    if base_id is None:
        for pid, sc in db.execute(text("select id, scenario from plans order by id desc limit 50")).fetchall():
            if not sc or sc in ("null", "{}"):          # portable: JSON columns cannot be compared in SQL on PostgreSQL
                base_id = pid
                break
    if base_id is None:
        base_id = ps.create_plan(db, horizon=req.horizon_days, alphas=req.alphas, default_alpha=req.default_alpha)
    base = db.get(m.Plan, base_id)
    if base is None:
        raise ps.PlanError(404, f"base plan {base_id} not found")
    a = base.alphas
    new_id = ps.create_plan(db, horizon=base.horizon_days, alphas=a.get("by_category", {}),
                            default_alpha=a.get("default", 0.7), scenario=scenario, parent_id=base_id)
    cmp = diff_plans(db, base_id, new_id)
    sim = m.SimulationResult(base_plan_id=base_id, new_plan_id=new_id, scenario=scenario, comparison=cmp)
    db.add(sim)
    db.commit()
    return dict(simulation_id=sim.id, scenario=scenario, base_plan_id=base_id,
                new_plan=ps.get_plan(db, new_id, page=1, page_size=100), comparison=cmp)
