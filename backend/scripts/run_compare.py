"""Replay baseline vs optimised policy over the held-out window and store the result.

Usage: python -m scripts.run_compare [--seeds 11 12 13 14 15] [--plan-every 7] [--horizon 14] [--alpha 0.7]
"""
import argparse
import json
import time
from datetime import datetime

from sqlalchemy import delete, insert

from app.database import models as m
from app.database.session import engine
from app.simulation.replay import ReplayConfig, run_comparison
from app.simulation.world import load_world


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13, 14, 15])
    ap.add_argument("--plan-every", type=int, default=1)
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--alpha", type=float, default=0.7)
    a = ap.parse_args()
    t = time.time()
    world = load_world(engine)
    cfg = ReplayConfig(plan_every_days=a.plan_every, plan_horizon=a.horizon, alpha=a.alpha)
    result = run_comparison(engine, world, a.seeds, cfg)
    result["wall_clock_seconds"] = round(time.time() - t, 1)
    with engine.begin() as conn:
        conn.execute(delete(m.ComparisonRun))
        conn.execute(insert(m.ComparisonRun).values(created_at=datetime.utcnow(), config=result["config"],
                                                    result=json.loads(json.dumps(result, default=float))))
    print(f"\nstored comparison ({result['wall_clock_seconds']}s) for seeds {a.seeds}")
    for k, v in result["kpis"].items():
        rd = v["rel_diff_pct"]
        print(f"{k:22s} baseline {v['baseline']['mean']:10.2f} [{v['baseline']['min']:.2f}-{v['baseline']['max']:.2f}] | "
              f"optimized {v['optimized']['mean']:10.2f} [{v['optimized']['min']:.2f}-{v['optimized']['max']:.2f}] | "
              f"rel diff {rd if rd is None else round(rd, 1)}%")
    print("violations", result["extra"]["constraint_violations"]["optimized"],
          "| explanation coverage", result["extra"]["explanation_coverage_pct"]["optimized"])


if __name__ == "__main__":
    main()
