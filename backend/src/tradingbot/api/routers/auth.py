from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from tradingbot.api.dependencies import authenticate_admin
from tradingbot.config import get_settings
from tradingbot.schemas.auth import LoginRequest, LoginResponse
from tradingbot.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if not authenticate_admin(payload.email, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    settings = get_settings()
    return LoginResponse(
        access_token=create_access_token(payload.email),
        expires_in_minutes=settings.jwt_expire_minutes,
    )

