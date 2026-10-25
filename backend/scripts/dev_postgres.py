"""Dev/testing helper: start a throw-away local PostgreSQL (pip install pgserver) and print its URL.

Not used in production, and pgserver is deliberately not in requirements.txt. It lets you exercise the
PostgreSQL code paths without installing database software:
    pip install pgserver
    python -m scripts.dev_postgres            # prints DATABASE_URL, keeps the server up until Ctrl+C
"""
import sys
import tempfile
import time
from pathlib import Path

import pgserver
import psycopg


def main() -> None:
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "vebstock_pg"
    srv = pgserver.get_server(d, cleanup_mode=None)
    base = srv.get_uri()
    with psycopg.connect(base, autocommit=True) as c:
        if not c.execute("select 1 from pg_database where datname = 'vebstock'").fetchone():
            c.execute("create database vebstock")
    print("DATABASE_URL=" + base.rsplit("/", 1)[0] + "/vebstock", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
