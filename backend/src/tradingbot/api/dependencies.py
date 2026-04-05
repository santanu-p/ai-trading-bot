from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from tradingbot.config import get_settings
from tradingbot.db import get_db_session
from tradingbot.security import decode_access_token, verify_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def db_session_dependency() -> Generator[Session, None, None]:
    yield from get_db_session()


def authenticate_admin(email: str, password: str) -> bool:
    settings = get_settings()
    if email != settings.admin_email:
        return False
    if settings.admin_password_hash:
        return verify_password(password, settings.admin_password_hash)
    return settings.admin_password == password


def get_current_operator(token: str = Depends(oauth2_scheme)) -> str:
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    return subject

