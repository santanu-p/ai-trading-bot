from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from tradingbot.config import get_settings
from tradingbot.db import get_db_session
from tradingbot.enums import OperatorRole
from tradingbot.models import OperatorSession
from tradingbot.security import decode_signed_session, verify_password


@dataclass(frozen=True)
class ConfiguredUser:
    email: str
    role: OperatorRole
    password: str | None = None
    password_hash: str | None = None


@dataclass(frozen=True)
class CurrentActor:
    email: str
    role: OperatorRole
    session_id: str
    expires_at: datetime


def db_session_dependency() -> Generator[Session, None, None]:
    yield from get_db_session()


def _configured_users() -> dict[str, ConfiguredUser]:
    settings = get_settings()
    users = {
        settings.admin_email: ConfiguredUser(
            email=settings.admin_email,
            role=OperatorRole.ADMIN,
            password=settings.admin_password,
            password_hash=settings.admin_password_hash,
        )
    }
    if settings.operator_email:
        users[settings.operator_email] = ConfiguredUser(
            email=settings.operator_email,
            role=OperatorRole.OPERATOR,
            password=settings.operator_password,
            password_hash=settings.operator_password_hash,
        )
    if settings.reviewer_email:
        users[settings.reviewer_email] = ConfiguredUser(
            email=settings.reviewer_email,
            role=OperatorRole.REVIEWER,
            password=settings.reviewer_password,
            password_hash=settings.reviewer_password_hash,
        )
    return users


def authenticate_user(email: str, password: str) -> ConfiguredUser | None:
    user = _configured_users().get(email)
    if user is None:
        return None
    if user.password_hash:
        return user if verify_password(password, user.password_hash) else None
    if user.password is None:
        return None
    return user if user.password == password else None


def get_current_operator(
    request: Request,
    session: Session = Depends(db_session_dependency),
) -> CurrentActor:
    settings = get_settings()
    raw_cookie = request.cookies.get(settings.session_cookie_name)
    if not raw_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    payload = decode_signed_session(raw_cookie)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

    session_id = payload.get("sid")
    email = payload.get("sub")
    role = payload.get("role")
    if not isinstance(session_id, str) or not isinstance(email, str) or not isinstance(role, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload.")

    session_row = session.get(OperatorSession, session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked.")
    expires_at = session_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired.")

    session_row.last_seen_at = datetime.now(UTC)
    session.commit()

    try:
        resolved_role = OperatorRole(role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session role.") from exc

    return CurrentActor(
        email=email,
        role=resolved_role,
        session_id=session_row.id,
        expires_at=expires_at,
    )


def require_roles(*roles: OperatorRole) -> Callable[[CurrentActor], CurrentActor]:
    allowed = set(roles)

    def dependency(current: CurrentActor = Depends(get_current_operator)) -> CurrentActor:
        if current.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return current

    return dependency
