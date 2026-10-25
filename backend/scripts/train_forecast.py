"""Train LightGBM quantile models, evaluate on the held-out window, persist forecasts.

Usage: python -m scripts.train_forecast [--mode fast|full] [--eval fixed|retrain]
  fast  : weekly origins every 14 days, 120 trees (default for demos)
  full  : weekly origins every 7 days, 300 trees
  --eval retrain refits at every weekly test origin (slowest, strictest rolling-origin)
"""
import argparse
from datetime import datetime

from sqlalchemy import delete, insert

from app.config import get_settings
from app.database import models as m
from app.database.session import engine
from app.forecasting import model as fm
from app.simulation.world import load_world


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="fast", choices=["fast", "full"])
    ap.add_argument("--eval", default="fixed", choices=["fixed", "retrain"])
    a = ap.parse_args()
    world = load_world(engine)
    models, metrics, preds = fm.run_forecast_job(world, a.mode, a.eval)
    models.save(get_settings().model_dir)

    lanes = world.lanes[world.lanes["cost_rank"] == 1].set_index("store_id")["lead_time_days"]
    lead = lanes.loc[world.ss.store_id].to_numpy()
    rows = []
    with engine.begin() as conn:
        conn.execute(delete(m.Forecast))
        conn.execute(delete(m.ForecastRun))
        res = conn.execute(insert(m.ForecastRun).values(
            created_at=datetime.utcnow(), mode=f"{a.mode}/{a.eval}", metrics=metrics, as_of_idx=world.t0))
        run_id = res.inserted_primary_key[0]
        for h, q in preds.items():
            ss_ = fm.safety_stock(q[:, 1], q[:, 2], h, lead)
            for i in range(world.ss.n):
                rows.append(dict(run_id=run_id, store_id=int(world.ss.store_id[i]), sku_id=int(world.ss.sku_id[i]),
                                 horizon=h, p10=float(q[i, 0]), p50=float(q[i, 1]), p90=float(q[i, 2]),
                                 safety_stock=float(ss_[i])))
        for i in range(0, len(rows), 20000):
            conn.execute(insert(m.Forecast), rows[i:i + 20000])
    print(f"run {run_id}: weekly MAPE mean {metrics['mape_mean']:.1f}% "
          f"(min {metrics['mape_min']:.1f}, max {metrics['mape_max']:.1f}), WAPE {metrics['wape']:.1f}%, "
          f"P10-P90 coverage {metrics['coverage_p10_p90']:.1f}% | target <20% met: {metrics['target_met']} "
          f"| {metrics['train_seconds']}s")


if __name__ == "__main__":
    main()
