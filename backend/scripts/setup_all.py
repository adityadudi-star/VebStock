"""One explicit setup command for a fresh database (local or production).

    python -m scripts.setup_all --profile aditya            # schema + seed + forecasts (+ optional replay)
    python -m scripts.setup_all --profile aditya --compare  # also run the 5-seed replay (minutes)

Idempotent: if the database is already seeded it does nothing unless --force is given
(--force wipes ALL tables, including plans and override history).
Run it once against the production DATABASE_URL (Render shell, a one-off job, or locally with the
external connection string). The web service never seeds on startup.
"""
import argparse
import subprocess
import sys

from sqlalchemy import inspect, text

from app.database.models import Base
from app.database.session import engine


def seeded() -> bool:
    if "meta" not in inspect(engine).get_table_names():
        return False
    with engine.connect() as c:
        return c.execute(text("select count(*) from meta where key = 'as_of'")).scalar() > 0


def run(*args: str) -> None:
    print("->", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="aditya", choices=["aditya", "dev", "full"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--forecast-mode", default="fast", choices=["fast", "full"])
    ap.add_argument("--compare", action="store_true", help="also run the baseline-vs-optimised replay")
    ap.add_argument("--force", action="store_true", help="wipe and reseed even if data exists")
    a = ap.parse_args()
    Base.metadata.create_all(engine)
    if seeded() and not a.force:
        print("Database already seeded; nothing to do (use --force to wipe and reseed).")
        return
    run("scripts.seed", "--profile", a.profile, "--seed", str(a.seed))
    run("scripts.train_forecast", "--mode", a.forecast_mode)
    if a.compare:
        run("scripts.run_compare")
    print("Setup complete.")


if __name__ == "__main__":
    main()
