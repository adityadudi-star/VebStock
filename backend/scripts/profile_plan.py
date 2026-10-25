"""cProfile one plan solve (use with the full profile). python -m scripts.profile_plan"""
import cProfile
import pstats
import time

from app.database.session import SessionLocal
from app.optimization.model import solve
from app.services.inputs import build_inputs

with SessionLocal() as db:
    inp = build_inputs(db, 14, {}, default_alpha=0.7)
pr = cProfile.Profile()
t = time.time()
pr.enable()
res = solve(inp)
pr.disable()
print("solve wall", round(time.time() - t, 2), res.notes)
pstats.Stats(pr).sort_stats("cumulative").print_stats(22)
