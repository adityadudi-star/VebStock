"""Build optimiser inputs from the database (and apply what-if scenarios)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.forecasting.safety import safety_stock
from app.optimization.types import PlanInputs


def get_meta(db: Session, key: str) -> dict:
    import json
    v = db.execute(text("select value from meta where key = :k"), {"k": key}).scalar()
    if v is None:
        raise LookupError(f"meta '{key}' missing - run `python -m scripts.seed` first")
    return json.loads(v) if isinstance(v, str) else v


def asof_date(db: Session) -> date:
    return date.fromisoformat(get_meta(db, "as_of")["date"])


def latest_forecast_run(db: Session) -> int | None:
    return db.execute(text("select max(id) from forecast_runs")).scalar()


def horizon_demand(p: dict[int, np.ndarray], H: int) -> np.ndarray:
    """Interpolate cumulative demand over horizon H from the 7/14/30-day forecasts (linear in days)."""
    if H <= 7:
        return p[7] * H / 7
    if H <= 14:
        return p[7] + (p[14] - p[7]) * (H - 7) / 7
    if H <= 30:
        return p[14] + (p[30] - p[14]) * (H - 14) / 16
    return p[30] + (p[30] - p[14]) / 16 * (H - 30)


def build_inputs(db: Session, horizon: int, alphas: dict | None, scenario: dict | None = None,
                 default_alpha: float = 0.7) -> PlanInputs:
    scenario = scenario or {}
    conn = db.connection()
    asof = asof_date(db)
    run = latest_forecast_run(db)
    if run is None:
        raise LookupError("no forecast run found - run `python -m scripts.train_forecast` first")

    fc = pd.read_sql(text("select store_id, sku_id, horizon, p10, p50, p90 from forecasts where run_id = :r"),
                     conn, params={"r": run})
    stock = pd.read_sql(text("select store_id, sku_id, on_hand, reserved from store_stock order by store_id, sku_id"), conn)
    skus = pd.read_sql(text("select * from skus"), conn).set_index("id")
    stores = pd.read_sql(text("select id, name, capacity_volume from stores"), conn).set_index("id")
    whs = pd.read_sql(text("select id, name from warehouses"), conn).set_index("id")
    lanes = pd.read_sql(text("select warehouse_id as wh_id, store_id, cost_per_unit as cost, "
                             "lead_time_days as lead, capacity_volume as cap from lanes"), conn)
    batches = pd.read_sql(text("select id, warehouse_id as wh_id, sku_id, qty, expiry_date, received_date from warehouse_batches"), conn)
    wh_sku = pd.read_sql(text("select warehouse_id, sku_id, reserved_qty from warehouse_sku"), conn)
    inc = pd.read_sql(text("select store_id, sku_id, qty, eta_date, delay_days from incoming_shipments"), conn)

    # ---- scenario: closure / cost change / supplier delay ---------------------------------
    closed: set = set()
    extra_lead: dict = {}
    sc_type = scenario.get("type")
    if sc_type == "warehouse_closure":
        closed.add(int(scenario["warehouse_id"]))
    if sc_type == "transport_cost_change":
        pct = float(scenario.get("pct", 0)) / 100.0
        wid = scenario.get("warehouse_id")
        mask = np.ones(len(lanes), bool) if wid is None else (lanes["wh_id"] == int(wid)).to_numpy()
        lanes.loc[mask, "cost"] = lanes.loc[mask, "cost"] * (1 + pct)
    if sc_type == "supplier_delay":
        d = int(scenario.get("delay_days", 0))
        wid = scenario.get("warehouse_id")
        for w in (whs.index if wid is None else [int(wid)]):
            extra_lead[int(w)] = d
    lanes = lanes[~lanes["wh_id"].isin(closed)].copy()
    lanes["_c"] = lanes["cost"]
    lanes = lanes.sort_values(["store_id", "_c"])
    lanes["rank"] = lanes.groupby("store_id").cumcount() + 1
    n_cand = 3
    lanes = lanes[lanes["rank"] <= n_cand].drop(columns="_c")

    # ---- demand & safety stock ------------------------------------------------------------
    piv = {h: fc[fc["horizon"] == h].set_index(["store_id", "sku_id"]).sort_index() for h in (7, 14, 30)}
    idx = stock.set_index(["store_id", "sku_id"]).index
    p10 = {h: piv[h]["p10"].reindex(idx).fillna(0).to_numpy() for h in piv}
    p50 = {h: piv[h]["p50"].reindex(idx).fillna(0).to_numpy() for h in piv}
    p90 = {h: piv[h]["p90"].reindex(idx).fillna(0).to_numpy() for h in piv}
    DH = horizon_demand(p50, horizon)
    P10H = horizon_demand(p10, horizon)
    P90H = horizon_demand(p90, horizon)
    lead_best = lanes[lanes["rank"] == 1].set_index("store_id")["lead"]
    lt = stock["store_id"].map(lead_best).fillna(lanes["lead"].max() if len(lanes) else 3).to_numpy().astype(float)
    if extra_lead and len(set(extra_lead.values())) == 1 and len(extra_lead) == len(whs):
        lt = lt + list(extra_lead.values())[0]
    SS = safety_stock(p50[7], p90[7], 7, lt)

    if sc_type == "demand_spike":
        pct = float(scenario.get("pct", 40)) / 100.0
        mask = np.ones(len(stock), bool)
        if scenario.get("category"):
            cats = skus["category"].reindex(stock["sku_id"]).to_numpy()
            mask &= cats == scenario["category"]
        if scenario.get("sku_ids"):
            mask &= stock["sku_id"].isin([int(x) for x in scenario["sku_ids"]]).to_numpy()
        f = np.where(mask, 1 + pct, 1.0)
        DH, P10H, P90H, SS = DH * f, P10H * f, P90H * f, SS * f

    # ---- incoming within horizon (supplier delay pushes ETAs out) -------------------------
    R = np.zeros(len(stock))
    if len(inc):
        delay = max(extra_lead.values()) if extra_lead else 0
        inc = inc.copy()
        inc["days"] = (pd.to_datetime(inc["eta_date"]).dt.date.map(lambda d: (d - asof).days)) + delay
        inc = inc[inc["days"] <= horizon]
        s = inc.groupby(["store_id", "sku_id"])["qty"].sum().reindex(idx).fillna(0).to_numpy()
        R = s

    batches = batches[~batches["wh_id"].isin([])].copy()
    batches["exp_days"] = pd.to_datetime(batches["expiry_date"]).dt.date.map(lambda d: (d - asof).days)
    batches["recv_days"] = pd.to_datetime(batches["received_date"]).dt.date.map(lambda d: (d - asof).days)
    batches = batches[batches["qty"] > 0][["id", "wh_id", "sku_id", "qty", "exp_days", "recv_days"]]
    wh_reserved = {(int(a), int(b)): int(c) for a, b, c in zip(wh_sku["warehouse_id"], wh_sku["sku_id"], wh_sku["reserved_qty"])}

    I = (stock["on_hand"] - stock["reserved"]).clip(lower=0).to_numpy().astype(float)
    return PlanInputs(
        horizon=horizon, store_id=stock["store_id"].to_numpy(), sku_id=stock["sku_id"].to_numpy(), I=I, R=R,
        DH=DH, SS=SS, rate=DH / horizon, p10h=P10H, p90h=P90H, lanes=lanes, batches=batches,
        wh_reserved=wh_reserved, store_cap=stores["capacity_volume"].to_dict(),
        skus=skus[["lost_margin", "writeoff_cost", "unit_volume", "min_shelf_life_days", "category", "name"]],
        alpha_by_category=dict(alphas or {}), default_alpha=default_alpha,
        store_names=stores["name"].to_dict(), wh_names=whs["name"].to_dict(), asof_label=asof.isoformat(),
        closed_warehouses=closed, extra_lead=extra_lead, n_candidate_lanes=n_cand)
