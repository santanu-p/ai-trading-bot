from __future__ import annotations

from pydantic import BaseModel, Field

from tradingbot.enums import (
    BotStatus,
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


class BotSettingsResponse(BaseModel):
    status: BotStatus
    mode: TradingMode
    kill_switch_enabled: bool
    scan_interval_minutes: int
    consensus_threshold: float
    max_open_positions: int
    max_daily_loss_pct: float
    max_position_risk_pct: float
    max_symbol_notional_pct: float
    symbol_cooldown_minutes: int
    openai_model: str
    watchlist: list[str]
    trading_profile: TradingProfile
    strategy_profile_completed: bool
    execution_support_status: str


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
    trading_profile: TradingProfile = Field(default_factory=TradingProfile)


class BotModeUpdate(BaseModel):
    mode: TradingMode


class BotStatusResponse(BaseModel):
    status: BotStatus
    mode: TradingMode
    kill_switch_enabled: bool
