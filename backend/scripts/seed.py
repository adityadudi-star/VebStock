"""Generate simulated data and load it. Usage: python -m scripts.seed [--profile aditya|full] [--seed 42]

WARNING: wipes and reloads every table (including plans/overrides)."""
import argparse
import time

from app.database.models import Base
from app.database.session import engine
from app.simulation import generator as g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="aditya", choices=[*g.PROFILES, *g.PROFILE_ALIASES])
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    Base.metadata.create_all(engine)
    cfg = g.get_profile(a.profile)
    cfg.seed = a.seed
    t = time.time()
    world = g.build(cfg)
    print(f"generated in {time.time() - t:.1f}s; series={world['ss'].n}")
    print(g.load(world, engine))


if __name__ == "__main__":
    main()
