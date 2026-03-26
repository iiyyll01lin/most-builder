from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.db.database import get_session
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.schemas import UserRole
from ddm_v2.services.auth_service import decode_access_token

security = HTTPBearer()


async def get_store(session: AsyncSession = Depends(get_session)) -> PostgresStore:
    """FastAPI dependency — yields a ``PostgresStore`` bound to the request session."""
    return PostgresStore(session)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    store: PostgresStore = Depends(get_store),
) -> dict:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = await store.get_user_by_username(username) if username else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in {role.value for role in allowed_roles}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user

    return dependency

