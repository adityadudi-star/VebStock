"""Irreducible error of the simulated data: weekly MAPE/WAPE of an ORACLE that knows the true expected demand.

No real forecaster can beat this on the test window; it contextualises the measured LightGBM accuracy.
    python -m scripts.noise_floor
"""
import numpy as np

from app.database.session import engine
from app.simulation import demand as dm
from app.simulation.world import load_world

w = load_world(engine)
mu = dm.expected_demand(w.ss, w.cal)
t0 = w.t0
ape, num, den = [], 0.0, 0.0
for wk in range((dm.N_DAYS - t0) // 7):
    s = t0 + 7 * wk
    a = w.sales[:, s:s + 7].sum(1).astype(float)
    f = mu[:, s:s + 7].sum(1).astype(float)
    pos = a > 0
    ape.append(100 * np.mean(np.abs(a[pos] - f[pos]) / a[pos]))
    num += np.abs(a - f).sum()
    den += a.sum()
print(f"oracle weekly MAPE (A>0): mean {np.mean(ape):.1f}% min {np.min(ape):.1f}% max {np.max(ape):.1f}% | WAPE {100 * num / den:.1f}%")
print("so a perfect forecaster of the expected value would still miss the PRD's <20% MAPE target on this dataset"
      if np.mean(ape) >= 20 else "oracle MAPE is below 20%: the target is achievable in principle")
