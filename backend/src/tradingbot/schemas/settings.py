from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tradingbot.enums import (
    BotStatus,
    BrokerSlug,
    InstrumentClass,
    MarketUniverse,
    RiskProfile,
    StrategyFamily,
    TradingMode,
    TradingPattern,
)


class TradingProfile(BaseModel):
    trading_pattern: TradingPattern | None = None
    instrument_class: InstrumentClass | None = None
    strategy_family: StrategyFamily | None = None
    risk_profile: RiskProfile | None = None
    market_universe: MarketUniverse | None = None
    profile_notes: str = ""


class BrokerSettings(BaseModel):
    broker: BrokerSlug = BrokerSlug.ALPACA
    account_type: str = Field(default="cash", min_length=1, max_length=40)
    venue: str = Field(default="US equities", min_length=1, max_length=80)
    timezone: str = Field(default="America/New_York", min_length=1, max_length=80)
    base_currency: str = Field(default="USD", min_length=1, max_length=12)
    permissions: list[str] = Field(default_factory=list)


class BrokerCapability(BaseModel):
    key: str
    label: str
    description: str
    supported: bool


class MarketSessionResponse(BaseModel):
    venue: str
    timezone: str
    status: str
    reason: str | None = None
    is_half_day: bool = False
    can_scan: bool
    can_submit_orders: bool
    should_flatten_positions: bool
    session_opens_at: datetime | None = None
    session_closes_at: datetime | None = None
    next_session_opens_at: datetime | None = None


class BotSettingsResponse(BaseModel):
    status: BotStatus
    mode: TradingMode
    kill_switch_enabled: bool
    live_enabled: bool
    live_trading_env_allowed: bool
    scan_interval_minutes: int
    consensus_threshold: float
    max_open_positions: int
    max_daily_loss_pct: float
    max_position_risk_pct: float
    max_symbol_notional_pct: float
    symbol_cooldown_minutes: int
    openai_model: str
    watchlist: list[str]
    broker_settings: BrokerSettings
    broker_capability_matrix: list[BrokerCapability]
    selected_for_analysis: TradingProfile
    supported_for_execution: TradingProfile | None
    strategy_profile_completed: bool
    execution_support_status: str
    live_start_allowed: bool
    analysis_only_downgrade_reason: str | None
    market_session: MarketSessionResponse


class BotSettingsUpdate(BaseModel):
    scan_interval_minutes: int = Field(default=5, ge=1, le=60)
    consensus_threshold: float = Field(default=0.64, ge=0, le=1)
    max_open_positions: int = Field(default=6, ge=1, le=30)
    max_daily_loss_pct: float = Field(default=0.025, gt=0, le=0.25)
    max_position_risk_pct: float = Field(default=0.005, gt=0, le=0.05)
    max_symbol_notional_pct: float = Field(default=0.16, gt=0, le=0.5)
    symbol_cooldown_minutes: int = Field(default=45, ge=0, le=480)
    openai_model: str = Field(default="gpt-5-mini", min_length=1)
    watchlist: list[str] = Field(default_factory=list)
    broker_settings: BrokerSettings = Field(default_factory=BrokerSettings)
    selected_for_analysis: TradingProfile = Field(default_factory=TradingProfile)


class BotModeUpdate(BaseModel):
    mode: TradingMode


class BotStatusResponse(BaseModel):
    status: BotStatus
    mode: TradingMode
    kill_switch_enabled: bool
    live_enabled: bool
