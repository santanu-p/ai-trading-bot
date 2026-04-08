from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return float(raw_value)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


def _env_csv(name: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, "")
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Trading Bot")
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/tradingbot",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    session_secret: str = os.getenv("SESSION_SECRET", os.getenv("JWT_SECRET", "change-me"))
    session_expire_minutes: int = _env_int("SESSION_EXPIRE_MINUTES", _env_int("JWT_EXPIRE_MINUTES", 720))
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "tradingbot_session")
    session_cookie_secure: bool = _env_bool("SESSION_COOKIE_SECURE", os.getenv("ENVIRONMENT", "development") != "development")
    admin_email: str = field(default_factory=lambda: os.getenv("ADMIN_EMAIL", "admin@example.com"))
    admin_password: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD"))
    admin_password_hash: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD_HASH"))
    operator_email: str | None = field(default_factory=lambda: os.getenv("OPERATOR_EMAIL"))
    operator_password: str | None = field(default_factory=lambda: os.getenv("OPERATOR_PASSWORD"))
    operator_password_hash: str | None = field(default_factory=lambda: os.getenv("OPERATOR_PASSWORD_HASH"))
    reviewer_email: str | None = field(default_factory=lambda: os.getenv("REVIEWER_EMAIL"))
    reviewer_password: str | None = field(default_factory=lambda: os.getenv("REVIEWER_PASSWORD"))
    reviewer_password_hash: str | None = field(default_factory=lambda: os.getenv("REVIEWER_PASSWORD_HASH"))
    web_origin: str = os.getenv("WEB_ORIGIN", "http://localhost:3000")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    alpaca_api_key: str | None = os.getenv("ALPACA_API_KEY")
    alpaca_api_secret: str | None = os.getenv("ALPACA_API_SECRET")
    alpaca_paper_base_url: str = os.getenv(
        "ALPACA_PAPER_BASE_URL",
        "https://paper-api.alpaca.markets",
    )
    alpaca_live_base_url: str = os.getenv(
        "ALPACA_LIVE_BASE_URL",
        "https://api.alpaca.markets",
    )
    alpaca_data_base_url: str = os.getenv(
        "ALPACA_DATA_BASE_URL",
        "https://data.alpaca.markets",
    )
    alpaca_market_data_feed: str = os.getenv("ALPACA_MARKET_DATA_FEED", "iex")
    market_timezone: str = os.getenv("MARKET_TIMEZONE", "America/New_York")
    scan_interval_minutes: int = _env_int("SCAN_INTERVAL_MINUTES", 5)
    consensus_threshold: float = _env_float("CONSENSUS_THRESHOLD", 0.64)
    min_approval_votes: int = _env_int("MIN_APPROVAL_VOTES", 2)
    allow_live_trading: bool = _env_bool("ALLOW_LIVE_TRADING", False)
    live_trading_allowed_brokers: tuple[str, ...] = _env_csv("LIVE_TRADING_ALLOWED_BROKERS")
    live_enable_code_ttl_minutes: int = _env_int("LIVE_ENABLE_CODE_TTL_MINUTES", 10)
    intraday_flatten_buffer_minutes: int = _env_int("INTRADAY_FLATTEN_BUFFER_MINUTES", 15)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
