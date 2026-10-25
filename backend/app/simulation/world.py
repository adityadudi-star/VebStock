"""Load the stored dataset from the database into numpy structures (offline jobs only).

API request handlers never call this: they query small, pre-computed tables instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.simulation import demand as dm

REGIONS = ["North", "South", "East", "West", "Central"]


@dataclass
class World:
    ss: dm.SeriesSet
    sales: np.ndarray              # int16 [S, D] stored realisation
    cal: dict
    skus: pd.DataFrame
    stores: pd.DataFrame
    lanes: pd.DataFrame
    asof: date
    t0: int
    settings: dict
    sku_cat_idx: np.ndarray        # per sku_id (index sku_id-1)

    def series_key(self) -> np.ndarray:
        return self.ss.store_id.astype(np.int64) * 4096 + self.ss.sku_id

    def index_of(self, store_id, sku_id) -> np.ndarray:
        key = self.series_key()
        q = np.asarray(store_id, dtype=np.int64) * 4096 + np.asarray(sku_id)
        order = np.argsort(key)
        pos = np.searchsorted(key[order], q)
        pos = np.clip(pos, 0, len(key) - 1)
        ok = key[order][pos] == q
        return np.where(ok, order[pos], -1)


def load_world(engine: Engine) -> World:
    with engine.connect() as c:
        meta = {r[0]: r[1] for r in c.execute(text("select key, value from meta"))}
        import json
        meta = {k: (json.loads(v) if isinstance(v, str) else v) for k, v in meta.items()}
        series = pd.read_sql("select * from series order by store_id, sku_id", c)
        skus = pd.read_sql("select * from skus order by id", c)
        stores = pd.read_sql("select * from stores order by id", c)
        lanes = pd.read_sql("select * from lanes", c)
        promos = pd.read_sql("select * from promotions", c)
        sales_rows = pd.read_sql("select store_id, sku_id, day_idx, qty from sales_daily", c)
    cat_names = [x[0] for x in dm.CATEGORIES]
    sku_cat = skus["category"].map({n: i for i, n in enumerate(cat_names)}).to_numpy()
    store_region = stores.set_index("id")["region"].map({n: i for i, n in enumerate(REGIONS)})
    store_cluster = stores.set_index("id")["cluster"]
    promo_list = [(int(r.sku_id), REGIONS.index(r.region), int(r.start_idx), int(r.end_idx), float(r.discount),
                   float(r.uplift)) for r in promos.itertuples()]
    sid = series["store_id"].to_numpy()
    kid = series["sku_id"].to_numpy()
    ss = dm.SeriesSet(store_id=sid, sku_id=kid, base_rate=series["base_rate"].to_numpy(),
                      growth=series["growth"].to_numpy(), cat_idx=sku_cat[kid - 1],
                      region_idx=store_region.loc[sid].to_numpy(), cluster=store_cluster.loc[sid].to_numpy(),
                      price=skus["unit_price"].to_numpy()[kid - 1], promos=promo_list)
    w = World(ss=ss, sales=np.zeros((ss.n, dm.N_DAYS), dtype=np.int16), cal=dm.calendar(), skus=skus,
              stores=stores, lanes=lanes, asof=date.fromisoformat(meta["as_of"]["date"]),
              t0=int(meta["as_of"]["day_idx"]), settings=meta["generator_settings"], sku_cat_idx=sku_cat)
    idx = w.index_of(sales_rows["store_id"].to_numpy(), sales_rows["sku_id"].to_numpy())
    w.sales[idx, sales_rows["day_idx"].to_numpy()] = sales_rows["qty"].to_numpy().astype(np.int16)
    return w
