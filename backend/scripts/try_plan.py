"""Developer smoke test: build inputs, solve, validate, print timing. python -m scripts.try_plan [horizon] [alpha]"""
import sys
import time

from app.database.session import SessionLocal
from app.optimization.model import solve
from app.optimization.validator import validate_plan
from app.services.inputs import build_inputs

H = int(sys.argv[1]) if len(sys.argv) > 1 else 14
A = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
with SessionLocal() as db:
    t = time.time()
    inp = build_inputs(db, H, {}, default_alpha=A)
    t_in = time.time() - t
    res = solve(inp)
    val = validate_plan(inp, res.lines, res.series)
print(f"inputs {t_in:.2f}s | solve {res.solve_seconds}s | status {res.solver_status}")
print("lines", len(res.lines), "units", int(res.lines.qty.sum()) if len(res.lines) else 0)
print("cost", res.cost)
print("notes", res.notes)
print("shortage units", round(res.series.shortage.sum(), 1), "of target", round(res.series.target.sum(), 1))
print("valid", val["valid"], val["violation_counts"])
if len(res.lines):
    print(res.lines.iloc[0].reason)
