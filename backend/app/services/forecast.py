"""GET /forecast: stored LightGBM quantile forecasts joined with stock, plus honest accuracy metrics."""
from __future__ import annotations

import json
import math
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.inputs import asof_date, get_meta, latest_forecast_run
from app.services.inventory import store_frame
from app.simulation import demand as dm


def accuracy(db: Session, run_id: int) -> dict:
    row = db.execute(text("select mode, metrics from forecast_runs where id = :i"), {"i": run_id}).first()
    m = json.loads(row[1]) if isinstance(row[1], str) else row[1]
    met = m["target_met"]
    note = (f"Weekly MAPE {m['mape_mean']:.1f}% (range {m['mape_min']:.1f}-{m['mape_max']:.1f}%) and WAPE {m['wape']:.1f}% "
            f"over {len(m['weeks'])} rolling-origin weeks of the held-out window; PRD target < 20% weekly MAPE is "
            f"{'MET' if met else 'NOT met'} on this simulated data. Model trained on days before the window only "
            f"({m.get('eval_mode')} evaluation, {m.get('train_mode')} training mode).")
    return dict(run_id=run_id, mode=row[0], mape_mean=m["mape_mean"], mape_min=m["mape_min"], mape_max=m["mape_max"],
                wape=m["wape"], coverage_p10_p90=m["coverage_p10_p90"], target_mape=m["target_mape"],
                target_met=bool(met), weeks=m["weeks"], note=note)


def _stockout(avail: float, p7: float, p14: float, p30: float) -> float | None:
    """Days until cumulative P50 demand reaches available stock (linear within 0-7, 7-14, 14-30; extrapolate beyond)."""
    if avail <= 0:
        return 0.0
    pts = [(0, 0.0), (7, p7), (14, p14), (30, p30)]
    for (t0, c0), (t1, c1) in zip(pts[:-1], pts[1:]):
        if avail <= c1:
            return t0 + (t1 - t0) * (avail - c0) / max(c1 - c0, 1e-9)
    return None


def get_forecast(db: Session, *, store_id=None, sku_id=None, region=None, category=None, horizon=None, page=1,
                 page_size=50, sort="days_of_cover", include_series=False) -> dict:
    t = time.time()
    run = latest_forecast_run(db)
    if run is None:
        raise LookupError("no forecast run found - run `python -m scripts.train_forecast`")
    as_of = asof_date(db)
    c = db.connection()
    q = "select store_id, sku_id, horizon, p10, p50, p90, safety_stock from forecasts where run_id = :r"
    params = {"r": run}
    if store_id:
        q += " and store_id = :s"
        params["s"] = store_id
    if sku_id:
        q += " and sku_id = :k"
        params["k"] = sku_id
    fc = pd.read_sql(text(q), c, params=params)
    sdf = store_frame(db, as_of)
    keep = sdf
    if store_id:
        keep = keep[keep["store_id"] == store_id]
    if sku_id:
        keep = keep[keep["sku_id"] == sku_id]
    if region:
        keep = keep[keep["region"].str.lower() == region.lower()]
    if category:
        keep = keep[keep["category"].str.lower() == category.lower()]
    lt = pd.read_sql(text("select store_id, lead_time_days from lanes where cost_rank = 1"), c).set_index("store_id")["lead_time_days"]

    if fc.empty:      # e.g. a store that does not stock that SKU: valid request, nothing to forecast
        return dict(as_of=as_of, run_id=run, total=0, page=page, page_size=page_size, items=[], series=None,
                    accuracy=accuracy(db, run), elapsed_ms=round((time.time() - t) * 1000, 1))
    wide = fc.pivot_table(index=["store_id", "sku_id"], columns="horizon", values=["p10", "p50", "p90", "safety_stock"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    df = keep.merge(wide, how="inner", left_on=["store_id", "sku_id"], right_index=True)
    df["uncertainty_ratio_7d"] = (df["p90_7"] - df["p10_7"]) / df["p50_7"].clip(lower=1.0)
    so = [_stockout(a, a7, a14, a30) for a, a7, a14, a30 in zip(df["available"], df["p50_7"], df["p50_14"], df["p50_30"])]
    df["stockout_days"] = so
    sort_col = {"days_of_cover": "stockout_days", "p50_7": "p50_7", "uncertainty": "uncertainty_ratio_7d",
                "safety_stock": "safety_stock_7"}.get(sort.lstrip("-"), "stockout_days")
    df = df.sort_values(sort_col, ascending=not sort.startswith("-"), na_position="last", kind="stable")
    total = len(df)
    sl = df.iloc[(page - 1) * page_size: page * page_size]
    hs = [horizon] if horizon else [7, 14, 30]
    items = []
    for r in sl.itertuples():
        d = r._asdict()
        ltd = int(lt.get(d["store_id"], 2))
        gap7 = max(d["p90_7"] - d["p50_7"], 0.0)
        sd = d["stockout_days"]
        items.append(dict(
            store_id=int(d["store_id"]), store=d["store"], region=d["region"], sku_id=int(d["sku_id"]),
            sku_code=d["sku_code"], sku_name=d["sku_name"], category=d["category"],
            horizons=[dict(horizon_days=h, p10=round(float(d[f"p10_{h}"]), 2), p50=round(float(d[f"p50_{h}"]), 2),
                           p90=round(float(d[f"p90_{h}"]), 2), safety_stock=round(float(d[f"safety_stock_{h}"]), 2))
                      for h in hs],
            available_stock=int(d["available"]), avg_daily_demand=round(float(d["avg_daily_demand"]), 3),
            days_of_cover=None if pd.isna(d["days_of_cover"]) else round(float(d["days_of_cover"]), 1),
            predicted_stockout_date=None if sd is None or pd.isna(sd) else as_of + timedelta(days=int(math.floor(sd))),
            stockout_within_days=None if sd is None or pd.isna(sd) else round(float(sd), 1),
            uncertainty_ratio_7d=round(float(d["uncertainty_ratio_7d"]), 3),
            safety_stock_explanation=(
                f"Safety stock {d['safety_stock_7']:.1f} units = P90 - P50 demand over the {ltd}-day lead time "
                f"(7-day P90-P50 gap {gap7:.1f} units, rescaled by sqrt({ltd}/7) assuming independent daily demand).")))
    series = None
    if include_series and store_id and sku_id and len(sl):
        series = _series_points(db, store_id, sku_id, as_of, sl.iloc[0])
    return dict(as_of=as_of, run_id=run, total=total, page=page, page_size=page_size, items=items, series=series,
                accuracy=accuracy(db, run), elapsed_ms=round((time.time() - t) * 1000, 1))


def _series_points(db: Session, store_id: int, sku_id: int, as_of: date, row) -> list[dict]:
    t0 = get_meta(db, "as_of")["day_idx"]
    c = db.connection()
    s = pd.read_sql(text("select day_idx, qty from sales_daily where store_id = :s and sku_id = :k"), c,
                    params={"s": store_id, "k": sku_id})
    daily = np.zeros(dm.N_DAYS)
    daily[s["day_idx"].to_numpy()] = s["qty"].to_numpy()
    pts = []
    for w in range(26, 0, -1):               # 26 weeks of history before the as-of date
        a = t0 - 7 * w
        if a < 0:
            continue
        pts.append(dict(week_start=dm.START_DATE + timedelta(a), units=float(daily[a:a + 7].sum()), kind="history"))
    n_w = (dm.N_DAYS - t0) // 7
    for w in range(min(4, n_w)):             # held-out actuals (simulated future) for backtest comparison
        a = t0 + 7 * w
        pts.append(dict(week_start=dm.START_DATE + timedelta(a), units=float(daily[a:a + 7].sum()), kind="actual_held_out"))
    p = {h: (row[f"p10_{h}"], row[f"p50_{h}"], row[f"p90_{h}"]) for h in (7, 14, 30)}
    inc1 = [p[7][i] for i in range(3)]
    inc2 = [p[14][i] - p[7][i] for i in range(3)]
    inc34 = [(p[30][i] - p[14][i]) * 7 / 16 for i in range(3)]
    for w, inc in enumerate([inc1, inc2, inc34, inc34]):
        a = t0 + 7 * w
        pts.append(dict(week_start=dm.START_DATE + timedelta(a), units=float(inc[1]), kind="forecast",
                        p10=float(inc[0]), p50=float(inc[1]), p90=float(inc[2])))
    return pts
