"""
Auth helpers using only Python stdlib for JWT (HMAC-SHA256 / HS256)
and bcrypt directly (bypassing passlib which has version compat issues with bcrypt 5.x).
"""

import os
import json
import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .database import get_db

SECRET_KEY = os.getenv("JWT_SECRET", "hyopps-dev-secret-change-in-prod").encode()
ACCESS_TOKEN_EXPIRE_HOURS = 8

bearer_scheme = HTTPBearer()


# ── Minimal HS256 JWT (stdlib only) ───────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _sign(msg: str) -> str:
    return _b64url_encode(hmac.new(SECRET_KEY, msg.encode(), hashlib.sha256).digest())


def create_token(user_id: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = _b64url_encode(json.dumps({"sub": user_id, "exp": int(expire.timestamp())}).encode())
    sig = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"


def _decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header, payload_b64, sig = parts
    expected_sig = _sign(f"{header}.{payload_b64}")
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid token signature")
    data = json.loads(_b64url_decode(payload_b64))
    if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
        raise ValueError("Token expired")
    return data


# ── Password helpers (bcrypt direct) ──────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode() if isinstance(hashed, str) else hashed)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ── User lookup ────────────────────────────────────────────────────────────

def _get_user_by_id(user_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT id,firstname,lastname,email,languages,skills,roles,organization_id,app_role,created_at FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["languages"] = json.loads(d["languages"] or "[]")
    d["skills"] = json.loads(d["skills"] or "[]")
    d["roles"] = json.loads(d["roles"] or "[]")
    return d


# ── FastAPI dependencies ───────────────────────────────────────────────────

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        payload = _decode_token(credentials.credentials)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise ValueError("Missing sub")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user = _get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["app_role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
