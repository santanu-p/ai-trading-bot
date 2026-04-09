from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from tradingbot.enums import OperatorRole


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionResponse(BaseModel):
    session_id: str
    email: str
    role: OperatorRole
    expires_at: datetime
    current: bool = False
    user_agent: str | None = None
    ip_address: str | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None


class LoginResponse(BaseModel):
    authenticated: bool
    email: str
    role: OperatorRole
    expires_at: datetime
    session_id: str
    csrf_token: str | None = None
