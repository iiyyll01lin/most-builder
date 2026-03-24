from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import UserRole
from ddm_v2.services.auth_service import decode_access_token

security = HTTPBearer()


def get_store(request: Request) -> JsonStore:
    return request.app.state.store


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    store: JsonStore = Depends(get_store),
) -> dict:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = store.state["users"].get(username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in {role.value for role in allowed_roles}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user

    return dependency
