from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tradingbot.api.dependencies import db_session_dependency
from tradingbot.api.main import create_app
from tradingbot.config import get_settings
from tradingbot.db import Base
from tradingbot.security import create_csrf_token, verify_csrf_token
from tradingbot.services.http_controls import SlidingWindowRateLimiter


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ADMIN_EMAIL", "phase10-admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "phase10-secret")
    monkeypatch.setenv("SESSION_SECRET", "phase10-session-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("REQUEST_BODY_MAX_BYTES", "256")
    monkeypatch.setenv("STREAM_POLL_INTERVAL_SECONDS", "1")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    app = create_app()

    def _override_db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[db_session_dependency] = _override_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _login(client: TestClient) -> str:
    response = client.post(
        "/auth/login",
        json={"email": "phase10-admin@example.com", "password": "phase10-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    return str(payload["csrf_token"])


def test_phase10_csrf_token_round_trip() -> None:
    token = create_csrf_token("phase10-session")

    assert verify_csrf_token(token, session_id="phase10-session") is True
    assert verify_csrf_token(token, session_id="other-session") is False


def test_phase10_rate_limiter_blocks_after_budget_exhausted() -> None:
    limiter = SlidingWindowRateLimiter()

    first = limiter.consume("phase10", limit=2, window_seconds=60)
    second = limiter.consume("phase10", limit=2, window_seconds=60)
    third = limiter.consume("phase10", limit=2, window_seconds=60)

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1


def test_phase10_mutating_auth_route_requires_csrf_header(api_client: TestClient) -> None:
    csrf_token = _login(api_client)

    blocked = api_client.post("/auth/logout")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "CSRF validation failed."

    allowed = api_client.post("/auth/logout", headers={"x-csrf-token": csrf_token})
    assert allowed.status_code == 200
    assert allowed.json()["authenticated"] is False


def test_phase10_authenticated_get_keeps_csrf_header_cookie_pair_usable(api_client: TestClient) -> None:
    _login(api_client)

    summary = api_client.get("/performance/summary?window_minutes=60")
    assert summary.status_code == 200
    rotated_token = summary.headers.get("x-csrf-token")
    assert isinstance(rotated_token, str)
    assert rotated_token

    logout = api_client.post("/auth/logout", headers={"x-csrf-token": rotated_token})
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False


def test_phase10_request_size_limit_blocks_large_mutating_payload(api_client: TestClient) -> None:
    csrf_token = _login(api_client)

    response = api_client.post("/auth/logout", headers={"x-csrf-token": csrf_token}, content=b"x" * 1024)

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body exceeds the configured limit."


def test_phase10_operations_stream_emits_snapshot(api_client: TestClient) -> None:
    _login(api_client)

    with api_client.stream("GET", "/stream/operations") as response:
        assert response.status_code == 200
        chunks = []
        for chunk in response.iter_text():
            if chunk:
                chunks.append(chunk)
            if any("operations.snapshot" in item for item in chunks):
                break

    assert any("operations.snapshot" in item for item in chunks)
