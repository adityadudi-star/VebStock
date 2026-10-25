"""Create or update a login account.

Usage:
  python -m scripts.create_user --username anita --role finance
  python -m scripts.create_user --username store12 --role retail --store-id 12
The password is prompted for (or read from the VEBSTOCK_PASSWORD environment variable). Re-running for an existing
username updates its password, role and store and re-activates it. Use --deactivate to revoke an account.
"""
import argparse
import getpass
import os
import sys

from app import auth
from app.database import models as m
from app.database.session import SessionLocal, engine


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    ap.add_argument("--role", required=True, choices=auth.ROLES)
    ap.add_argument("--store-id", type=int, help="required for the retail role: the one store this account may see")
    ap.add_argument("--deactivate", action="store_true")
    a = ap.parse_args()

    m.AppUser.__table__.create(engine, checkfirst=True)
    name = a.username.strip().lower()
    with SessionLocal() as db:
        u = db.query(m.AppUser).filter(m.AppUser.username == name).first()
        if a.deactivate:
            if u is None:
                print("No such user", file=sys.stderr)
                return 1
            u.active = 0
            db.commit()
            print(f"Deactivated {name}")
            return 0
        if a.role == "retail":
            if not a.store_id or db.get(m.Store, a.store_id) is None:
                print("--store-id must name an existing store for the retail role", file=sys.stderr)
                return 1
        elif a.store_id:
            print("--store-id is only for the retail role", file=sys.stderr)
            return 1
        pw = os.environ.get("VEBSTOCK_PASSWORD") or getpass.getpass("Password: ")
        if len(pw) < 8:
            print("Password must be at least 8 characters", file=sys.stderr)
            return 1
        if u is None:
            u = m.AppUser(username=name, password_hash="", role=a.role)
            db.add(u)
        u.password_hash, u.role, u.store_id, u.active = auth.hash_password(pw), a.role, a.store_id, 1
        db.commit()
        print(f"Saved {name} ({a.role}{', store ' + str(a.store_id) if a.store_id else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
