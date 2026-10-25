"""Test fixtures: a small, isolated, reproducible dataset in a temp SQLite file (never the dev DB)."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="vebstock_test_"))
os.environ["DATABASE_URL"] = "sqlite:///" + (_TMP / "test.db").as_posix()
os.environ["CORS_ORIGINS"] = "https://vebstock.vercel.app,http://localhost:3000"
os.environ["MODEL_DIR"] = str(_TMP / "models")
# Pre-existing endpoint tests run open; tests/test_auth.py turns enforcement on explicitly.
os.environ["AUTH_REQUIRED"] = "false"

import pytest  # noqa: E402
from datetime import datetime  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, insert  # noqa: E402

from app.database import models as m  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.forecasting import model as fm  # noqa: E402
from app.simulation import generator as g  # noqa: E402
from app.simulation.world import load_world  # noqa: E402


@pytest.fixture(scope="session")
def world():
    m.Base.metadata.create_all(engine)
    cfg = g.GeneratorConfig(profile="test", seed=7, n_stores=24, n_skus=16, assortment=0.6, n_promotions=16)
    w = g.build(cfg)
    g.load(w, engine)
    wld = load_world(engine)
    models, metrics, preds = fm.run_forecast_job(wld, "fast", "fixed")
    import numpy as np
    lanes = wld.lanes[wld.lanes["cost_rank"] == 1].set_index("store_id")["lead_time_days"]
    lead = lanes.loc[wld.ss.store_id].to_numpy()
    rows = []
    with engine.begin() as conn:
        rid = conn.execute(insert(m.ForecastRun).values(created_at=datetime.utcnow(), mode="fast/fixed", metrics=metrics,
                                                        as_of_idx=wld.t0)).inserted_primary_key[0]
        for h, q in preds.items():
            ss_ = fm.safety_stock(q[:, 1], q[:, 2], h, lead)
            for i in range(wld.ss.n):
                rows.append(dict(run_id=rid, store_id=int(wld.ss.store_id[i]), sku_id=int(wld.ss.sku_id[i]), horizon=h,
                                 p10=float(q[i, 0]), p50=float(q[i, 1]), p90=float(q[i, 2]), safety_stock=float(ss_[i])))
        conn.execute(insert(m.Forecast), rows)
    wld.metrics, wld.models, wld.preds = metrics, models, preds
    return wld


@pytest.fixture(scope="session")
def client(world):
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def db(world):
    s = SessionLocal()
    yield s
    s.close()
