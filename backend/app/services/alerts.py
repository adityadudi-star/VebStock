"""Alerts (P1-3) derived from stock, forecasts and shipments; recomputed on every request so they track the latest forecast run."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.inputs import asof_date, latest_forecast_run
from app.services.inventory import store_frame

TYPES = ["stockout_prediction", "low_stock", "rising_demand", "near_expiry", "delayed_shipment"]


def stockout_days(avail, p7, p14, p30):
    """Days until cumulative P50 demand reaches available stock; NaN if beyond 30 days."""
    avail, p7, p14, p30 = (np.asarray(x, float) for x in (avail, p7, p14, p30))
    t = np.full(avail.shape, np.nan)
    c0 = np.zeros_like(avail)
    done = np.zeros(avail.shape, bool)
    for t0, t1, c1 in ((0, 7, p7), (7, 14, p14), (14, 30, p30)):
        hit = (~done) & (avail <= c1)
        denom = np.maximum(c1 - c0, 1e-9)
        t[hit] = t0 + (t1 - t0) * (avail[hit] - c0[hit]) / denom[hit]
        done |= hit
        c0 = c1
    t[avail <= 0] = 0.0
    return t


def get_alerts(db: Session, region: str | None = None, alert_type: str | None = None, limit: int = 60) -> dict:
    as_of = asof_date(db)
    run = latest_forecast_run(db)
    sdf = store_frame(db, as_of)
    if region:
        sdf = sdf[sdf["region"].str.lower() == region.lower()]
    c = db.connection()
    fc = pd.read_sql(text("select store_id, sku_id, horizon, p50 from forecasts where run_id = :r"), c, params={"r": run})
    w = fc.pivot_table(index=["store_id", "sku_id"], columns="horizon", values="p50")
    w.columns = [f"p50_{h}" for h in w.columns]
    df = sdf.merge(w, how="left", left_on=["store_id", "sku_id"], right_index=True)
    df["so"] = stockout_days(df["available"], df["p50_7"].fillna(0), df["p50_14"].fillna(0), df["p50_30"].fillna(0))
    out: dict[str, list] = {t: [] for t in TYPES}
    counts: dict[str, int] = {}

    def add(t, frame, builder, sort_key, asc=True):
        counts[t] = int(len(frame))
        for r in frame.sort_values(sort_key, ascending=asc).head(limit).itertuples():
            out[t].append(builder(r))

    s = df[df["so"] <= 7]
    add("stockout_prediction", s,
        lambda r: dict(type="stockout_prediction", severity="high" if r.so <= 3 else "medium", store=r.store, region=r.region,
                       sku_code=r.sku_code, sku_name=r.sku_name,
                       message=f"Predicted stockout in {r.so:.1f} days ({r.available} units available vs P50 {r.p50_7:.0f} units/7d)",
                       value=round(float(r.so), 1)), "so")
    lo = df[df["low_stock"] & (df["avg_daily_demand"] > 0)]
    add("low_stock", lo,
        lambda r: dict(type="low_stock", severity="high" if (r.days_of_cover or 0) < 1 else "medium", store=r.store,
                       region=r.region, sku_code=r.sku_code, sku_name=r.sku_name,
                       message=f"{r.available} units available = {0 if pd.isna(r.days_of_cover) else r.days_of_cover:.1f} days of cover",
                       value=None if pd.isna(r.days_of_cover) else round(float(r.days_of_cover), 1)), "days_of_cover")
    ratio = df["p50_7"] / (df["avg_daily_demand"] * 7).clip(lower=1e-9)
    df["rise"] = ratio
    ri = df[(df["rise"] >= 1.3) & (df["p50_7"] >= 5)]
    add("rising_demand", ri,
        lambda r: dict(type="rising_demand", severity="medium", store=r.store, region=r.region, sku_code=r.sku_code,
                       sku_name=r.sku_name,
                       message=f"Forecast 7-day demand {r.p50_7:.0f} is {100 * (r.rise - 1):.0f}% above the trailing 28-day average",
                       value=round(float(r.rise), 2)), "rise", False)
    ne = df[df["expiry_risk"]]
    add("near_expiry", ne,
        lambda r: dict(type="near_expiry", severity="high" if r.qty_expiry_at_risk >= 20 else "medium", store=r.store,
                       region=r.region, sku_code=r.sku_code, sku_name=r.sku_name,
                       message=f"{r.qty_expiry_at_risk} units cannot be sold before expiry at the average rate "
                               f"(nearest expiry {pd.Timestamp(r.nearest_expiry).date() if not pd.isna(r.nearest_expiry) else 'n/a'})",
                       value=int(r.qty_expiry_at_risk)), "qty_expiry_at_risk", False)
    dl = pd.read_sql(text(
        "select i.qty, i.eta_date, i.delay_days, s.name as store, s.region, k.code as sku_code, k.name as sku_name "
        "from incoming_shipments i join stores s on s.id = i.store_id join skus k on k.id = i.sku_id where i.delay_days > 0"), c)
    if region and len(dl):
        dl = dl[dl["region"].str.lower() == region.lower()]
    counts["delayed_shipment"] = int(len(dl))
    for r in dl.sort_values("delay_days", ascending=False).head(limit).itertuples():
        out["delayed_shipment"].append(dict(
            type="delayed_shipment", severity="high" if r.delay_days >= 4 else "medium", store=r.store, region=r.region,
            sku_code=r.sku_code, sku_name=r.sku_name,
            message=f"{r.qty} units delayed {r.delay_days} days, new ETA {pd.Timestamp(r.eta_date).date()}", value=int(r.delay_days)))
    alerts = out.get(alert_type, []) if alert_type else [a for t in TYPES for a in out[t]]
    return dict(as_of=as_of, counts=counts, total=sum(counts.values()) if not alert_type else counts.get(alert_type, 0),
                alerts=alerts, refreshed_with_forecast_run=run)
