from __future__ import annotations

import requests
import jwt
from fastapi import HTTPException, Request
from . import config


def _token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else None


def require_user(request: Request) -> dict:
    token = _token(request)
    if not token or not config.SUPABASE_JWT_SECRET:
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(
            token,
            config.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            issuer=f"{config.SUPABASE_URL}/auth/v1" if config.SUPABASE_URL else None,
            options={"verify_iss": bool(config.SUPABASE_URL)},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session") from exc
    return claims


def login(email: str, password: str) -> dict:
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise HTTPException(503, "Supabase Auth is not configured")
    response = requests.post(
        f"{config.SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": config.SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    if response.status_code in (400, 401):
        raise HTTPException(401, "Invalid email or password")
    response.raise_for_status()
    data = response.json()
    return {"access_token": data["access_token"], "token_type": "bearer", "user": data.get("user")}