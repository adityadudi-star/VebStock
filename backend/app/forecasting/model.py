"""LightGBM quantile demand forecasting (P10/P50/P90) for 7/14/30-day horizons.

One stacked model per quantile covers every SKU-store series and all horizons (horizon is a feature).
Target = units demanded over the next h days, normalised by recent run-rate (monotone, so
quantiles are preserved after rescaling).

Leakage rules: features at origin d only use sales on days < d. Calendar items for the
target window (festival days, promo days, price ratio) are plan-known in advance. Training
rows only use target windows that end before the training cut-off.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np

from app.forecasting.safety import safety_stock  # noqa: F401  (re-exported)
from app.simulation import demand as dm
from app.simulation.world import World

HORIZONS = (7, 14, 30)
QUANTILES = (0.1, 0.5, 0.9)
FEATURES = ["horizon", "s7", "s14p", "s28", "s56", "mean28", "std28", "trend", "nz28", "last7_ratio",
            "promo_hist28", "promo_days", "price_ratio", "fest_days", "weekend_days", "month", "month_end",
            "cluster", "cat", "region", "price", "log_level"]


@dataclass
class Prepared:
    flag: np.ndarray
    ratio: np.ndarray


def prepare(world: World) -> Prepared:
    flag, ratio, _ = dm.promo_matrices(world.ss)
    return Prepared(flag=flag, ratio=ratio)


def build_features(world: World, prep: Prepared, sales: np.ndarray, d: int, h: int) -> np.ndarray:
    """Feature matrix [S, F] for forecasts starting on day index d (uses sales[:, :d] only)."""
    ss, cal = world.ss, world.cal
    hist = sales[:, :d].astype(np.float32)
    s7 = hist[:, max(0, d - 7):d].sum(1)
    s14p = hist[:, max(0, d - 14):max(0, d - 7)].sum(1)
    s28 = hist[:, max(0, d - 28):d].sum(1)
    s56 = hist[:, max(0, d - 56):d].sum(1)
    w28 = hist[:, max(0, d - 28):d]
    mean28 = w28.mean(1)
    std28 = w28.std(1)
    nz28 = (w28 > 0).mean(1)
    trend = (s7 + 1) / (s14p + 1)
    last7_ratio = (s7 + 1) / (s28 / 4 + 1)
    end = min(d + h, dm.N_DAYS)
    win = slice(d, end)
    n = max(end - d, 1)
    promo_days = prep.flag[:, win].sum(1)
    price_ratio = prep.ratio[:, win].mean(1)
    fest_days = float((cal["fest_id"][win] > 0).sum())
    wk = float((cal["dow"][win] >= 5).sum())
    month = float(cal["month"][min(d, dm.N_DAYS - 1)])
    month_end = float(cal["month"][min(end - 1, dm.N_DAYS - 1)])
    f = np.column_stack([
        np.full(ss.n, h, dtype=np.float32), s7, s14p, s28, s56, mean28, std28, trend, nz28, last7_ratio,
        prep.flag[:, max(0, d - 28):d].sum(1), promo_days, price_ratio,
        np.full(ss.n, fest_days), np.full(ss.n, wk), np.full(ss.n, month), np.full(ss.n, month_end),
        ss.cluster, ss.cat_idx, ss.region_idx, ss.price, np.log1p(mean28 * 7),
    ]).astype(np.float32)
    return f


def _scale(f: np.ndarray, h: int) -> np.ndarray:
    return f[:, FEATURES.index("mean28")] * h + 1.0


def _target(sales: np.ndarray, d: int, h: int) -> np.ndarray:
    return sales[:, d:d + h].sum(1).astype(np.float32)


@dataclass
class ForecastModels:
    boosters: dict  # quantile -> lgb.Booster
    train_cutoff: int
    params: dict

    def predict(self, f: np.ndarray, h: int) -> np.ndarray:
        """Return array [S, 3] of (P10, P50, P90) demand over h days, monotone."""
        sc = _scale(f, h)[:, None]
        out = np.column_stack([np.clip(self.boosters[q].predict(f), 0, None) for q in QUANTILES])
        out = np.sort(out, axis=1) * sc
        return out

    def save(self, directory: str) -> None:
        import os
        os.makedirs(directory, exist_ok=True)
        for q, b in self.boosters.items():
            b.save_model(f"{directory}/lgbm_q{int(q * 100)}.txt")


def train(world: World, prep: Prepared, sales: np.ndarray, cutoff: int, mode: str = "fast") -> ForecastModels:
    """Train on target windows that end on/before `cutoff` (exclusive of any later data)."""
    step = 7 if mode == "full" else 14
    rows_x, rows_y = [], []
    for h in HORIZONS:
        for d in range(56, cutoff - h + 1, step):
            f = build_features(world, prep, sales, d, h)
            y = _target(sales, d, h) / _scale(f, h)
            rows_x.append(f)
            rows_y.append(y)
    X = np.vstack(rows_x)
    Y = np.concatenate(rows_y)
    n_rounds = 300 if mode == "full" else 120
    params = dict(learning_rate=0.05, num_leaves=31, min_data_in_leaf=40, bagging_fraction=0.8,
                  bagging_freq=1, feature_fraction=0.9, verbose=-1, num_threads=0, seed=7)
    boosters = {}
    for q in QUANTILES:
        ds = lgb.Dataset(X, label=Y, feature_name=FEATURES, free_raw_data=False)
        boosters[q] = lgb.train(dict(params, objective="quantile", alpha=q), ds, num_boost_round=n_rounds)
    return ForecastModels(boosters=boosters, train_cutoff=cutoff, params=dict(params, rounds=n_rounds))


def evaluate_rolling(world: World, prep: Prepared, sales: np.ndarray, mode: str = "fast",
                     eval_mode: str = "fixed", base_models: ForecastModels | None = None) -> dict:
    """Weekly rolling-origin evaluation over the held-out window (12 full weeks).

    eval_mode "fixed": one model trained on days < T0; each weekly origin builds features from all
    earlier data (including earlier test days). "retrain": refit at every origin (slow, strictest)."""
    t0 = world.t0
    models = base_models or train(world, prep, sales, t0, mode)
    weeks = []
    for w in range((dm.N_DAYS - t0) // 7):
        d = t0 + 7 * w
        if eval_mode == "retrain" and w > 0:
            models = train(world, prep, sales, d, mode)
        f = build_features(world, prep, sales, d, 7)
        q = models.predict(f, 7)
        actual = _target(sales, d, 7)
        pos = actual > 0
        ape = np.abs(actual - q[:, 1])[pos] / actual[pos]
        weeks.append(dict(
            week=w + 1, start_idx=d, mape=float(100 * ape.mean()) if pos.any() else None,
            wape=float(100 * np.abs(actual - q[:, 1]).sum() / max(actual.sum(), 1)),
            actual_units=float(actual.sum()), forecast_units=float(q[:, 1].sum()),
            coverage_p10_p90=float(100 * ((actual >= q[:, 0]) & (actual <= q[:, 2])).mean()),
            n_series_positive=int(pos.sum())))
    mapes = [x["mape"] for x in weeks if x["mape"] is not None]
    tot_a = sum(x["actual_units"] for x in weeks)
    wape = sum(x["wape"] * x["actual_units"] for x in weeks) / max(tot_a, 1)
    return dict(weeks=weeks, mape_mean=float(np.mean(mapes)), mape_min=float(np.min(mapes)),
                mape_max=float(np.max(mapes)), wape=float(wape),
                coverage_p10_p90=float(np.mean([x["coverage_p10_p90"] for x in weeks])),
                eval_mode=eval_mode, train_mode=mode, train_cutoff_idx=t0,
                target_mape=20.0, target_met=bool(np.mean(mapes) < 20.0))


def run_forecast_job(world: World, mode: str = "fast", eval_mode: str = "fixed") -> tuple[ForecastModels, dict, dict]:
    """Train, evaluate on the held-out window, and produce live forecasts at the as-of date."""
    t = time.time()
    prep = prepare(world)
    models = train(world, prep, world.sales, world.t0, mode)
    metrics = evaluate_rolling(world, prep, world.sales, mode, eval_mode, base_models=models)
    metrics["train_seconds"] = round(time.time() - t, 1)
    preds = {}
    for h in HORIZONS:
        preds[h] = models.predict(build_features(world, prep, world.sales, world.t0, h), h)
    return models, metrics, preds
