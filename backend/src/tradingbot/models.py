from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingbot.db import Base
from tradingbot.enums import (
    BotStatus,
    BrokerSlug,
    InstrumentClass,
    MarketUniverse,
    OrderIntent,
    RiskProfile,
    RunStatus,
    StrategyFamily,
    TradingMode,
    TradingPattern,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class BotSettings(Base, TimestampMixin):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[BotStatus] = mapped_column(Enum(BotStatus), default=BotStatus.STOPPED)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode), default=TradingMode.PAPER)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    consensus_threshold: Mapped[float] = mapped_column(Float, default=0.64)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=6)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=0.025)
    max_position_risk_pct: Mapped[float] = mapped_column(Float, default=0.005)
    max_symbol_notional_pct: Mapped[float] = mapped_column(Float, default=0.16)
    symbol_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=45)
    openai_model: Mapped[str] = mapped_column(String(100), default="gpt-5-mini")
    broker_slug: Mapped[BrokerSlug] = mapped_column(Enum(BrokerSlug), default=BrokerSlug.ALPACA)
    broker_account_type: Mapped[str] = mapped_column(String(40), default="cash")
    broker_venue: Mapped[str] = mapped_column(String(80), default="US equities")
    broker_timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    broker_base_currency: Mapped[str] = mapped_column(String(12), default="USD")
    broker_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    trading_pattern: Mapped[TradingPattern | None] = mapped_column(Enum(TradingPattern), nullable=True)
    instrument_class: Mapped[InstrumentClass | None] = mapped_column(Enum(InstrumentClass), nullable=True)
    strategy_family: Mapped[StrategyFamily | None] = mapped_column(Enum(StrategyFamily), nullable=True)
    risk_profile: Mapped[RiskProfile | None] = mapped_column(Enum(RiskProfile), nullable=True)
    market_universe: Mapped[MarketUniverse | None] = mapped_column(Enum(MarketUniverse), nullable=True)
    profile_notes: Mapped[str] = mapped_column(Text, default="")
    analysis_only_downgrade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class WatchlistSymbol(Base, TimestampMixin):
    __tablename__ = "watchlist_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.QUEUED)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    trade_candidates: Mapped[list["TradeCandidate"]] = relationship(back_populates="run")


class TradeCandidate(Base, TimestampMixin):
    __tablename__ = "trade_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    direction: Mapped[OrderIntent] = mapped_column(Enum(OrderIntent))
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    thesis: Mapped[str] = mapped_column(Text)
    entry: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    risk_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[AgentRun] = relationship(back_populates="trade_candidates")


class OrderRecord(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode))
    direction: Mapped[OrderIntent] = mapped_column(Enum(OrderIntent))
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), index=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class PositionRecord(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    average_entry_price: Mapped[float] = mapped_column(Float)
    market_value: Mapped[float] = mapped_column(Float)
    unrealized_pl: Mapped[float] = mapped_column(Float, default=0)
    side: Mapped[str] = mapped_column(String(12), default="long")


class RiskEvent(Base, TimestampMixin):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(12), default="warning")
    code: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class PortfolioSnapshot(Base, TimestampMixin):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    buying_power: Mapped[float] = mapped_column(Float)
    daily_pl: Mapped[float] = mapped_column(Float)
    exposure: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="alpaca")


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
