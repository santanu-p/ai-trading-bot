from __future__ import annotations

import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Trading Bot")
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/tradingbot",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = _env_int("JWT_EXPIRE_MINUTES", 720)
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password: str | None = os.getenv("ADMIN_PASSWORD")
    admin_password_hash: str | None = os.getenv("ADMIN_PASSWORD_HASH")
    web_origin: str = os.getenv("WEB_ORIGIN", "http://localhost:3000")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
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
    auto_create_tables: bool = _env_bool("AUTO_CREATE_TABLES", True)
    market_timezone: str = os.getenv("MARKET_TIMEZONE", "America/New_York")
    scan_interval_minutes: int = _env_int("SCAN_INTERVAL_MINUTES", 5)
    consensus_threshold: float = _env_float("CONSENSUS_THRESHOLD", 0.64)
    min_approval_votes: int = _env_int("MIN_APPROVAL_VOTES", 2)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
