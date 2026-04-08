from __future__ import annotations

import pytest

from tradingbot.config import Settings, validate_runtime_settings


def test_phase1_validation_blocks_default_secret_in_production() -> None:
    settings = Settings(environment="production", session_secret="change-me")

    with pytest.raises(ValueError, match="SESSION_SECRET"):
        validate_runtime_settings(settings, service_name="api")


def test_phase1_validation_requires_separate_live_credentials_when_enabled() -> None:
    settings = Settings(
        environment="production",
        session_secret="a-very-long-production-session-secret",
        session_cookie_secure=True,
        allow_live_trading=True,
        alpaca_paper_api_key="paper-key",
        alpaca_paper_api_secret="paper-secret",
        alpaca_live_api_key="paper-key",
        alpaca_live_api_secret="paper-secret",
    )

    with pytest.raises(ValueError, match="must be separate"):
        validate_runtime_settings(settings, service_name="worker")


def test_phase1_validation_requires_live_credentials_when_live_enabled() -> None:
    settings = Settings(
        environment="production",
        session_secret="a-very-long-production-session-secret",
        session_cookie_secure=True,
        allow_live_trading=True,
        alpaca_paper_api_key="paper-key",
        alpaca_paper_api_secret="paper-secret",
    )

    with pytest.raises(ValueError, match="live broker credentials are required"):
        validate_runtime_settings(settings, service_name="worker")
