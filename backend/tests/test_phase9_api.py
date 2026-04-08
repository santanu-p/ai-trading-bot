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


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ADMIN_EMAIL", "phase9-admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "phase9-secret")
    monkeypatch.setenv("SESSION_SECRET", "phase9-session-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
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


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "phase9-admin@example.com", "password": "phase9-secret"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_phase9_health_endpoint_propagates_request_id(api_client: TestClient) -> None:
    response = api_client.get("/health", headers={"x-request-id": "phase9-request-id"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("x-request-id") == "phase9-request-id"


def test_phase9_auth_session_and_observability_endpoints(api_client: TestClient) -> None:
    unauthenticated = api_client.get("/performance/summary")
    assert unauthenticated.status_code == 401

    _login(api_client)

    who_am_i = api_client.get("/auth/me")
    assert who_am_i.status_code == 200
    assert who_am_i.json()["email"] == "phase9-admin@example.com"

    summary = api_client.get("/performance/summary?window_minutes=60")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["window_minutes"] == 60
    assert isinstance(payload["counters"], list)
    assert isinstance(payload["latencies"], list)

    alerts = api_client.get("/alerts?limit=12")
    assert alerts.status_code == 200
    assert isinstance(alerts.json(), list)

    logout = api_client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False

    post_logout = api_client.get("/auth/me")
    assert post_logout.status_code == 401
