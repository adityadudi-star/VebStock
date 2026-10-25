"""PuLP/CBC allocation LP with FEFO (PRD 7.1).

    min  sum (c_ij + delta*r_b) x[s,i,b,j] + alpha*sum pi_s u[s,j] + (1-alpha)*sum eps_s w[s,j]

Supply, batch, lane/store capacity, demand+SS, expiry and shelf-life constraints are modelled as in
the PRD. Scale controls: only series with a coverage deficit get variables, only the 3 cheapest
eligible lanes per store are candidates, and large problems are solved per home-warehouse group
(sequentially, passing remaining supply forward). The LP is continuous; the solution is rounded to
integers with a supply-preserving rounding + capacity repair + FEFO re-assignment. Everything that
changed vs. the LP optimum is reported in `notes`.
"""
from __future__ import annotations

import time
from collections import defaultdict

import numpy as np
import pandas as pd
import pulp

from app.optimization.explain import explain_lines
from app.optimization.types import PlanInputs, PlanResult

DELTA = 0.01          # FEFO tie-break per rank step (currency / unit)
EPS = 1e-6
MAX_VARS_SINGLE_SOLVE = 60000


def _pools(inp: PlanInputs) -> dict:
    pools: dict = defaultdict(list)
    b = inp.batches
    for bid, wh, sku, qty, exp in zip(b["id"], b["wh_id"], b["sku_id"], b["qty"], b["exp_days"]):
        pools[(int(wh), int(sku))].append([int(bid), int(qty), int(exp)])
    for k in pools:
        pools[k].sort(key=lambda r: (r[2], r[0]))
    return pools


def _lanes_by_store(inp: PlanInputs) -> dict:
    out: dict = defaultdict(list)
    for r in inp.lanes.sort_values(["store_id", "cost"]).itertuples():
        lead = int(r.lead) + int(inp.extra_lead.get(int(r.wh_id), 0))
        out[int(r.store_id)].append(dict(wh=int(r.wh_id), cost=float(r.cost), lead=lead, cap=float(r.cap), rank=int(r.rank)))
    return out


def life_window(inp: PlanInputs, pools, lanes_by_store, i: int, sku_params: dict) -> float:
    """Average sellable days left after arrival over eligible candidate batches (used for D_L)."""
    j, s = int(inp.store_id[i]), int(inp.sku_id[i])
    m = sku_params[s]["min_shelf_life_days"]
    vals, w_ = [], []
    anyb = []
    for ln in lanes_by_store.get(j, []):
        for bid, qty, exp in pools.get((ln["wh"], s), []):
            rem = exp - ln["lead"]
            anyb.append(rem)
            if rem >= m and qty > 0:
                vals.append(rem)
                w_.append(qty)
    if vals:
        return float(np.average(vals, weights=w_))
    if anyb:
        return float(max(np.mean(anyb), 1.0))
    return 30.0


def series_context(inp: PlanInputs):
    """(DL, alpha) per series - same definitions the solver uses; needed to re-score edited plans."""
    sku_params = inp.skus.to_dict("index")
    pools = _pools(inp)
    lbs = _lanes_by_store(inp)
    DL = np.array([inp.rate[i] * min(max(life_window(inp, pools, lbs, i, sku_params), 1.0), 90.0)
                   for i in range(inp.n)])
    alpha = np.array([inp.alpha_for_sku(int(s)) for s in inp.sku_id])
    return DL, alpha


def solve(inp: PlanInputs, time_limit: float = 8.0, by_group: bool | None = None) -> PlanResult:
    t_start = time.time()
    sku_params = inp.skus.to_dict("index")
    pools = _pools(inp)
    lanes_by_store = _lanes_by_store(inp)

    avail = {}
    for key, rows in pools.items():
        tot = sum(r[1] for r in rows)
        avail[key] = max(0, tot - int(inp.wh_reserved.get(key, 0)))
    batch_rem = {r[0]: r[1] for rows in pools.values() for r in rows}
    batch_meta = {r[0]: (key[0], key[1], r[2]) for key, rows in pools.items() for r in rows}
    batch_rank = {}
    for key, rows in pools.items():
        for rk, r in enumerate(rows):
            batch_rank[r[0]] = rk

    deficit = inp.DH + inp.SS - inp.I - inp.R
    DL = np.array([inp.rate[i] * min(max(life_window(inp, pools, lanes_by_store, i, sku_params), 1.0), 90.0)
                   for i in range(inp.n)])
    alpha = np.array([inp.alpha_for_sku(int(s)) for s in inp.sku_id])
    need = np.where(deficit > EPS)[0]

    # ---- group stores by home (cheapest open) warehouse -----------------------------------
    def home(i):
        ls = lanes_by_store.get(int(inp.store_id[i]), [])
        return ls[0]["wh"] if ls else -1

    groups: dict = defaultdict(list)
    est_vars = 0
    for i in need:
        groups[home(int(i))].append(int(i))
        est_vars += 9
    if by_group is None:
        by_group = est_vars > MAX_VARS_SINGLE_SOLVE
    glist = list(groups.values()) if by_group else [list(need)]

    xs = []   # (series_i, wh, bid, store, value)
    lp_obj = 0.0
    statuses = []
    n_vars_total = 0
    # remaining capacity trackers (lane and store) shared across groups
    lane_used: dict = defaultdict(float)
    store_used: dict = defaultdict(float)

    for gi, grp in enumerate(glist):
        # Terms are collected as (variable, coefficient) tuples and turned into PuLP expressions in one
        # call each: this avoids millions of operator-overload objects and is ~2x faster than `coef * var`.
        prob = pulp.LpProblem("plan", pulp.LpMinimize)
        AE, GE, LE = pulp.LpAffineExpression, pulp.LpConstraintGE, pulp.LpConstraintLE
        obj: list = []
        pool_terms: dict = defaultdict(list)
        batch_terms: dict = defaultdict(list)
        lane_terms: dict = defaultdict(list)
        store_terms: dict = defaultdict(list)
        xmeta = []
        xall = []
        for i in grp:
            j, s = int(inp.store_id[i]), int(inp.sku_id[i])
            sp = sku_params[s]
            v = float(sp["unit_volume"])
            m_s = int(sp["min_shelf_life_days"])
            xv = []
            for ln in lanes_by_store.get(j, []):
                for bid, _q, exp in pools.get((ln["wh"], s), []):
                    if batch_rem[bid] <= 0 or exp - ln["lead"] < m_s:
                        continue
                    var = pulp.LpVariable(f"x{len(xmeta)}", lowBound=0)
                    xmeta.append((i, ln["wh"], bid, j, ln))
                    xall.append(var)
                    xv.append(var)
                    obj.append((var, ln["cost"] + DELTA * batch_rank[bid]))
                    pool_terms[(ln["wh"], s)].append((var, 1.0))
                    batch_terms[bid].append((var, 1.0))
                    lane_terms[(ln["wh"], j)].append((var, v))
                    store_terms[j].append((var, v))
            u = pulp.LpVariable(f"u{i}", lowBound=0)
            w = pulp.LpVariable(f"w{i}", lowBound=0)
            obj.append((u, float(alpha[i] * sp["lost_margin"])))
            obj.append((w, float((1 - alpha[i]) * sp["writeoff_cost"])))
            # demand + safety stock:  sum(x) + u >= D_H + SS - I - R
            prob += pulp.LpConstraint(AE([(x, 1.0) for x in xv] + [(u, 1.0)]), GE,
                                      rhs=float(inp.DH[i] + inp.SS[i] - inp.I[i] - inp.R[i]))
            # expiry:  w - sum(x) >= I + R - D_L
            prob += pulp.LpConstraint(AE([(w, 1.0)] + [(x, -1.0) for x in xv]), GE,
                                      rhs=float(inp.I[i] + inp.R[i] - DL[i]))
        prob.setObjective(AE(obj))
        for key, vs in pool_terms.items():
            prob += pulp.LpConstraint(AE(vs), LE, rhs=float(avail[key]))
        for bid, vs in batch_terms.items():
            prob += pulp.LpConstraint(AE(vs), LE, rhs=float(batch_rem[bid]))
        lane_caps = {(int(r.wh_id), int(r.store_id)): float(r.cap) for r in inp.lanes.itertuples()}
        for key, vs in lane_terms.items():
            prob += pulp.LpConstraint(AE(vs), LE, rhs=max(0.0, lane_caps.get(key, 0.0) - lane_used[key]))
        for j, vs in store_terms.items():
            prob += pulp.LpConstraint(AE(vs), LE, rhs=max(0.0, inp.store_cap.get(j, 1e12) - store_used[j]))
        n_vars_total += len(xmeta)
        remaining = max(1.5, time_limit / max(len(glist), 1))
        prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=remaining, threads=4))
        st = pulp.LpStatus[prob.status]
        if prob.sol_status == pulp.LpSolutionIntegerFeasible:
            st = "Feasible (time limit)"
        statuses.append(st)
        lp_obj += float(pulp.value(prob.objective) or 0.0)
        for var, (i, wh, bid, j, ln) in zip(xall, xmeta):
            val = var.value() if var.value() is not None else 0.0
            if val > EPS:
                xs.append((i, wh, bid, j, val))
                sp = sku_params[int(inp.sku_id[i])]
                avail[(wh, int(inp.sku_id[i]))] -= val
                batch_rem[bid] -= val
                lane_used[(wh, j)] += val * float(sp["unit_volume"])
                store_used[j] += val * float(sp["unit_volume"])
    lp_seconds = time.time() - t_start

    # ---- integer rounding, capacity repair, FEFO re-assignment ----------------------------
    pools2 = _pools(inp)
    lines, rnd_notes = _round_and_repair(inp, xs, pools2, sku_params, lanes_by_store)
    lines = _fefo_normalise(inp, lines, pools2, sku_params, lanes_by_store, rnd_notes)

    series = _series_table(inp, lines, DL, alpha, sku_params)
    cost = _costs(lines, series, sku_params, inp)
    lines = explain_lines(inp, lines, series, pools2, lanes_by_store, sku_params, DL, alpha)
    status = "Optimal" if all(s == "Optimal" for s in statuses) else ", ".join(sorted(set(statuses)))
    notes = dict(rnd_notes, lp_variables=n_vars_total, solved_by_group=bool(by_group), groups=len(glist),
                 series_considered=int(inp.n), series_needing_stock=int(len(need)),
                 candidate_lanes_per_store=inp.n_candidate_lanes, lp_seconds=round(lp_seconds, 3),
                 lp_objective_continuous=round(lp_obj, 2),
                 relaxation="continuous LP + supply-preserving rounding; "
                            "group solves pass remaining supply/capacity forward" if by_group else
                            "continuous LP + supply-preserving rounding")
    return PlanResult(lines=lines, series=series, solver_status=status,
                      solve_seconds=round(time.time() - t_start, 3), objective_lp=lp_obj, cost=cost, notes=notes)


def _round_and_repair(inp, xs, pools, sku_params, lanes_by_store):
    notes = dict(lp_units=0.0, rounded_units=0, capacity_trimmed_units=0)
    if not xs:
        return pd.DataFrame(columns=["series_idx", "wh_id", "batch_id", "store_id", "qty"]), notes
    df = pd.DataFrame(xs, columns=["series_idx", "wh_id", "batch_id", "store_id", "val"])
    notes["lp_units"] = round(float(df["val"].sum()), 2)
    df["qty"] = np.floor(df["val"] + 1e-9).astype(int)
    df["frac"] = df["val"] - df["qty"]
    # largest-remainder rounding inside each batch keeps sum(rounded) = floor(sum(x)) <= batch qty
    k = np.floor(df.groupby("batch_id")["frac"].transform("sum") + 1e-6).astype(int)
    rank = df.groupby("batch_id")["frac"].rank(method="first", ascending=False)
    df["qty"] += (rank <= k).astype(int)
    df = df[df["qty"] > 0].copy()
    notes["rounded_units"] = int(df["qty"].sum())
    # capacity repair (rounding up can exceed a lane/store volume cap by < 1 unit-volume)
    vol = {s: float(p["unit_volume"]) for s, p in sku_params.items()}
    df["sku_id"] = inp.sku_id[df["series_idx"].to_numpy()]
    df["vol"] = df["sku_id"].map(vol) * df["qty"]
    lane_caps = {(int(r.wh_id), int(r.store_id)): float(r.cap) for r in inp.lanes.itertuples()}
    trimmed = 0
    for _ in range(50):
        changed = False
        ll = df.groupby(["wh_id", "store_id"])["vol"].sum()
        for (wh, st), load in ll.items():
            if load > lane_caps.get((wh, st), 1e12) + 1e-6:
                idx = df[(df.wh_id == wh) & (df.store_id == st)].sort_values("vol", ascending=False).index[0]
                df.loc[idx, "qty"] -= 1
                df.loc[idx, "vol"] = vol[df.at[idx, "sku_id"]] * df.at[idx, "qty"]
                trimmed += 1
                changed = True
        sl = df.groupby("store_id")["vol"].sum()
        for st, load in sl.items():
            if load > inp.store_cap.get(st, 1e12) + 1e-6:
                idx = df[df.store_id == st].sort_values("vol", ascending=False).index[0]
                df.loc[idx, "qty"] -= 1
                df.loc[idx, "vol"] = vol[df.at[idx, "sku_id"]] * df.at[idx, "qty"]
                trimmed += 1
                changed = True
        df = df[df["qty"] > 0]
        if not changed:
            break
    notes["capacity_trimmed_units"] = trimmed
    return df[["series_idx", "wh_id", "batch_id", "store_id", "qty"]].reset_index(drop=True), notes


def _fefo_normalise(inp, lines, pools, sku_params, lanes_by_store, notes):
    """Re-assign batches inside each warehouse-SKU pool so earliest-expiry eligible batches are used
    first, keeping every (warehouse, SKU, store) quantity unchanged. Falls back to the LP's own
    assignment for a pool if the greedy cannot place everything (reported in notes)."""
    if lines.empty:
        return lines.assign(sku_id=[], cost_per_unit=[], lead=[])
    lines = lines.copy()
    lines["sku_id"] = inp.sku_id[lines["series_idx"].to_numpy()]
    lane_info = {(int(r.wh_id), int(r.store_id)): (float(r.cost), int(r.lead) + int(inp.extra_lead.get(int(r.wh_id), 0)))
                 for r in inp.lanes.itertuples()}
    out, fallback = [], 0
    # plain-Python grouping (pandas groupby per pool was the dominant cost at 14k series)
    by_pool: dict = defaultdict(list)
    for ser, wh, bid, st, q, sku in zip(lines["series_idx"].tolist(), lines["wh_id"].tolist(), lines["batch_id"].tolist(),
                                        lines["store_id"].tolist(), lines["qty"].tolist(), lines["sku_id"].tolist()):
        by_pool[(wh, sku)].append((ser, bid, st, q))
    for (wh, sku), items in by_pool.items():
        rows = pools[(wh, sku)]
        m_s = int(sku_params[sku]["min_shelf_life_days"])
        agg: dict = defaultdict(int)                   # (store, series) -> qty
        for ser, _bid, st, q in items:
            agg[(st, ser)] += q
        todo = sorted(((lane_info[(wh, st)][1], st, ser, q) for (st, ser), q in agg.items()), reverse=True)  # most constrained first
        rem = {r[0]: r[1] for r in rows}
        new, ok = [], True
        for lead, st, ser, q in todo:
            need_q = q
            for bid, _q, exp in rows:
                if need_q <= 0:
                    break
                if exp - lead < m_s or rem[bid] <= 0:
                    continue
                t = min(need_q, rem[bid])
                new.append((ser, wh, bid, st, t, sku))
                rem[bid] -= t
                need_q -= t
            if need_q > 0:
                ok = False
                break
        if ok:
            out.extend(new)
        else:
            fallback += 1
            out.extend((ser, wh, bid, st, q, sku) for ser, bid, st, q in items)
    notes["fefo_pool_fallbacks"] = fallback
    res = pd.DataFrame(out, columns=["series_idx", "wh_id", "batch_id", "store_id", "qty", "sku_id"])
    res = res.groupby(["series_idx", "wh_id", "batch_id", "store_id", "sku_id"], as_index=False)["qty"].sum()
    res["cost_per_unit"] = [lane_info[(int(a), int(b))][0] for a, b in zip(res["wh_id"], res["store_id"])]
    res["lead"] = [lane_info[(int(a), int(b))][1] for a, b in zip(res["wh_id"], res["store_id"])]
    return res


def _series_table(inp, lines, DL, alpha, sku_params):
    ship = np.zeros(inp.n)
    if len(lines):
        np.add.at(ship, lines["series_idx"].to_numpy(), lines["qty"].to_numpy())
    target = inp.DH + inp.SS
    shortage = np.clip(target - (inp.I + inp.R + ship), 0, None)
    expiring = np.clip(inp.I + inp.R + ship - DL, 0, None)
    return pd.DataFrame(dict(series_idx=np.arange(inp.n), store_id=inp.store_id, sku_id=inp.sku_id, shipped=ship,
                             target=target, shortage=shortage, expiring=expiring, DL=DL, alpha=alpha))


def _costs(lines, series, sku_params, inp):
    transport = float((lines["qty"] * lines["cost_per_unit"]).sum()) if len(lines) else 0.0
    pi = series["sku_id"].map(lambda s: sku_params[int(s)]["lost_margin"]).to_numpy()
    eps = series["sku_id"].map(lambda s: sku_params[int(s)]["writeoff_cost"]).to_numpy()
    sh = float((series["alpha"] * pi * series["shortage"]).sum())
    ex = float(((1 - series["alpha"]) * eps * series["expiring"]).sum())
    return dict(transport=round(transport, 2), shortage=round(sh, 2), expiry=round(ex, 2),
                total=round(transport + sh + ex, 2))
