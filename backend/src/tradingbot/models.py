from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingbot.db import Base
from tradingbot.enums import (
    BotStatus,
    BrokerSlug,
    ExecutionIntentStatus,
    ExecutionIntentType,
    InstrumentClass,
    MarketUniverse,
    OperatorRole,
    OptionRight,
    OrderIntent,
    OrderStatus,
    OrderType,
    RiskProfile,
    RunStatus,
    StrategyFamily,
    TimeInForce,
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
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    live_enable_code_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    live_enable_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class OperatorSession(Base, TimestampMixin):
    __tablename__ = "operator_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[OperatorRole] = mapped_column(Enum(OperatorRole))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.QUEUED)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_versions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
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


class BacktestReport(Base, TimestampMixin):
    __tablename__ = "backtest_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    initial_equity: Mapped[float] = mapped_column(Float, default=100_000)
    slippage_bps: Mapped[float] = mapped_column(Float, default=5.0)
    commission_per_share: Mapped[float] = mapped_column(Float, default=0.005)
    fill_delay_bars: Mapped[int] = mapped_column(Integer, default=1)
    reject_probability: Mapped[float] = mapped_column(Float, default=0.03)
    max_holding_bars: Mapped[int] = mapped_column(Integer, default=24)
    random_seed: Mapped[int] = mapped_column(Integer, default=42)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    rejected_orders: Mapped[int] = mapped_column(Integer, default=0)
    final_equity: Mapped[float] = mapped_column(Float, default=0.0)
    total_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    expectancy: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    turnover: Mapped[float] = mapped_column(Float, default=0.0)
    avg_exposure_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_exposure_pct: Mapped[float] = mapped_column(Float, default=0.0)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    walk_forward_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    regime_breakdown_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    equity_curve_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    symbol_breakdown_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("backtest_reports.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    regime: Mapped[str] = mapped_column(String(24), index=True)
    signal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    holding_bars: Mapped[int] = mapped_column(Integer, default=0)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    commission_paid: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_paid: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)

    report: Mapped[BacktestReport] = relationship(back_populates="trades")


class ExecutionIntent(Base, TimestampMixin):
    __tablename__ = "execution_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, unique=True, index=True)
    intent_type: Mapped[ExecutionIntentType] = mapped_column(Enum(ExecutionIntentType), default=ExecutionIntentType.TRADE)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode))
    status: Mapped[ExecutionIntentStatus] = mapped_column(
        Enum(ExecutionIntentStatus),
        default=ExecutionIntentStatus.PENDING_APPROVAL,
        index=True,
    )
    symbol: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    direction: Mapped[OrderIntent | None] = mapped_column(Enum(OrderIntent), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    decision_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class OrderRecord(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_intent_id: Mapped[str | None] = mapped_column(ForeignKey("execution_intents.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode))
    direction: Mapped[OrderIntent] = mapped_column(Enum(OrderIntent))
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), default=OrderType.BRACKET)
    time_in_force: Mapped[TimeInForce] = mapped_column(Enum(TimeInForce), default=TimeInForce.DAY)
    quantity: Mapped[int] = mapped_column(Integer)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.NEW, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_order_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    parent_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    replaced_by_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_broker_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    state_transitions: Mapped[list["OrderStateTransition"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        foreign_keys="OrderStateTransition.order_id",
    )
    fills: Mapped[list["OrderFill"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        foreign_keys="OrderFill.order_id",
    )


class OrderStateTransition(Base):
    __tablename__ = "order_state_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    from_status: Mapped[OrderStatus | None] = mapped_column(Enum(OrderStatus), nullable=True)
    to_status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), index=True)
    transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    source: Mapped[str] = mapped_column(String(24), default="local")
    broker_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    order: Mapped[OrderRecord] = relationship(back_populates="state_transitions", foreign_keys=[order_id])


class OrderFill(Base):
    __tablename__ = "order_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    broker_fill_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    order: Mapped[OrderRecord] = relationship(back_populates="fills", foreign_keys=[order_id])


class PositionRecord(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    average_entry_price: Mapped[float] = mapped_column(Float)
    market_value: Mapped[float] = mapped_column(Float)
    unrealized_pl: Mapped[float] = mapped_column(Float, default=0)
    side: Mapped[str] = mapped_column(String(12), default="long")
    broker_position_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class InstrumentContract(Base, TimestampMixin):
    __tablename__ = "instrument_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    instrument_class: Mapped[InstrumentClass] = mapped_column(Enum(InstrumentClass), index=True)
    underlying_symbol: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    exchange: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    tick_size: Mapped[float] = mapped_column(Float, default=0.01)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    contract_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    strike_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    option_right: Mapped[OptionRight | None] = mapped_column(Enum(OptionRight), nullable=True)
    shortable: Mapped[bool] = mapped_column(Boolean, default=False)
    option_chain_available: Mapped[bool] = mapped_column(Boolean, default=False)
    price_band_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_band_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ReconciliationMismatch(Base, TimestampMixin):
    __tablename__ = "reconciliation_mismatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_slug: Mapped[BrokerSlug] = mapped_column(Enum(BrokerSlug), index=True)
    symbol: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    mismatch_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(12), default="critical")
    local_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    broker_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class TradeReview(Base, TimestampMixin):
    __tablename__ = "trade_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, unique=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    prompt_versions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_score: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    loss_cause: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    recurring_pattern_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    review_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
