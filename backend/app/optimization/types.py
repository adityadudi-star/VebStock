"""Plain data containers for the optimiser (no database access here)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class PlanInputs:
    horizon: int
    # one row per store-SKU series that the plan considers (arrays aligned by index)
    store_id: np.ndarray
    sku_id: np.ndarray
    I: np.ndarray            # usable store stock (on-hand minus reserved)
    R: np.ndarray            # confirmed incoming within horizon
    DH: np.ndarray           # P50 demand over horizon
    SS: np.ndarray           # uncertainty-driven safety stock (P90-P50 over lead time)
    rate: np.ndarray         # P50 daily demand (DH / horizon)
    p10h: np.ndarray
    p90h: np.ndarray
    lanes: pd.DataFrame      # candidate lanes: store_id, wh_id, cost, lead, cap, rank
    batches: pd.DataFrame    # id, wh_id, sku_id, qty, exp_days (days from as-of)
    wh_reserved: dict        # (wh_id, sku_id) -> SSW
    store_cap: dict          # store_id -> Store[j]
    skus: pd.DataFrame       # indexed by sku_id: lost_margin, writeoff_cost, unit_volume, min_shelf_life_days, category, name
    alpha_by_category: dict
    default_alpha: float = 0.7
    store_names: dict = field(default_factory=dict)
    wh_names: dict = field(default_factory=dict)
    asof_label: str = ""
    closed_warehouses: set = field(default_factory=set)
    extra_lead: dict = field(default_factory=dict)       # wh_id -> additional lead days (supplier delay)
    n_candidate_lanes: int = 3

    @property
    def n(self) -> int:
        return len(self.store_id)

    def alpha_for_sku(self, sku_id: int) -> float:
        cat = self.skus.at[sku_id, "category"]
        return float(self.alpha_by_category.get(cat, self.default_alpha))


@dataclass
class PlanResult:
    lines: pd.DataFrame           # series_idx, sku_id, store_id, wh_id, batch_id, qty, cost_per_unit, lead, reason
    series: pd.DataFrame          # per-series: idx, shortage, expiring, shipped, DL, alpha ...
    solver_status: str
    solve_seconds: float
    objective_lp: float
    cost: dict                    # transport, shortage, expiry, total
    notes: dict
