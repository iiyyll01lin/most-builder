from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from ddm_v2.settings import ACCESS_TOKEN_EXPIRE_HOURS, SECRET_KEY


def create_access_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "exp": datetime.now(UTC) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
