"""Role-based access: password hashing, signed session tokens and the FastAPI guards used by app.api.routes.

Standard library only. Role selection in the UI is never trusted: every protected endpoint re-checks the role (and, for
retail, the store) carried by a server-signed token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import models as m
from app.database.session import get_db

ROLES = ("manufacturer", "finance", "warehouse", "retail")
STAFF = ("manufacturer", "finance", "warehouse")

_DEV_SECRET = secrets.token_hex(32)


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    store_id: int | None = None


# Used when AUTH_REQUIRED=false: behaves like an unrestricted operator (pre-existing behaviour).
OPEN = Principal(username="anonymous", role="open", store_id=None)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), digest)
    except Exception:
        return False


def _secret() -> bytes:
    s = get_settings()
    if s.auth_secret:
        return s.auth_secret.encode()
    if s.environment == "production":
        raise RuntimeError("AUTH_SECRET must be set in production")
    return _DEV_SECRET.encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user: m.AppUser) -> tuple[str, int]:
    exp = int(time.time()) + get_settings().auth_token_hours * 3600
    body = _b64(json.dumps(dict(u=user.username, r=user.role, s=user.store_id, e=exp), separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", exp


def read_token(token: str) -> Principal | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        d = json.loads(_unb64(body))
        if d["e"] < time.time() or d["r"] not in ROLES:
            return None
        return Principal(username=d["u"], role=d["r"], store_id=d.get("s"))
    except Exception:
        return None


def current_principal(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Principal:
    if not get_settings().auth_required:
        return OPEN
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    p = read_token(authorization[7:].strip())
    if p is None:
        raise HTTPException(401, "Your session has expired or is invalid. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    # The account must still exist, be active and keep the same role/store (revocation without waiting for expiry).
    u = db.query(m.AppUser).filter(m.AppUser.username == p.username).first()
    if u is None or not u.active or u.role != p.role or u.store_id != p.store_id:
        raise HTTPException(401, "This account is no longer active. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return p


def require(*roles: str):
    """Dependency: the caller must be signed in with one of `roles`."""
    allowed = set(roles)

    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if p is OPEN or p.role in allowed:
            return p
        raise HTTPException(403, f"The {p.role} role cannot use this resource.")

    return dep


def own_store(p: Principal) -> int | None:
    """Store id a retail caller is confined to; None for everyone else. A retail account without a store gets nothing."""
    if p.role != "retail":
        return None
    if not p.store_id:
        raise HTTPException(403, "This retail account is not linked to a store.")
    return p.store_id


# --- login throttling (in-memory, per process: slows password guessing, not a substitute for a WAF) ---
_FAILS: dict[str, list[float]] = {}
_WINDOW, _MAX_FAILS = 300, 5


def throttled(username: str) -> bool:
    now = time.time()
    hits = [t for t in _FAILS.get(username, []) if now - t < _WINDOW]
    _FAILS[username] = hits
    return len(hits) >= _MAX_FAILS


def record_failure(username: str) -> None:
    _FAILS.setdefault(username, []).append(time.time())


def clear_failures(username: str) -> None:
    _FAILS.pop(username, None)
