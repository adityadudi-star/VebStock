"""Safety-stock rule (no heavy imports so the API process does not need LightGBM)."""
import numpy as np


def safety_stock(p50_h: np.ndarray, p90_h: np.ndarray, h: int, lead_time: np.ndarray) -> np.ndarray:
    """SS = P90 - P50 demand over the lead time.

    The h-day quantile gap is rescaled to the lead time assuming independent daily demand
    (gap scales with sqrt(LT/h)); this is documented as an approximation in docs/."""
    gap = np.clip(p90_h - p50_h, 0, None)
    return gap * np.sqrt(np.clip(lead_time, 1, None) / h)
