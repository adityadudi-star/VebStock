"""Reproducible simulated-data generator (PRD section 2 / 9).

Everything is driven by an explicit seed and a profile. Settings and cost assumptions are
written to the `meta` table so the UI can display exactly what was used.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import timedelta

import numpy as np
from sqlalchemy import delete, insert
from sqlalchemy.engine import Engine

from app.database import models as m
from app.simulation import demand as dm

REGIONS = ["North", "South", "East", "West", "Central"]
WH_XY = np.array([[750, 1300], [750, 200], [1300, 750], [200, 750], [750, 750]], dtype=float)


@dataclass
class GeneratorConfig:
    profile: str = "dev"
    seed: int = 42
    n_warehouses: int = 5
    n_stores: int = 60
    n_skus: int = 60
    assortment: float = 0.5          # share of SKUs each store stocks
    n_days: int = dm.N_DAYS
    test_days: int = dm.TEST_DAYS
    n_promotions: int = 60
    demand_dispersion_shape: float = 6.0
    start_date: str = dm.START_DATE.isoformat()
    # cost assumptions (all visible in the UI)
    # Calibrated so freight is roughly 1-3% of unit price (typical FMCG distribution), not tuned to KPIs.
    transport_base: float = 0.15           # per unit
    transport_per_km: float = 0.0016       # per unit per km
    lead_time_km_per_day: float = 300.0
    lost_margin_note: str = "pi_s = unit_price x category margin %"
    writeoff_note: str = "eps_s = unit_price x category write-off %"
    warehouse_reserve_share: float = 0.10  # SSW share of on-hand held back
    store_capacity_days: float = 2.0       # Store[j] = days of demand volume per run, x14
    expiry_risk_days: int = 7


PROFILES = {
    "aditya": GeneratorConfig(profile="Aditya", n_stores=60, n_skus=60, assortment=0.5, n_promotions=60),
    "full": GeneratorConfig(profile="Full (PRD scale)", n_stores=400, n_skus=300, assortment=0.12, n_promotions=400),
}
PROFILE_ALIASES = {"dev": "aditya"}   # backwards-compatible CLI name


def get_profile(name: str) -> GeneratorConfig:
    return PROFILES[PROFILE_ALIASES.get(name, name)]


def build(cfg: GeneratorConfig) -> dict:
    rng = np.random.default_rng(cfg.seed)
    nW, nS, nK = cfg.n_warehouses, cfg.n_stores, cfg.n_skus
    start = dm.START_DATE
    t0 = cfg.n_days - cfg.test_days
    asof = start + timedelta(t0)

    # --- warehouses / distributors / stores -------------------------------------------------
    warehouses = [dict(id=i + 1, name=f"WH-{i + 1} {REGIONS[i]}", region=REGIONS[i]) for i in range(nW)]
    distributors = []
    for r in range(nW):
        for k in range(4):
            distributors.append(dict(id=r * 4 + k + 1, name=f"{REGIONS[r]} Distribution {k + 1}", region=REGIONS[r]))
    home = rng.integers(0, nW, size=nS)
    sxy = WH_XY[home] + rng.normal(0, 170, size=(nS, 2))
    dist_all = np.linalg.norm(sxy[:, None, :] - WH_XY[None, :nW, :], axis=2)  # [S, W]
    region_idx = dist_all.argmin(axis=1)
    size_factor = rng.lognormal(0, 0.4, size=nS)
    cluster = np.digitize(size_factor, np.quantile(size_factor, [0.33, 0.66]))  # 0 small .. 2 large
    stores = []
    for j in range(nS):
        r = int(region_idx[j])
        stores.append(dict(id=j + 1, name=f"Store {j + 1:03d}", region=REGIONS[r],
                           distributor_id=r * 4 + int(rng.integers(0, 4)) + 1, cluster=int(cluster[j]),
                           capacity_volume=0.0))

    # --- SKUs ---------------------------------------------------------------------------------
    cat_of = np.sort(rng.integers(0, dm.N_CAT, size=nK)) if False else np.arange(nK) % dm.N_CAT
    skus = []
    sku_pop = rng.lognormal(0, 0.7, size=nK)
    sku_price = np.zeros(nK)
    for k in range(nK):
        name, life, minlife, (plo, phi), margin, wo, vol = dm.CATEGORIES[cat_of[k]]
        price = round(float(rng.uniform(plo, phi)), 2)
        sku_price[k] = price
        skus.append(dict(id=k + 1, code=f"SKU{k + 1:04d}", name=f"{name} item {k // dm.N_CAT + 1}",
                         category=name, unit_volume=round(vol * float(rng.uniform(0.7, 1.3)), 3),
                         unit_price=price, lost_margin=round(price * margin, 2),
                         writeoff_cost=round(price * wo, 2), shelf_life_days=life,
                         min_shelf_life_days=minlife))

    # --- lanes (every warehouse -> every store) ------------------------------------------------
    cost = cfg.transport_base + cfg.transport_per_km * dist_all * rng.uniform(0.9, 1.1, size=dist_all.shape)
    lead = 1 + (dist_all // cfg.lead_time_km_per_day).astype(int)
    rank = cost.argsort(axis=1).argsort(axis=1) + 1

    # --- series (assortment) ------------------------------------------------------------------
    sid, kid = [], []
    for j in range(nS):
        n_k = max(5, int(round(cfg.assortment * nK)))
        chosen = rng.choice(nK, size=min(n_k, nK), replace=False, p=sku_pop / sku_pop.sum())
        sid += [j] * len(chosen)
        kid += sorted(chosen.tolist())
    sid, kid = np.array(sid), np.array(kid)
    base = 2.2 * size_factor[sid] * sku_pop[kid] * rng.lognormal(0, 0.5, size=len(sid))
    base = np.clip(base, 0.3, 40.0)
    growth = rng.normal(0.04, 0.05, size=len(sid))

    # --- promotions ---------------------------------------------------------------------------
    promos = []
    for _ in range(cfg.n_promotions):
        s = int(rng.integers(0, cfg.n_days - 14))
        ln = int(rng.integers(7, 15))
        disc = round(float(rng.uniform(0.10, 0.30)), 2)
        promos.append((int(rng.integers(0, nK)) + 1, int(rng.integers(0, nW)), s, min(s + ln, cfg.n_days - 1),
                       disc, round(1.0 + disc * 3.0, 3)))
    # make sure some promotions fall inside the held-out window
    for _ in range(max(3, cfg.n_promotions // 5)):
        s = int(rng.integers(t0 + 2, cfg.n_days - 10))
        disc = round(float(rng.uniform(0.15, 0.30)), 2)
        promos.append((int(rng.integers(0, nK)) + 1, int(rng.integers(0, nW)), s, min(s + 9, cfg.n_days - 1),
                       disc, round(1.0 + disc * 3.0, 3)))

    ss = dm.SeriesSet(store_id=sid + 1, sku_id=kid + 1, base_rate=base, growth=growth,
                      cat_idx=cat_of[kid], region_idx=region_idx[sid], cluster=cluster[sid],
                      price=sku_price[kid], promos=promos)
    cal = dm.calendar()
    mu = dm.expected_demand(ss, cal)
    sales = dm.realise(mu, cfg.seed + 1, cfg.demand_dispersion_shape)

    # --- inventory at the as-of date (day t0) -------------------------------------------------
    life = np.array([s["shelf_life_days"] for s in skus])
    minlife = np.array([s["min_shelf_life_days"] for s in skus])
    vol = np.array([s["unit_volume"] for s in skus])
    avg28 = sales[:, t0 - 28:t0].mean(axis=1)
    store_stock, store_batches, incoming = [], [], []
    for i in range(ss.n):
        j, k = int(ss.store_id[i]) , int(ss.sku_id[i])
        rate = max(float(avg28[i]), 0.1)
        u = rng.random()
        cover = rng.uniform(0, 2.5) if u < 0.25 else (rng.uniform(25, 55) if u < 0.37 else rng.uniform(3, 14))
        on_hand = int(round(rate * cover))
        reserved = int(on_hand * rng.uniform(0, 0.12))
        inc, inc_exp = 0, None
        if rng.random() < 0.18:
            inc = int(max(1, round(rate * rng.uniform(3, 7))))
            delay = int(rng.integers(2, 6)) if rng.random() < 0.2 else 0
            eta = asof + timedelta(int(rng.integers(1, 5)) + delay)
            exp = asof + timedelta(int(0.85 * life[k - 1]))
            incoming.append(dict(store_id=j, sku_id=k, qty=inc, expiry_date=exp, eta_date=eta,
                                 delay_days=delay, status="delayed" if delay else "in_transit"))
        near, qnear, parts = None, 0, 0
        if on_hand > 0:
            parts = 2 if on_hand > 6 and rng.random() < 0.5 else 1
            split = [on_hand] if parts == 1 else [int(on_hand * 0.4), on_hand - int(on_hand * 0.4)]
            for q in split:
                if q <= 0:
                    continue
                rem = int(rng.uniform(1, 0.8 * life[k - 1])) if rng.random() < 0.85 else int(rng.integers(1, 6))
                exp = asof + timedelta(rem)
                store_batches.append(dict(store_id=j, sku_id=k, qty=q, expiry_date=exp))
                near = exp if near is None or exp < near else near
        store_stock.append(dict(store_id=j, sku_id=k, on_hand=on_hand, reserved=reserved, incoming=inc,
                                nearest_expiry=near, qty_near_expiry=0, avg_daily_demand=round(rate, 4)))

    # --- warehouse batches --------------------------------------------------------------------
    wh_week = np.zeros((nW, nK))
    for w in range(nW):
        sel = region_idx[sid] == w
        np.add.at(wh_week[w], kid[sel], base[sel] * 7)
    wh_batches, wh_sku = [], []
    code = 0
    for w in range(nW):
        for k in range(nK):
            weekly = max(wh_week[w, k], 3.0)
            total = int(weekly * rng.uniform(3.0, 6.0))
            wh_sku.append(dict(warehouse_id=w + 1, sku_id=k + 1, reserved_qty=int(total * cfg.warehouse_reserve_share)))
            nb = int(rng.integers(2, 4))
            wts = rng.dirichlet(np.ones(nb))
            for b in range(nb):
                q = int(total * wts[b])
                if q <= 0:
                    continue
                rem = int(rng.uniform(minlife[k] + 2, 0.9 * life[k]))
                exp = asof + timedelta(rem)
                recv = exp - timedelta(int(life[k] + rng.normal(0, 0.12 * life[k])))
                code += 1
                wh_batches.append(dict(warehouse_id=w + 1, sku_id=k + 1, batch_code=f"B{code:06d}", qty=q,
                                       received_date=recv, expiry_date=exp))
    # supplier inbound schedule inside the test window (+ some history), with delays
    delays = []
    for w in range(nW):
        for k in range(nK):
            weekly = max(wh_week[w, k], 3.0)
            for d in range(t0 + 3, cfg.n_days, 7):
                dl = int(rng.integers(2, 8)) if rng.random() < 0.15 else 0
                delays.append(dict(warehouse_id=w + 1, sku_id=k + 1, day_idx=d, delay_days=dl,
                                   qty=int(weekly * rng.uniform(0.8, 1.1))))
    for _ in range(200):
        delays.append(dict(warehouse_id=int(rng.integers(1, nW + 1)), sku_id=int(rng.integers(1, nK + 1)),
                           day_idx=int(rng.integers(0, t0)), delay_days=int(rng.integers(1, 8)),
                           qty=int(rng.integers(20, 200))))

    # --- capacities (per planning run, volume units) ------------------------------------------
    vol_rate = np.zeros(nS)
    np.add.at(vol_rate, sid, base * vol[kid])
    for j in range(nS):
        stores[j]["capacity_volume"] = round(float(vol_rate[j] * 14 * cfg.store_capacity_days), 1)
    lanes = []
    for j in range(nS):
        for w in range(nW):
            r = int(rank[j, w])
            cap = stores[j]["capacity_volume"] * (1.0 if r == 1 else 0.7)
            lanes.append(dict(warehouse_id=w + 1, store_id=j + 1, cost_per_unit=round(float(cost[j, w]), 3),
                              lead_time_days=int(lead[j, w]), capacity_volume=round(cap, 1), cost_rank=r))

    return dict(cfg=cfg, warehouses=warehouses, distributors=distributors, stores=stores, skus=skus, lanes=lanes,
                wh_sku=wh_sku, wh_batches=wh_batches, store_stock=store_stock, store_batches=store_batches,
                incoming=incoming, delays=delays, ss=ss, sales=sales, asof=asof, t0=t0,
                promos=promos, mu=mu)


def _bulk(conn, table, rows, chunk=20000):
    for i in range(0, len(rows), chunk):
        conn.execute(insert(table), rows[i:i + chunk])


def load(world: dict, engine: Engine) -> dict:
    cfg: GeneratorConfig = world["cfg"]
    t = time.time()
    with engine.begin() as conn:
        for tbl in reversed(m.Base.metadata.sorted_tables):
            conn.execute(delete(tbl))
        _bulk(conn, m.Warehouse, world["warehouses"])
        _bulk(conn, m.Distributor, world["distributors"])
        _bulk(conn, m.Store, world["stores"])
        _bulk(conn, m.Sku, world["skus"])
        _bulk(conn, m.Lane, world["lanes"])
        _bulk(conn, m.WarehouseSku, world["wh_sku"])
        _bulk(conn, m.WarehouseBatch, world["wh_batches"])
        _bulk(conn, m.StoreStock, world["store_stock"])
        _bulk(conn, m.StoreBatch, world["store_batches"])
        _bulk(conn, m.IncomingShipment, world["incoming"])
        _bulk(conn, m.SupplierDelay, world["delays"])
        ss: dm.SeriesSet = world["ss"]
        _bulk(conn, m.SeriesParam, [dict(store_id=int(a), sku_id=int(b), base_rate=float(c), growth=float(d))
                                    for a, b, c, d in zip(ss.store_id, ss.sku_id, ss.base_rate, ss.growth)])
        _bulk(conn, m.Promotion, [dict(sku_id=p[0], region=REGIONS[p[1]], start_idx=p[2], end_idx=p[3],
                                       discount=p[4], uplift=p[5]) for p in world["promos"]])
        r, c = np.nonzero(world["sales"])
        q = world["sales"][r, c]
        sid, kid = ss.store_id[r], ss.sku_id[r]
        for i in range(0, len(r), 100000):
            sl = slice(i, i + 100000)
            _bulk(conn, m.SalesDaily, [dict(store_id=int(a), sku_id=int(b), day_idx=int(d), qty=int(v))
                                       for a, b, d, v in zip(sid[sl], kid[sl], c[sl], q[sl])], chunk=50000)
        meta = {
            "generator_settings": asdict(cfg),
            "as_of": {"date": world["asof"].isoformat(), "day_idx": world["t0"]},
            "festivals": [{"date": d.isoformat(), "name": {1: "Holi", 2: "Eid", 3: "Diwali"}[f]} for d, f in dm.FESTIVALS],
            "categories": [dict(name=c[0], shelf_life_days=c[1], min_remaining_shelf_life_days=c[2],
                                margin_pct=c[4], writeoff_pct_of_price=c[5]) for c in dm.CATEGORIES],
            "counts": {"warehouses": cfg.n_warehouses, "stores": cfg.n_stores, "skus": cfg.n_skus,
                       "series": int(ss.n), "sales_rows": int(len(r))},
            "notes": ["Sales are simulated (gamma-Poisson around a seeded expected-demand model).",
                      "Only non-zero daily sales are stored; zeros are implied.",
                      "The system 'today' is the first day of the 90-day held-out window."],
        }
        _bulk(conn, m.Meta, [dict(key=k, value=v) for k, v in meta.items()])
    return {"seconds": round(time.time() - t, 1), "series": int(ss.n), "sales_rows": int(len(r))}
