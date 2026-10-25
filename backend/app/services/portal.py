"""Role-portal read models. Everything here is derived from existing tables (no new data is stored):
finance valuation at list price, and the approved-plan deliveries / in-transit stock for one store."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import inventory as inv
from app.services import plans as plan_svc
from app.services.inputs import asof_date, get_meta

HISTORY_DAYS = 28

LIMITATIONS = [
    "No unit cost or purchase price is stored, so cost of goods, gross margin and profit cannot be calculated.",
    "Sales value is units sold multiplied by the current list price. Promotion discounts and actual invoice prices are not stored.",
    "There are no invoices, customer payments, supplier payments or payables in the data, so receivables and payables are not shown.",
    "Expiry exposure uses each product's configured write-off cost, not an accounting write-off.",
    "All figures come from simulated data.",
]


def finance_summary(db: Session) -> dict:
    as_of = asof_date(db)
    t0 = get_meta(db, "as_of")["day_idx"]
    c = db.connection()

    def one(sql: str, **p) -> pd.DataFrame:
        return pd.read_sql(text(sql), c, params=p)

    stock = one(
        "select 'store' as tier, k.category, sum(s.on_hand * k.unit_price) as value, sum(s.on_hand) as units "
        "from store_stock s join skus k on k.id = s.sku_id group by k.category "
        "union all select 'warehouse', k.category, sum(b.qty * k.unit_price), sum(b.qty) "
        "from warehouse_batches b join skus k on k.id = b.sku_id group by k.category "
        "union all select 'in_transit', k.category, sum(i.qty * k.unit_price), sum(i.qty) "
        "from incoming_shipments i join skus k on k.id = i.sku_id group by k.category")
    sales = one(
        "select k.category, sum(d.qty * k.unit_price) as value, sum(d.qty) as units "
        "from sales_daily d join skus k on k.id = d.sku_id where d.day_idx >= :a and d.day_idx < :b group by k.category",
        a=t0 - HISTORY_DAYS, b=t0)

    woff = one("select id as sku_id, writeoff_cost, unit_price from skus").set_index("sku_id")
    exposure = {}
    for tier, frame in (("store", inv.store_frame(db, as_of)), ("warehouse", inv.warehouse_frame(db, as_of))):
        f = frame[frame["qty_expiry_at_risk"] > 0]
        exposure[tier] = dict(
            units=int(f["qty_expiry_at_risk"].sum()),
            writeoff_value=float((f["qty_expiry_at_risk"] * f["sku_id"].map(woff["writeoff_cost"])).sum()),
            list_value=float((f["qty_expiry_at_risk"] * f["sku_id"].map(woff["unit_price"])).sum()),
        )

    plan = None
    row = db.execute(text("select id from plans order by id desc limit 1")).first()
    if row:
        p = plan_svc.get_plan(db, row[0], page_size=1)
        plan = dict(id=p["id"], status=p["status"],
                    cost_breakdown=p["cost_breakdown"], units_shipped=p["kpis"].get("units_shipped"),
                    projected_fill_rate_pct=p["kpis"].get("projected_fill_rate_pct"),
                    expected_expiry_value=p["kpis"].get("expected_expiry_value"))

    by_tier = stock.groupby("tier")[["value", "units"]].sum()
    return dict(
        as_of=as_of,
        inventory_value=dict(
            basis="list price",
            total=float(stock["value"].sum()),
            by_tier={t: dict(value=float(r["value"]), units=int(r["units"])) for t, r in by_tier.iterrows()},
            by_category=[dict(category=k, store=float(g[g.tier == "store"]["value"].sum()),
                              warehouse=float(g[g.tier == "warehouse"]["value"].sum()),
                              in_transit=float(g[g.tier == "in_transit"]["value"].sum()))
                         for k, g in stock.groupby("category")]),
        sales=dict(basis="list price", days=HISTORY_DAYS, total=float(sales["value"].sum()), units=int(sales["units"].sum()),
                   by_category=[dict(category=r.category, value=float(r.value), units=int(r.units)) for r in sales.itertuples()]),
        expiry_exposure=exposure,
        latest_plan=plan,
        limitations=LIMITATIONS,
    )


def retail_deliveries(db: Session, store_id: int) -> dict:
    """What is on its way to one store: in-transit shipments, plus lines of the latest approved plan."""
    c = db.connection()
    store = db.execute(text("select id, name, region from stores where id = :i"), dict(i=store_id)).first()
    if store is None:
        raise LookupError(f"store {store_id} not found")
    incoming = pd.read_sql(text(
        "select k.code as sku_code, k.name as sku_name, i.qty, i.eta_date, i.delay_days, i.status "
        "from incoming_shipments i join skus k on k.id = i.sku_id where i.store_id = :s order by i.eta_date, k.code"),
        c, params=dict(s=store_id))
    plan = db.execute(text("select id, approved_at, approved_by from plans where status = 'approved' order by id desc limit 1")).first()
    lines = pd.DataFrame()
    if plan:
        lines = pd.read_sql(text(
            "select k.code as sku_code, k.name as sku_name, w.name as warehouse, pl.qty, l.lead_time_days "
            "from plan_lines pl join skus k on k.id = pl.sku_id join warehouses w on w.id = pl.warehouse_id "
            "left join lanes l on l.warehouse_id = pl.warehouse_id and l.store_id = pl.store_id "
            "where pl.plan_id = :p and pl.store_id = :s and pl.qty > 0 order by k.code"),
            c, params=dict(p=plan[0], s=store_id))
    return dict(
        store=dict(id=store[0], name=store[1], region=store[2]),
        incoming=[dict(r._asdict(), eta_date=str(r.eta_date)[:10]) for r in incoming.itertuples(index=False)],
        approved_plan=None if not plan else dict(id=plan[0], approved_at=str(plan[1]) if plan[1] else None, approved_by=plan[2]),
        planned_lines=lines.to_dict("records"),
    )
