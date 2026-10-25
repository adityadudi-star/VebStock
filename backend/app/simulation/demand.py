"""Deterministic demand model shared by the data generator, forecaster features and replay.

mu[series, day] is the *expected* daily demand. Realised sales are drawn around it
(gamma-Poisson) with an explicit seed, so every dataset and every replay seed is reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

START_DATE = date(2026, 1, 23)   # day 275 (the as-of day) = 2026-10-25
N_DAYS = 365
TEST_DAYS = 90
T0 = N_DAYS - TEST_DAYS  # 275 -> as-of day: first day of the held-out window

CATEGORIES = [
    # name, shelf_life_days, min_remaining_shelf_life, price range, margin pct, writeoff pct of price, volume L
    ("Dairy", 28, 7, (25, 90), 0.18, 0.85, 0.9),
    ("Beverages", 180, 30, (20, 120), 0.22, 0.70, 1.2),
    ("Snacks", 120, 21, (10, 60), 0.28, 0.70, 0.5),
    ("Staples", 270, 45, (40, 180), 0.12, 0.75, 1.5),
    ("Biscuits", 150, 30, (10, 50), 0.25, 0.70, 0.45),
    ("Personal Care", 540, 90, (50, 300), 0.35, 0.60, 0.4),
    ("Home Care", 540, 90, (40, 250), 0.30, 0.60, 0.8),
    ("Packaged Foods", 240, 45, (30, 150), 0.24, 0.72, 0.6),
]
N_CAT = len(CATEGORIES)

# festival id: 1 Holi, 2 Eid (al-Fitr, al-Adha), 3 Diwali.  (date, name_id)
FESTIVALS = [
    (date(2026, 3, 4), 1),     # Holi
    (date(2026, 3, 20), 2),    # Eid al-Fitr (approx.)
    (date(2026, 5, 27), 2),    # Eid al-Adha (approx.)
    (date(2026, 11, 8), 3),    # Diwali
]
FEST_WINDOW = (-6, 1)  # days around the festival date that carry uplift

# festival uplift per category [Holi, Eid, Diwali]
FEST_UPLIFT = np.array([
    [1.25, 1.20, 1.45],  # Dairy
    [1.45, 1.20, 1.30],  # Beverages
    [1.35, 1.25, 1.50],  # Snacks
    [1.10, 1.30, 1.25],  # Staples
    [1.20, 1.20, 1.50],  # Biscuits
    [1.05, 1.10, 1.25],  # Personal care
    [1.00, 1.05, 1.30],  # Home care
    [1.10, 1.20, 1.30],  # Packaged foods
])
DOW_MULT = np.array([0.90, 0.90, 0.95, 1.00, 1.10, 1.25, 1.20])  # Mon..Sun
# month seasonality amplitude / peak month per category
SEAS_AMP = np.array([0.05, 0.25, 0.05, 0.03, 0.06, 0.04, 0.04, 0.05])
SEAS_PEAK = np.array([6, 5, 11, 1, 12, 1, 6, 12])


def calendar() -> dict:
    days = [START_DATE + timedelta(d) for d in range(N_DAYS)]
    dow = np.array([d.weekday() for d in days])
    month = np.array([d.month for d in days])
    fest_id = np.zeros(N_DAYS, dtype=np.int8)
    for fd, fid in FESTIVALS:
        c = (fd - START_DATE).days
        for off in range(FEST_WINDOW[0], FEST_WINDOW[1] + 1):
            i = c + off
            if 0 <= i < N_DAYS:
                fest_id[i] = fid
    return {"dates": days, "dow": dow, "month": month, "fest_id": fest_id}


@dataclass
class SeriesSet:
    """Arrays describing every stocked series (aligned by index)."""
    store_id: np.ndarray
    sku_id: np.ndarray
    base_rate: np.ndarray
    growth: np.ndarray
    cat_idx: np.ndarray
    region_idx: np.ndarray
    cluster: np.ndarray
    price: np.ndarray            # list price
    promos: list = field(default_factory=list)  # (sku_id, region_idx, start, end, discount, uplift)

    @property
    def n(self) -> int:
        return len(self.store_id)


def promo_matrices(ss: SeriesSet) -> tuple[np.ndarray, np.ndarray]:
    """Return (promo_flag int8 [S,D], price_ratio float32 [S,D]) built from promotion rows."""
    flag = np.zeros((ss.n, N_DAYS), dtype=np.int8)
    ratio = np.ones((ss.n, N_DAYS), dtype=np.float32)
    mult = np.ones((ss.n, N_DAYS), dtype=np.float32)
    if not ss.promos:
        return flag, ratio, mult
    # index series by (sku, region)
    key = ss.sku_id.astype(np.int64) * 16 + ss.region_idx
    order = np.argsort(key, kind="stable")
    skey = key[order]
    for sku, reg, s, e, disc, up in ss.promos:
        k = int(sku) * 16 + int(reg)
        lo, hi = np.searchsorted(skey, k, "left"), np.searchsorted(skey, k, "right")
        if hi <= lo:
            continue
        rows = order[lo:hi]
        flag[rows, s:e + 1] = 1
        ratio[rows, s:e + 1] = 1.0 - disc
        mult[rows, s:e + 1] = np.maximum(mult[rows, s:e + 1], up)
    return flag, ratio, mult


def expected_demand(ss: SeriesSet, cal: dict | None = None, promo_mult: np.ndarray | None = None) -> np.ndarray:
    """mu[S, D] float32."""
    cal = cal or calendar()
    if promo_mult is None:
        promo_mult = promo_matrices(ss)[2]
    dow = DOW_MULT[cal["dow"]][None, :]                                    # [1,D]
    months = cal["month"]
    seas = 1.0 + SEAS_AMP[:, None] * np.cos(2 * np.pi * (months[None, :] - SEAS_PEAK[:, None]) / 12.0)  # [C,D]
    fest = np.ones((N_CAT, N_DAYS))
    fid = cal["fest_id"]
    for f in (1, 2, 3):
        m = fid == f
        fest[:, m] = FEST_UPLIFT[:, f - 1][:, None]
    trend = 1.0 + ss.growth[:, None] * (np.arange(N_DAYS)[None, :] / N_DAYS)
    mu = (ss.base_rate[:, None] * dow * seas[ss.cat_idx] * fest[ss.cat_idx] * trend * promo_mult)
    return mu.astype(np.float32)


def realise(mu: np.ndarray, seed: int, shape: float = 6.0, day_slice: slice | None = None) -> np.ndarray:
    """Draw integer demand ~ Poisson(mu * Gamma(shape, 1/shape)); explicit seed => reproducible."""
    rng = np.random.default_rng(seed)
    m = mu if day_slice is None else mu[:, day_slice]
    g = rng.gamma(shape, 1.0 / shape, size=m.shape).astype(np.float32)
    return rng.poisson(m * g).astype(np.int16)
