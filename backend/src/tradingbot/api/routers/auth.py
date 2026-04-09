from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, authenticate_user, db_session_dependency, get_current_operator, require_roles
from tradingbot.config import get_settings
from tradingbot.enums import OperatorRole
from tradingbot.models import AuditLog, OperatorSession
from tradingbot.schemas.auth import LoginRequest, LoginResponse, SessionResponse
from tradingbot.security import create_access_token, create_csrf_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        expires=expires_at,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _set_csrf_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        max_age=max_age,
        expires=expires_at,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers[settings.csrf_header_name] = token


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", samesite="lax")


def _clear_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.csrf_cookie_name, path="/", samesite="lax")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(db_session_dependency),
) -> LoginResponse:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.session_expire_minutes)
    session_row = OperatorSession(
        email=user.email,
        role=user.role,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        last_seen_at=datetime.now(UTC),
    )
    session.add(session_row)
    session.flush()
    session.add(
        AuditLog(
            action="auth.login",
            actor=user.email,
            actor_role=user.role.value,
            session_id=session_row.id,
            details={},
        )
    )
    session.commit()
    token = create_access_token(user.email, role=user.role.value, session_id=session_row.id, expires_at=expires_at)
    csrf_token = create_csrf_token(session_row.id, expires_at=expires_at)
    _set_session_cookie(response, token, expires_at)
    _set_csrf_cookie(response, csrf_token, expires_at)
    return LoginResponse(
        authenticated=True,
        email=user.email,
        role=user.role,
        expires_at=expires_at,
        session_id=session_row.id,
        csrf_token=csrf_token,
    )


@router.get("/me", response_model=LoginResponse)
def who_am_i(response: Response, current: CurrentActor = Depends(get_current_operator)) -> LoginResponse:
    csrf_token = create_csrf_token(current.session_id, expires_at=current.expires_at)
    _set_csrf_cookie(response, csrf_token, current.expires_at)
    return LoginResponse(
        authenticated=True,
        email=current.email,
        role=current.role,
        expires_at=current.expires_at,
        session_id=current.session_id,
        csrf_token=csrf_token,
    )


@router.post("/logout", response_model=LoginResponse)
def logout(
    response: Response,
    current: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> LoginResponse:
    session_row = session.get(OperatorSession, current.session_id)
    if session_row is not None and session_row.revoked_at is None:
        session_row.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                action="auth.logout",
                actor=current.email,
                actor_role=current.role.value,
                session_id=current.session_id,
                details={},
            )
        )
        session.commit()
    _clear_session_cookie(response)
    _clear_csrf_cookie(response)
    return LoginResponse(
        authenticated=False,
        email=current.email,
        role=current.role,
        expires_at=current.expires_at,
        session_id=current.session_id,
        csrf_token=None,
    )


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    email: str | None = None,
    current: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[SessionResponse]:
    query = select(OperatorSession).order_by(OperatorSession.created_at.desc())
    if current.role != OperatorRole.ADMIN:
        query = query.where(OperatorSession.email == current.email)
    elif email:
        query = query.where(OperatorSession.email == email)
    rows = session.scalars(query).all()
    return [
        SessionResponse(
            session_id=row.id,
            email=row.email,
            role=row.role,
            expires_at=row.expires_at,
            current=row.id == current.session_id,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            last_seen_at=row.last_seen_at,
            revoked_at=row.revoked_at,
        )
        for row in rows
    ]


@router.post("/sessions/{session_id}/revoke", response_model=SessionResponse)
def revoke_session(
    session_id: str,
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> SessionResponse:
    session_row = session.get(OperatorSession, session_id)
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if session_row.revoked_at is None:
        session_row.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                action="auth.force_logout",
                actor=current.email,
                actor_role=current.role.value,
                session_id=current.session_id,
                details={"target_session_id": session_id, "target_email": session_row.email},
            )
        )
        session.commit()
    return SessionResponse(
        session_id=session_row.id,
        email=session_row.email,
        role=session_row.role,
        expires_at=session_row.expires_at,
        current=session_row.id == current.session_id,
        user_agent=session_row.user_agent,
        ip_address=session_row.ip_address,
        last_seen_at=session_row.last_seen_at,
        revoked_at=session_row.revoked_at,
    )
