from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from ddm_v2.settings import get_settings


def create_access_token(user: dict) -> str:
    settings = get_settings()
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "exp": datetime.now(UTC) + timedelta(hours=settings.access_token_expire_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
