"""Day-by-day replay of the baseline reorder-point policy and the optimised (LP) policy on identical
held-out demand (PRD section 9).

KPI definitions (all measured, never hard-coded):
  stockout rate   = store-SKU-days with zero on-hand at the start of the selling day / all store-SKU-days
  fill rate       = units sold / units demanded
  transport cost  = sum(units shipped x lane cost per unit)
  expiry wastage  = units expired (stores + warehouses) / units available (opening stock + inbound)
  weekly MAPE     = rolling-origin weekly forecast error on the same window (per seed)
  plan time       = mean wall-clock seconds of one LP solve (optimised policy only)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.forecasting import model as fm
from app.optimization.model import solve
from app.optimization.types import PlanInputs
from app.optimization.validator import validate_plan
from app.services.inputs import horizon_demand
from app.simulation import demand as dm
from app.simulation.world import World

K = 100  # store expiry buckets; anything >= K-1 days away cannot expire inside a 90-day window


@dataclass
class ReplayConfig:
    plan_every_days: int = 1              # PRD J1: a daily plan
    plan_horizon: int = 7
    alpha: float = 0.7
    baseline_safety_days: float = 2.0     # fixed safety margin = 2 days of average demand
    baseline_review_days: int = 7         # order-up-to = ROP + 7 days of demand
    solver_time_limit: float = 8.0
    demand_shape: float = 6.0


@dataclass
class State:
    B: np.ndarray                      # [S, K] store stock by remaining days
    pending: np.ndarray                # [S] units in transit
    transit: dict                      # day -> list[(series_idx, bucket, qty)]
    wb_qty: np.ndarray
    wb_wh: np.ndarray
    wb_sku: np.ndarray
    wb_exp: np.ndarray                 # absolute day index
    wb_recv: np.ndarray
    pools: dict                        # (wh, sku) -> np.ndarray of batch idx
    reserved: dict                     # (wh, sku) -> units
    inbound: dict                      # day -> list[(batch_idx, qty)]
    opening_units: float = 0.0
    inbound_units: float = 0.0


def load_state(engine: Engine, world: World) -> State:
    t0 = world.t0
    asof = world.asof
    with engine.connect() as c:
        sb = pd.read_sql(text("select store_id, sku_id, qty, expiry_date from store_batches"), c)
        inc = pd.read_sql(text("select store_id, sku_id, qty, expiry_date, eta_date from incoming_shipments"), c)
        wb = pd.read_sql(text("select id, warehouse_id, sku_id, qty, received_date, expiry_date from warehouse_batches order by id"), c)
        ws = pd.read_sql(text("select warehouse_id, sku_id, reserved_qty from warehouse_sku"), c)
        dl = pd.read_sql(text("select warehouse_id, sku_id, day_idx, delay_days, qty from supplier_delays where day_idx >= :t"), c, params={"t": t0})
    S = world.ss.n
    B = np.zeros((S, K), dtype=np.float32)
    day = lambda s: np.array([(d - asof).days for d in pd.to_datetime(s).dt.date], dtype=int)  # noqa: E731
    if len(sb):
        idx = world.index_of(sb["store_id"].to_numpy(), sb["sku_id"].to_numpy())
        rem = np.clip(day(sb["expiry_date"]), 0, K - 1)
        np.add.at(B, (idx, rem), sb["qty"].to_numpy().astype(np.float32))
    transit: dict = {}
    pending = np.zeros(S)
    if len(inc):
        idx = world.index_of(inc["store_id"].to_numpy(), inc["sku_id"].to_numpy())
        eta = day(inc["eta_date"])
        exp = day(inc["expiry_date"])
        for i, e, x, q in zip(idx, eta, exp, inc["qty"]):
            transit.setdefault(t0 + int(e), []).append((int(i), int(min(max(x - e, 0), K - 1)), float(q)))
            pending[i] += q
    n_init = len(wb)
    life = world.skus.set_index("id")["shelf_life_days"]
    extra = []
    inbound: dict = {}
    for r in dl.itertuples():
        arr = r.day_idx + r.delay_days
        if arr >= dm.N_DAYS:
            continue
        extra.append((r.warehouse_id, r.sku_id, arr, int(0.85 * life.loc[r.sku_id]), r.qty))
    n_tot = n_init + len(extra)
    wb_qty = np.zeros(n_tot)
    wb_wh = np.zeros(n_tot, dtype=int)
    wb_sku = np.zeros(n_tot, dtype=int)
    wb_exp = np.zeros(n_tot, dtype=int)
    wb_recv = np.zeros(n_tot, dtype=int)
    wb_qty[:n_init] = wb["qty"].to_numpy()
    wb_wh[:n_init] = wb["warehouse_id"].to_numpy()
    wb_sku[:n_init] = wb["sku_id"].to_numpy()
    wb_exp[:n_init] = t0 + day(wb["expiry_date"])
    wb_recv[:n_init] = t0 + day(wb["received_date"])
    inbound_units = 0.0
    for k, (w, s, arr, lf, q) in enumerate(extra):
        i = n_init + k
        wb_wh[i], wb_sku[i], wb_exp[i], wb_recv[i] = w, s, arr + lf, arr
        inbound.setdefault(int(arr), []).append((i, float(q)))
        inbound_units += q
    pools = {}
    keys = wb_wh.astype(np.int64) * 100000 + wb_sku
    order = np.argsort(keys, kind="stable")
    for k in np.unique(keys):
        lo, hi = np.searchsorted(keys[order], k, "left"), np.searchsorted(keys[order], k, "right")
        pools[(int(k // 100000), int(k % 100000))] = order[lo:hi]
    reserved = {(int(a), int(b)): int(c) for a, b, c in zip(ws["warehouse_id"], ws["sku_id"], ws["reserved_qty"])}
    return State(B=B, pending=pending, transit=transit, wb_qty=wb_qty, wb_wh=wb_wh, wb_sku=wb_sku, wb_exp=wb_exp,
                 wb_recv=wb_recv, pools=pools, reserved=reserved, inbound=inbound,
                 opening_units=float(B.sum() + wb_qty[:n_init].sum()), inbound_units=inbound_units)


def _copy(st: State) -> State:
    return State(B=st.B.copy(), pending=st.pending.copy(), transit={k: list(v) for k, v in st.transit.items()},
                 wb_qty=st.wb_qty.copy(), wb_wh=st.wb_wh, wb_sku=st.wb_sku, wb_exp=st.wb_exp, wb_recv=st.wb_recv,
                 pools=st.pools, reserved=st.reserved, inbound={k: list(v) for k, v in st.inbound.items()},
                 opening_units=st.opening_units, inbound_units=st.inbound_units)


def _ship(st: State, day: int, ser: int, b: int, qty: float, lead: int):
    """Move qty from warehouse batch b toward store series `ser`; returns nothing (state mutated)."""
    st.wb_qty[b] -= qty
    arr = day + lead
    bucket = int(min(st.wb_exp[b] - arr, K - 1))
    st.transit.setdefault(arr, []).append((ser, bucket, float(qty)))
    st.pending[ser] += qty


def run_policy(world: World, st0: State, demand: np.ndarray, sales_seed: np.ndarray, policy: str, cfg: ReplayConfig,
               models: fm.ForecastModels | None, prep: fm.Prepared, engine_data: dict) -> dict:
    st = _copy(st0)
    t0, S = world.t0, world.ss.n
    ndays = demand.shape[1]
    lane_by_store = engine_data["lane_best"]       # series -> (wh, cost, lead) cheapest
    sku_wo = engine_data["sku_writeoff"]
    ss = world.ss
    lead_s, cost_s, wh_s = lane_by_store["lead"], lane_by_store["cost"], lane_by_store["wh"]
    tot = dict(recv=0.0, demand=0.0, sold=0.0, stockout_days=0, transport=0.0, shipped=0.0, exp_store=0.0, exp_wh=0.0,
               exp_value=0.0, plan_seconds=[], violations=0, lines=0, lines_with_reason=0, plans=0,
               plan_status=[])
    for k in range(ndays):
        d = t0 + k
        # 1. arrivals at stores / warehouse inbound
        for ser, bucket, q in st.transit.pop(d, []):
            tot["recv"] += q
            if bucket < 0:
                tot["exp_store"] += q
                tot["exp_value"] += q * sku_wo[ser]
            else:
                st.B[ser, bucket] += q
            st.pending[ser] -= q
        for b, q in st.inbound.pop(d, []):
            st.wb_qty[b] += q
        # 2. policy action
        if policy == "baseline":
            _baseline_orders(world, st, sales_seed, d, cfg, lead_s, cost_s, wh_s, tot)
        elif k % cfg.plan_every_days == 0:
            _optimised_plan(world, st, sales_seed, d, cfg, models, prep, engine_data, tot)
        # 3. selling day
        onhand = st.B.sum(1)
        tot["stockout_days"] += int((onhand <= 0).sum())
        dem = demand[:, k].astype(np.float32)
        cs = np.cumsum(st.B, axis=1)
        sold = np.minimum(dem, cs[:, -1])
        take = np.clip(sold[:, None] - (cs - st.B), 0, st.B)
        st.B -= take
        tot["demand"] += float(dem.sum())
        tot["sold"] += float(sold.sum())
        # 4. end-of-day expiry
        exp0 = st.B[:, 0].copy()
        tot["exp_store"] += float(exp0.sum())
        tot["exp_value"] += float((exp0 * sku_wo).sum())
        st.B[:, :-1] = st.B[:, 1:]
        st.B[:, -1] = 0
        mask = (st.wb_exp == d) & (st.wb_qty > 0)
        if mask.any():
            w = float(st.wb_qty[mask].sum())
            tot["exp_wh"] += w
            tot["exp_value"] += float((st.wb_qty[mask] * engine_data["sku_writeoff_by_id"][st.wb_sku[mask]]).sum())
            st.wb_qty[mask] = 0
    # leftover in-transit units that never arrived inside the window are not counted as received
    expired_total = tot["exp_store"] + tot["exp_wh"]
    avail = st0.opening_units + st0.inbound_units
    return dict(
        stockout_rate=100.0 * tot["stockout_days"] / (S * ndays),
        fill_rate=100.0 * tot["sold"] / max(tot["demand"], 1.0),
        transport_cost=tot["transport"],
        # PRD definition: units expired at stores / units received at stores (opening store stock included)
        expiry_wastage_pct=100.0 * tot["exp_store"] / max(tot["recv"] + st0.B.sum(), 1.0),
        expiry_wastage_total_pct=100.0 * expired_total / max(avail, 1.0),
        expiry_wastage_warehouse_pct=100.0 * tot["exp_wh"] / max(float(st0.wb_qty.sum() + st0.inbound_units), 1.0),
        units_received_stores=tot["recv"],
        expired_units=expired_total, expired_units_store=tot["exp_store"], expired_units_warehouse=tot["exp_wh"],
        expiry_value=tot["exp_value"], units_shipped=tot["shipped"], units_demanded=tot["demand"],
        units_sold=tot["sold"], units_available=avail,
        plan_seconds_mean=float(np.mean(tot["plan_seconds"])) if tot["plan_seconds"] else 0.0,
        plan_seconds_max=float(np.max(tot["plan_seconds"])) if tot["plan_seconds"] else 0.0,
        plans=tot["plans"], constraint_violations=tot["violations"],
        explanation_coverage_pct=(100.0 * tot["lines_with_reason"] / tot["lines"]) if tot["lines"] else None,
        shipment_lines=tot["lines"], solver_statuses=sorted(set(tot["plan_status"])))


def _baseline_orders(world, st, sales_seed, d, cfg, lead_s, cost_s, wh_s, tot):
    avg = sales_seed[:, max(0, d - 28):d].mean(1)
    LT = lead_s.astype(float)
    margin = cfg.baseline_safety_days * avg
    rop = avg * LT + margin
    pos = st.B.sum(1) + st.pending
    trig = (avg > 0) & (pos <= rop)
    if not trig.any():
        return
    order = np.ceil(avg * (LT + cfg.baseline_review_days) + margin - pos)
    idx = np.where(trig & (order >= 1))[0]
    if len(idx) == 0:
        return
    skus = world.ss.sku_id[idx]
    keys = wh_s[idx].astype(np.int64) * 100000 + skus
    for k in np.unique(keys):
        sel = idx[keys == k]
        wh, sku = int(k // 100000), int(k % 100000)
        pool = st.pools.get((wh, sku))
        if pool is None:
            continue
        ok = pool[(st.wb_qty[pool] > 0) & (st.wb_exp[pool] >= d)]
        if len(ok) == 0:
            continue
        total = st.wb_qty[ok].sum()
        avail = max(0.0, total - st.reserved.get((wh, sku), 0))
        req = order[sel]
        frac = min(1.0, avail / max(req.sum(), 1.0))
        alloc = np.floor(req * frac)
        ok = ok[np.argsort(st.wb_recv[ok], kind="stable")]   # FIFO by received date
        for ser, q in zip(sel, alloc):
            q = int(q)
            while q > 0 and len(ok):
                b = ok[0]
                t = min(q, int(st.wb_qty[b]))
                if t <= 0:
                    ok = ok[1:]
                    continue
                _ship(st, d, int(ser), int(b), t, int(lead_s[ser]))
                tot["transport"] += t * cost_s[ser]
                tot["shipped"] += t
                q -= t
                if st.wb_qty[b] <= 0:
                    ok = ok[1:]


def _optimised_plan(world, st, sales_seed, d, cfg, models, prep, ed, tot):
    ss = world.ss
    S = ss.n
    H = cfg.plan_horizon
    p10, p50, p90 = {}, {}, {}
    for h in fm.HORIZONS:
        q = models.predict(fm.build_features(world, prep, sales_seed, d, h), h)
        p10[h], p50[h], p90[h] = q[:, 0], q[:, 1], q[:, 2]
    DH = horizon_demand(p50, H)
    lt = ed["lane_best"]["lead"].astype(float)
    SS = fm.safety_stock(p50[7], p90[7], 7, lt)
    on = st.B.sum(1).astype(float)
    # confirmed incoming that lands inside the horizon
    R = np.zeros(S)
    for day_, items in st.transit.items():
        if day_ - d <= H:
            for ser, _b, q in items:
                R[ser] += q
    live = np.where(st.wb_qty > 0)[0]
    live = live[st.wb_exp[live] >= d]
    batches = pd.DataFrame(dict(id=live, wh_id=st.wb_wh[live], sku_id=st.wb_sku[live],
                                qty=st.wb_qty[live].astype(int), exp_days=(st.wb_exp[live] - d)))
    batches = batches[batches["qty"] > 0]
    inp = PlanInputs(horizon=H, store_id=ss.store_id, sku_id=ss.sku_id, I=on, R=R, DH=DH, SS=SS, rate=DH / H,
                     p10h=horizon_demand(p10, H), p90h=horizon_demand(p90, H), lanes=ed["lanes_top3"],
                     batches=batches, wh_reserved=st.reserved, store_cap=ed["store_cap"], skus=ed["skus_df"],
                     alpha_by_category={}, default_alpha=cfg.alpha, store_names={}, wh_names={})
    res = solve(inp, time_limit=cfg.solver_time_limit)
    val = validate_plan(inp, res.lines, res.series)
    tot["plan_seconds"].append(res.solve_seconds)
    tot["violations"] += val["n_violations"]
    tot["plans"] += 1
    tot["plan_status"].append(res.solver_status)
    tot["lines"] += len(res.lines)
    tot["lines_with_reason"] += int(res.lines["reason"].astype(bool).sum()) if len(res.lines) else 0
    for r in res.lines.itertuples():
        _ship(st, d, int(r.series_idx), int(r.batch_id), int(r.qty), int(r.lead))
        tot["transport"] += r.qty * r.cost_per_unit
        tot["shipped"] += r.qty


def engine_data_from_world(world: World) -> dict:
    lanes = world.lanes.rename(columns={"warehouse_id": "wh_id", "cost_per_unit": "cost", "lead_time_days": "lead",
                                        "capacity_volume": "cap", "cost_rank": "rank"})
    top3 = lanes[lanes["rank"] <= 3][["wh_id", "store_id", "cost", "lead", "cap", "rank"]].copy()
    best = lanes[lanes["rank"] == 1].set_index("store_id")
    sid = world.ss.store_id
    skus = world.skus.set_index("id")
    wo_by_id = np.zeros(skus.index.max() + 1)
    wo_by_id[skus.index.to_numpy()] = skus["writeoff_cost"].to_numpy()
    return dict(
        lanes_top3=top3,
        lane_best=dict(wh=best.loc[sid, "wh_id"].to_numpy(), cost=best.loc[sid, "cost"].to_numpy(),
                       lead=best.loc[sid, "lead"].to_numpy()),
        store_cap=world.stores.set_index("id")["capacity_volume"].to_dict(),
        skus_df=skus[["lost_margin", "writeoff_cost", "unit_volume", "min_shelf_life_days", "category", "name"]],
        sku_writeoff=wo_by_id[world.ss.sku_id], sku_writeoff_by_id=wo_by_id)


KPI_KEYS = ["stockout_rate", "fill_rate", "transport_cost", "expiry_wastage_pct", "weekly_mape", "plan_seconds_mean",
            "expiry_wastage_warehouse_pct", "expiry_wastage_total_pct"]


def run_comparison(engine: Engine, world: World, seeds: list[int], cfg: ReplayConfig | None = None,
                   models: fm.ForecastModels | None = None, progress=print) -> dict:
    cfg = cfg or ReplayConfig()
    prep = fm.prepare(world)
    models = models or fm.train(world, prep, world.sales, world.t0, "fast")
    st0 = load_state(engine, world)
    ed = engine_data_from_world(world)
    mu = dm.expected_demand(world.ss, world.cal)
    per_seed = []
    for sd in seeds:
        t = time.time()
        real = dm.realise(mu[:, world.t0:], sd, world.settings.get("demand_dispersion_shape", 6.0))
        sales_seed = world.sales.copy()
        sales_seed[:, world.t0:] = real
        mape = fm.evaluate_rolling(world, prep, sales_seed, base_models=models)
        row = {"seed": sd, "weekly_mape": mape["mape_mean"], "wape": mape["wape"]}
        for pol in ("baseline", "optimized"):
            r = run_policy(world, st0, real, sales_seed, pol, cfg, models, prep, ed)
            r["weekly_mape"] = mape["mape_mean"]
            row[pol] = r
        per_seed.append(row)
        progress(f"seed {sd}: baseline fill {row['baseline']['fill_rate']:.2f}% / optimized {row['optimized']['fill_rate']:.2f}% "
                 f"({time.time() - t:.0f}s)")
    return summarise(per_seed, cfg, world)


def summarise(per_seed: list[dict], cfg: ReplayConfig, world: World) -> dict:
    kpis = {}
    for key in KPI_KEYS:
        entry = {}
        for pol in ("baseline", "optimized"):
            vals = [r[pol].get(key) if key != "weekly_mape" else r["weekly_mape"] for r in per_seed]
            vals = [v for v in vals if v is not None]
            entry[pol] = dict(mean=float(np.mean(vals)), min=float(np.min(vals)), max=float(np.max(vals)), values=vals)
        b, o = entry["baseline"]["mean"], entry["optimized"]["mean"]
        entry["abs_diff"] = o - b
        entry["rel_diff_pct"] = (100.0 * (o - b) / b) if abs(b) > 1e-9 else None
        kpis[key] = entry
    extra = {}
    for key in ("constraint_violations", "explanation_coverage_pct", "plans", "units_shipped", "expired_units",
                "expiry_value", "plan_seconds_max"):
        extra[key] = {pol: [r[pol].get(key) for r in per_seed] for pol in ("baseline", "optimized")}
    return dict(kpis=kpis, extra=extra, per_seed=per_seed, seeds=[r["seed"] for r in per_seed],
                config=dict(cfg.__dict__), window_days=dm.TEST_DAYS, as_of=world.asof.isoformat(),
                data_profile=world.settings.get("profile"),
                label="SIMULATED replay on simulated data; targets are goals, not guarantees")
