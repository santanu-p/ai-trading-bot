from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


_KNOWN_ENVIRONMENTS = {"development", "test", "staging", "production"}


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
    csrf_cookie_name: str = os.getenv("CSRF_COOKIE_NAME", "tradingbot_csrf")
    csrf_header_name: str = os.getenv("CSRF_HEADER_NAME", "x-csrf-token")
    session_cookie_secure: bool = _env_bool("SESSION_COOKIE_SECURE", os.getenv("ENVIRONMENT", "development") != "development")
    csrf_origin_enforcement: bool = _env_bool("CSRF_ORIGIN_ENFORCEMENT", True)
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
    alpaca_paper_api_key: str | None = os.getenv("ALPACA_PAPER_API_KEY")
    alpaca_paper_api_secret: str | None = os.getenv("ALPACA_PAPER_API_SECRET")
    alpaca_live_api_key: str | None = os.getenv("ALPACA_LIVE_API_KEY")
    alpaca_live_api_secret: str | None = os.getenv("ALPACA_LIVE_API_SECRET")
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
    request_body_max_bytes: int = _env_int("REQUEST_BODY_MAX_BYTES", 1_000_000)
    api_rate_limit_per_minute: int = _env_int("API_RATE_LIMIT_PER_MINUTE", 240)
    auth_rate_limit_per_minute: int = _env_int("AUTH_RATE_LIMIT_PER_MINUTE", 20)
    rate_limit_window_seconds: int = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    stream_poll_interval_seconds: int = _env_int("STREAM_POLL_INTERVAL_SECONDS", 5)
    alert_webhook_urls: tuple[str, ...] = _env_csv("ALERT_WEBHOOK_URLS")
    alert_webhook_timeout_seconds: float = _env_float("ALERT_WEBHOOK_TIMEOUT_SECONDS", 5.0)

    @property
    def normalized_environment(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_production_like(self) -> bool:
        return self.normalized_environment in {"staging", "production"}

    def paper_broker_credentials(self) -> tuple[str | None, str | None]:
        return (
            self.alpaca_paper_api_key or self.alpaca_api_key,
            self.alpaca_paper_api_secret or self.alpaca_api_secret,
        )

    def live_broker_credentials(self) -> tuple[str | None, str | None]:
        return (
            self.alpaca_live_api_key or self.alpaca_api_key,
            self.alpaca_live_api_secret or self.alpaca_api_secret,
        )


def validate_runtime_settings(settings: Settings, *, service_name: str) -> None:
    env = settings.normalized_environment
    if env not in _KNOWN_ENVIRONMENTS:
        known = ", ".join(sorted(_KNOWN_ENVIRONMENTS))
        raise ValueError(f"{service_name} startup blocked: ENVIRONMENT must be one of {known}.")

    if bool(settings.alpaca_paper_api_key) != bool(settings.alpaca_paper_api_secret):
        raise ValueError(
            f"{service_name} startup blocked: ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET must be set together.",
        )
    if bool(settings.alpaca_live_api_key) != bool(settings.alpaca_live_api_secret):
        raise ValueError(
            f"{service_name} startup blocked: ALPACA_LIVE_API_KEY and ALPACA_LIVE_API_SECRET must be set together.",
        )

    if settings.is_production_like:
        if settings.session_secret.strip() in {"", "change-me"}:
            raise ValueError(f"{service_name} startup blocked: SESSION_SECRET must be set to a non-default value.")
        if len(settings.session_secret.strip()) < 32:
            raise ValueError(f"{service_name} startup blocked: SESSION_SECRET must be at least 32 characters.")
        if not settings.session_cookie_secure:
            raise ValueError(f"{service_name} startup blocked: SESSION_COOKIE_SECURE must be true outside development.")
        if not settings.csrf_origin_enforcement:
            raise ValueError(f"{service_name} startup blocked: CSRF_ORIGIN_ENFORCEMENT must stay enabled outside development.")

    paper_key, paper_secret = settings.paper_broker_credentials()
    live_key, live_secret = settings.live_broker_credentials()
    if settings.is_production_like and (not paper_key or not paper_secret):
        raise ValueError(
            f"{service_name} startup blocked: paper broker credentials are required in staging/production.",
        )
    if settings.allow_live_trading:
        if not live_key or not live_secret:
            raise ValueError(
                f"{service_name} startup blocked: "
                "live broker credentials are required when live trading is enabled.",
            )
        if (paper_key, paper_secret) == (live_key, live_secret):
            raise ValueError(
                f"{service_name} startup blocked: paper and live broker credentials must be separate when live trading is enabled.",
            )

    if settings.request_body_max_bytes <= 0:
        raise ValueError(f"{service_name} startup blocked: REQUEST_BODY_MAX_BYTES must be positive.")
    if settings.api_rate_limit_per_minute <= 0:
        raise ValueError(f"{service_name} startup blocked: API_RATE_LIMIT_PER_MINUTE must be positive.")
    if settings.auth_rate_limit_per_minute <= 0:
        raise ValueError(f"{service_name} startup blocked: AUTH_RATE_LIMIT_PER_MINUTE must be positive.")
    if settings.rate_limit_window_seconds <= 0:
        raise ValueError(f"{service_name} startup blocked: RATE_LIMIT_WINDOW_SECONDS must be positive.")
    if settings.stream_poll_interval_seconds <= 0:
        raise ValueError(f"{service_name} startup blocked: STREAM_POLL_INTERVAL_SECONDS must be positive.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
