"""One-line shipment explanations built from the model's own inputs, cost terms and binding constraints.

Every reason is assembled from numbers the optimiser used (cover days, forecast, batch rank/expiry,
lane cost rank, saturation of cheaper alternatives, residual shortage). No free-text generation.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def explain_lines(inp, lines, series, pools, lanes_by_store, sku_params, DL, alpha) -> pd.DataFrame:
    if lines.empty:
        lines = lines.copy()
        lines["reason"] = []
        return lines
    lines = lines.copy()
    # final allocation state per warehouse-SKU pool / batch / lane / store
    shipped_pool: dict = defaultdict(int)
    shipped_batch: dict = defaultdict(int)
    lane_load: dict = defaultdict(float)
    store_load: dict = defaultdict(float)
    for r in lines.itertuples():
        v = float(sku_params[int(r.sku_id)]["unit_volume"])
        shipped_pool[(int(r.wh_id), int(r.sku_id))] += int(r.qty)
        shipped_batch[int(r.batch_id)] += int(r.qty)
        lane_load[(int(r.wh_id), int(r.store_id))] += v * int(r.qty)
        store_load[int(r.store_id)] += v * int(r.qty)
    lane_caps = {(int(r.wh_id), int(r.store_id)): float(r.cap) for r in inp.lanes.itertuples()}
    batch_info = {}
    for key, rows in pools.items():
        for rk, (bid, qty, exp) in enumerate(rows):
            batch_info[bid] = (key, rk + 1, len(rows), qty, exp)
    ser = series.set_index("series_idx")
    reasons = []
    for r in lines.itertuples():
        i, wh, j, s = int(r.series_idx), int(r.wh_id), int(r.store_id), int(r.sku_id)
        sp = sku_params[s]
        rate = float(inp.rate[i])
        stock = float(inp.I[i] + inp.R[i])
        cover = stock / rate if rate > 1e-9 else float("inf")
        store, whn = inp.store_names.get(j, f"Store {j}"), inp.wh_names.get(wh, f"WH-{wh}")
        # urgency
        if cover < 1.5:
            urg = f"{store} has {cover:.1f} days of cover ({stock:.0f} units vs {rate:.1f}/day P50)"
        elif cover < inp.horizon:
            urg = f"{store} covers {cover:.1f} of the {inp.horizon}-day horizon (P50 {inp.DH[i]:.0f} + safety {inp.SS[i]:.0f} units)"
        else:
            urg = f"{store} needs safety stock top-up (cover {cover:.0f} d, SS {inp.SS[i]:.0f} from P90-P50 gap)"
        # source batch
        (_k, rank, nb, bq, exp) = batch_info[int(r.batch_id)]
        fefo = ("earliest-expiry batch" if rank == 1 else f"expiry rank {rank} of {nb} (earlier batches exhausted or too short for shelf-life limit)")
        src = f"{whn} batch expires in {exp} d - {fefo}"
        # lane cost / binding constraints on cheaper alternatives
        lane_opts = lanes_by_store.get(j, [])
        mine = next((x for x in lane_opts if x["wh"] == wh), None)
        if mine is not None and mine is lane_opts[0]:
            lane_txt = f"lane cost {mine['cost']:.2f}/unit is lowest of {len(lane_opts)}"
        else:
            cheaper = lane_opts[0] if lane_opts else None
            why = "cheaper lane unavailable"
            if cheaper is not None:
                cw = cheaper["wh"]
                avail_left = sum(q for _b, q, _e in pools.get((cw, s), [])) - inp.wh_reserved.get((cw, s), 0) - shipped_pool[(cw, s)]
                if cw in inp.closed_warehouses:
                    why = f"{inp.wh_names.get(cw, cw)} is closed"
                elif avail_left <= 0:
                    why = f"{inp.wh_names.get(cw, cw)} supply of this SKU is fully allocated"
                elif lane_load[(cw, j)] >= 0.98 * lane_caps.get((cw, j), 1e12):
                    why = "cheapest lane capacity is full"
                else:
                    why = "cheapest lane had no batch with enough remaining shelf life"
            lane_txt = f"lane {mine['cost']:.2f}/unit used because {why}" if mine else "lane n/a"
        # impact
        short = float(ser.at[i, "shortage"])
        if short > 0.5:
            a_pi = float(alpha[i]) * float(sp["lost_margin"])
            best = lane_opts[0]["cost"] if lane_opts else float("inf")
            if best >= a_pi:
                imp = (f"residual shortfall {short:.0f} units left because lane cost {best:.2f} >= "
                       f"alpha-weighted lost margin {a_pi:.2f} (alpha {float(alpha[i]):.2f})")
            else:
                imp = f"residual shortfall {short:.0f} units (supply, capacity or shelf-life binding)"
        else:
            imp = "closes the coverage gap"
        extra = ""
        if lane_load[(wh, j)] >= 0.98 * lane_caps.get((wh, j), 1e12):
            extra = "; lane capacity binding"
        elif store_load[j] >= 0.98 * inp.store_cap.get(j, 1e12):
            extra = "; store capacity binding"
        reasons.append(f"{urg}; {src}; {lane_txt}; {imp}{extra}.")
    lines["reason"] = reasons
    return lines
