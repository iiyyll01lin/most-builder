from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import LoginRequest, TokenResponse, UserSummary
from ddm_v2.services.auth_service import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, store: JsonStore = Depends(get_store)) -> TokenResponse:
    user = store.state["users"].get(payload.username)
    if user is None or user["password"] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user=UserSummary(id=user["id"], username=user["username"], role=user["role"], name=user["name"]),
    )


@router.get("/me", response_model=UserSummary)
def me(user: dict = Depends(get_current_user)) -> UserSummary:
    return UserSummary(id=user["id"], username=user["username"], role=user["role"], name=user["name"])
