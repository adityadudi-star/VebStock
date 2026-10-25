"""Inventory views (GET /inventory) and the flag logic shared with alerts and the overview.

Flags (thresholds are returned with every response):
  low_stock    : available / avg daily demand < LOW_DAYS  (stores: 3 days; warehouses: 7 days)
  excess_stock : available / avg daily demand > EXCESS_DAYS (stores: 30 days; warehouses: 60 days)
  expiry_risk  : units that FEFO consumption at the average daily rate cannot sell before expiry
                 (per batch: clip(cumulative qty - rate * days_left, 0, qty); expired batches are fully at risk)
"""
from __future__ import annotations

import time
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.inputs import asof_date, get_meta

STORE_LOW_DAYS, STORE_EXCESS_DAYS = 3.0, 30.0
WH_LOW_DAYS, WH_EXCESS_DAYS = 7.0, 60.0
THRESHOLDS = {"store_low_days": STORE_LOW_DAYS, "store_excess_days": STORE_EXCESS_DAYS,
              "warehouse_low_days": WH_LOW_DAYS, "warehouse_excess_days": WH_EXCESS_DAYS,
              "expiry_risk_rule": "units not sellable before expiry at the average daily rate (FEFO)"}

_CACHE: dict = {}
_TTL = 60.0


def _cached(key, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def clear_cache() -> None:
    _CACHE.clear()


def _at_risk(batches: pd.DataFrame, group_cols: list[str], rate: pd.Series, as_of: date) -> pd.DataFrame:
    """Adds days_left and qty_at_risk to a batch frame sorted by expiry within group."""
    b = batches.copy()
    b["expiry_date"] = pd.to_datetime(b["expiry_date"])
    b["days_left"] = (b["expiry_date"] - pd.Timestamp(as_of)).dt.days
    b = b.sort_values(group_cols + ["expiry_date"])
    b["cum"] = b.groupby(group_cols)["qty"].cumsum()
    b["rate"] = rate.reindex(pd.MultiIndex.from_frame(b[group_cols])).fillna(0).to_numpy()
    sell = b["rate"] * b["days_left"].clip(lower=0)
    b["qty_at_risk"] = np.where(b["days_left"] < 0, b["qty"], np.clip(b["cum"] - sell, 0, b["qty"])).round().astype(int)
    return b


def store_frame(db: Session, as_of: date) -> pd.DataFrame:
    def build():
        c = db.connection()
        df = pd.read_sql(text(
            "select ss.store_id, ss.sku_id, ss.on_hand, ss.reserved, ss.incoming, ss.avg_daily_demand, "
            "st.name as store, st.region, d.name as distributor, k.code as sku_code, k.name as sku_name, k.category "
            "from store_stock ss join stores st on st.id = ss.store_id join distributors d on d.id = st.distributor_id "
            "join skus k on k.id = ss.sku_id"), c)
        b = pd.read_sql(text("select store_id, sku_id, qty, expiry_date from store_batches"), c)
        rate = df.set_index(["store_id", "sku_id"])["avg_daily_demand"]
        if len(b):
            br = _at_risk(b, ["store_id", "sku_id"], rate, as_of)
            g = br.groupby(["store_id", "sku_id"]).agg(qty_expiry_at_risk=("qty_at_risk", "sum"),
                                                        nearest_expiry=("expiry_date", "min"))
            df = df.merge(g, how="left", left_on=["store_id", "sku_id"], right_index=True)
        else:
            df["qty_expiry_at_risk"], df["nearest_expiry"] = 0, pd.NaT
        df["qty_expiry_at_risk"] = df["qty_expiry_at_risk"].fillna(0).astype(int)
        df["available"] = (df["on_hand"] - df["reserved"]).clip(lower=0)
        rate_v = df["avg_daily_demand"].to_numpy()
        df["days_of_cover"] = np.where(rate_v > 1e-9, df["available"] / np.where(rate_v > 1e-9, rate_v, 1), np.nan)
        df["low_stock"] = (df["days_of_cover"] < STORE_LOW_DAYS) | ((rate_v <= 1e-9) & (df["available"] == 0))
        df["excess_stock"] = df["days_of_cover"] > STORE_EXCESS_DAYS
        df["expiry_risk"] = df["qty_expiry_at_risk"] > 0
        return df
    return _cached(("store", as_of), build)


def warehouse_frame(db: Session, as_of: date) -> pd.DataFrame:
    def build():
        c = db.connection()
        asof_idx = get_meta(db, "as_of")["day_idx"]
        wb = pd.read_sql(text(
            "select b.id, b.warehouse_id, b.sku_id, b.qty, b.expiry_date from warehouse_batches b"), c)
        ws = pd.read_sql(text("select warehouse_id, sku_id, reserved_qty from warehouse_sku"), c)
        whs = pd.read_sql(text("select id as warehouse_id, name as warehouse, region from warehouses"), c)
        sk = pd.read_sql(text("select id as sku_id, code as sku_code, name as sku_name, category from skus"), c)
        dl = pd.read_sql(text("select warehouse_id, sku_id, day_idx + delay_days as arr, qty from supplier_delays"), c)
        dl = dl[(dl["arr"] >= asof_idx) & (dl["arr"] < asof_idx + 14)]
        stores = store_frame(db, as_of)
        reg = stores.groupby(["region", "sku_id"])["avg_daily_demand"].sum()
        wh_region = whs.set_index("warehouse_id")["region"]
        wb["region"] = wb["warehouse_id"].map(wh_region)
        rate_b = reg.rename("r")
        wb["rate_key"] = list(zip(wb["region"], wb["sku_id"]))
        rate_map = {k: v for k, v in rate_b.items()}
        wb["rate"] = wb["rate_key"].map(rate_map).fillna(0.0)
        wb2 = wb.sort_values(["warehouse_id", "sku_id", "expiry_date"]).copy()
        wb2["expiry_date"] = pd.to_datetime(wb2["expiry_date"])
        wb2["days_left"] = (wb2["expiry_date"] - pd.Timestamp(as_of)).dt.days
        wb2["cum"] = wb2.groupby(["warehouse_id", "sku_id"])["qty"].cumsum()
        sell = wb2["rate"] * wb2["days_left"].clip(lower=0)
        wb2["qty_at_risk"] = np.where(wb2["days_left"] < 0, wb2["qty"], np.clip(wb2["cum"] - sell, 0, wb2["qty"])).round().astype(int)
        g = wb2.groupby(["warehouse_id", "sku_id"]).agg(on_hand=("qty", "sum"), qty_expiry_at_risk=("qty_at_risk", "sum"),
                                                        nearest_expiry=("expiry_date", "min"), rate=("rate", "first")).reset_index()
        df = g.merge(ws, how="left", on=["warehouse_id", "sku_id"]).merge(whs, on="warehouse_id").merge(sk, on="sku_id")
        df["reserved"] = np.minimum(df["reserved_qty"].fillna(0), df["on_hand"]).astype(int)
        inc = dl.groupby(["warehouse_id", "sku_id"])["qty"].sum().rename("incoming")
        df = df.merge(inc, how="left", left_on=["warehouse_id", "sku_id"], right_index=True)
        df["incoming"] = df["incoming"].fillna(0).astype(int)
        df["avg_daily_demand"] = df["rate"]
        df["available"] = (df["on_hand"] - df["reserved"]).clip(lower=0)
        r = df["avg_daily_demand"].to_numpy()
        df["days_of_cover"] = np.where(r > 1e-9, df["available"] / np.where(r > 1e-9, r, 1), np.nan)
        df["low_stock"] = df["days_of_cover"] < WH_LOW_DAYS
        df["excess_stock"] = df["days_of_cover"] > WH_EXCESS_DAYS
        df["expiry_risk"] = df["qty_expiry_at_risk"] > 0
        return df
    return _cached(("wh", as_of), build)


def _filter(df: pd.DataFrame, product, region, search, flag, warehouse_id=None, store_id=None) -> pd.DataFrame:
    if product:
        p = str(product).strip()
        m = (df["sku_code"].str.lower() == p.lower()) | (df["category"].str.lower() == p.lower())
        if p.isdigit():
            m |= df["sku_id"] == int(p)
        df = df[m]
    if region:
        df = df[df["region"].str.lower() == region.lower()]
    if warehouse_id is not None and "warehouse_id" in df:
        df = df[df["warehouse_id"] == warehouse_id]
    if store_id is not None and "store_id" in df:
        df = df[df["store_id"] == store_id]
    if search:
        s = search.lower()
        cols = [c for c in ("sku_code", "sku_name", "category", "store", "warehouse", "distributor", "region") if c in df]
        m = np.zeros(len(df), bool)
        for c in cols:
            m |= df[c].astype(str).str.lower().str.contains(s, regex=False).to_numpy()
        df = df[m]
    if flag:
        col = {"low_stock": "low_stock", "excess": "excess_stock", "excess_stock": "excess_stock",
               "expiry_risk": "expiry_risk"}[flag]
        df = df[df[col]]
    return df


def _rowify(df: pd.DataFrame, level: str) -> list[dict]:
    rows = []
    for r in df.itertuples():
        d = r._asdict()
        ne = d.get("nearest_expiry")
        ne = None if ne is None or pd.isna(ne) else pd.Timestamp(ne).date()
        doc = d.get("days_of_cover")
        rows.append(dict(
            key=str(d["key"]), level=level, name=str(d["name"]), region=d.get("region"),
            warehouse=d.get("warehouse"), distributor=d.get("distributor"), store=d.get("store"),
            sku_code=d.get("sku_code"), sku_name=d.get("sku_name"), category=d.get("category"),
            on_hand=int(d["on_hand"]), reserved=int(d["reserved"]), available=int(d["available"]),
            incoming=int(d["incoming"]), avg_daily_demand=round(float(d["avg_daily_demand"]), 3),
            days_of_cover=None if doc is None or pd.isna(doc) else round(float(doc), 1),
            nearest_expiry=ne, qty_expiry_at_risk=int(d["qty_expiry_at_risk"]),
            low_stock=bool(d["low_stock"]), excess_stock=bool(d["excess_stock"]), expiry_risk=bool(d["expiry_risk"]),
            n_series=int(d.get("n_series", 1)), n_low_stock=int(d.get("n_low_stock", 0)),
            n_excess=int(d.get("n_excess", 0)), n_expiry_risk=int(d.get("n_expiry_risk", 0))))
    return rows


def _aggregate(df: pd.DataFrame, by: str, name_col: str, extra: list[str]) -> pd.DataFrame:
    agg = dict(on_hand=("on_hand", "sum"), reserved=("reserved", "sum"), available=("available", "sum"),
               incoming=("incoming", "sum"), avg_daily_demand=("avg_daily_demand", "sum"),
               qty_expiry_at_risk=("qty_expiry_at_risk", "sum"), nearest_expiry=("nearest_expiry", "min"),
               n_series=("on_hand", "size"), n_low_stock=("low_stock", "sum"), n_excess=("excess_stock", "sum"),
               n_expiry_risk=("expiry_risk", "sum"))
    for e in extra:
        agg[e] = (e, "first")
    g = df.groupby(by).agg(**agg).reset_index()
    g["key"] = g[by].astype(str)
    g["name"] = g[name_col] if name_col != by else g[by].astype(str)
    r = g["avg_daily_demand"].to_numpy()
    g["days_of_cover"] = np.where(r > 1e-9, g["available"] / np.where(r > 1e-9, r, 1), np.nan)
    g["low_stock"] = g["n_low_stock"] > 0
    g["excess_stock"] = g["n_excess"] > 0
    g["expiry_risk"] = g["n_expiry_risk"] > 0
    return g


LEVELS = ["store_sku", "store", "sku", "region", "distributor", "warehouse", "warehouse_sku"]


def get_inventory(db: Session, *, level="store_sku", product=None, region=None, as_of: date | None = None,
                  search=None, flag=None, warehouse_id=None, store_id=None, page=1, page_size=50,
                  sort="name") -> dict:
    t = time.time()
    default_asof = asof_date(db)
    as_of = as_of or default_asof
    sdf = store_frame(db, as_of)
    wdf = warehouse_frame(db, as_of)
    s_f = _filter(sdf, product, region, None, None, store_id=store_id)
    w_f = _filter(wdf, product, region, None, None, warehouse_id=warehouse_id)

    if level in ("warehouse", "warehouse_sku"):
        base = _filter(wdf, product, region, search, flag, warehouse_id=warehouse_id)
        if level == "warehouse_sku":
            base = base.assign(key=base["warehouse_id"].astype(str) + "-" + base["sku_id"].astype(str),
                               name=base["warehouse"] + " / " + base["sku_code"])
            out = base
        else:
            out = _aggregate(base, "warehouse_id", "warehouse", ["warehouse", "region"])
    else:
        base = _filter(sdf, product, region, search, flag, store_id=store_id)
        if level == "store_sku":
            out = base.assign(key=base["store_id"].astype(str) + "-" + base["sku_id"].astype(str),
                              name=base["store"] + " / " + base["sku_code"])
        elif level == "store":
            out = _aggregate(base, "store_id", "store", ["store", "region", "distributor"])
        elif level == "sku":
            out = _aggregate(base, "sku_id", "sku_name", ["sku_code", "sku_name", "category"])
        elif level == "region":
            out = _aggregate(base, "region", "region", [])
        elif level == "distributor":
            out = _aggregate(base, "distributor", "distributor", ["region"])
        else:
            raise ValueError(f"unknown level {level}")
    asc = True
    sort_col = sort.lstrip("-")
    if sort.startswith("-"):
        asc = False
    if sort_col not in out.columns:
        sort_col = "name"
    out = out.sort_values(sort_col, ascending=asc, kind="stable")
    total = len(out)
    page_rows = out.iloc[(page - 1) * page_size: page * page_size]
    summary = dict(
        skus=int(s_f["sku_id"].nunique()), warehouses=int(w_f["warehouse_id"].nunique()),
        stores=int(s_f["store_id"].nunique()), series=int(len(s_f)),
        on_hand=int(s_f["on_hand"].sum()), reserved=int(s_f["reserved"].sum()),
        available=int(s_f["available"].sum()), incoming=int(s_f["incoming"].sum()),
        low_stock_series=int(s_f["low_stock"].sum()), excess_series=int(s_f["excess_stock"].sum()),
        expiry_risk_series=int(s_f["expiry_risk"].sum()),
        thresholds=dict(THRESHOLDS, warehouse_on_hand=int(w_f["on_hand"].sum()),
                        warehouse_reserved=int(w_f["reserved"].sum()),
                        warehouse_available=int(w_f["available"].sum()),
                        warehouse_low_stock=int(w_f["low_stock"].sum()),
                        warehouse_excess=int(w_f["excess_stock"].sum()),
                        warehouse_expiry_risk=int(w_f["expiry_risk"].sum()),
                        tier_note="summary counts stores (store-SKU series); warehouse_* keys cover the warehouse tier"))
    return dict(as_of=as_of, level=level, total=total, page=page, page_size=page_size, summary=summary,
                rows=_rowify(page_rows, level), elapsed_ms=round((time.time() - t) * 1000, 1))


def get_batches(db: Session, *, warehouse_id=None, product=None, as_of: date | None = None, only_risk=False,
                page=1, page_size=50) -> dict:
    as_of = as_of or asof_date(db)
    c = db.connection()
    b = pd.read_sql(text(
        "select b.id as batch_id, b.batch_code, w.name as warehouse, b.warehouse_id, k.id as sku_id, k.code as sku_code, "
        "k.name as sku_name, k.category, b.qty, b.received_date, b.expiry_date from warehouse_batches b "
        "join warehouses w on w.id = b.warehouse_id join skus k on k.id = b.sku_id"), c)
    wdf = warehouse_frame(db, as_of)
    rate = wdf.set_index(["warehouse_id", "sku_id"])["avg_daily_demand"]
    br = _at_risk(b, ["warehouse_id", "sku_id"], rate, as_of)
    if warehouse_id:
        br = br[br["warehouse_id"] == warehouse_id]
    if product:
        p = str(product).lower()
        br = br[(br["sku_code"].str.lower() == p) | (br["category"].str.lower() == p) | (br["sku_id"].astype(str) == p)]
    br = br.assign(expiry_risk=br["qty_at_risk"] > 0)
    if only_risk:
        br = br[br["expiry_risk"]]
    br = br.sort_values(["expiry_date", "batch_id"])
    total = len(br)
    sl = br.iloc[(page - 1) * page_size: page * page_size]
    rows = [dict(batch_id=int(r.batch_id), batch_code=r.batch_code, warehouse=r.warehouse, sku_code=r.sku_code,
                 sku_name=r.sku_name, category=r.category, qty=int(r.qty),
                 received_date=pd.Timestamp(r.received_date).date(), expiry_date=pd.Timestamp(r.expiry_date).date(),
                 days_to_expiry=int(r.days_left), expiry_risk=bool(r.expiry_risk), qty_at_risk=int(r.qty_at_risk))
            for r in sl.itertuples()]
    return dict(as_of=as_of, total=total, page=page, page_size=page_size, rows=rows)
