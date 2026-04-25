from __future__ import annotations

from typing import Any

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from tradingbot.enums import (
    ExecutionIntentStatus,
    ExecutionIntentType,
    OperatorRole,
    OrderIntent,
    OrderStatus,
    OrderType,
    RiskDecision,
    RunStatus,
    TimeInForce,
    TradingMode,
)


class AgentDecision(BaseModel):
    role: str
    symbol: str
    direction: OrderIntent
    confidence: float = Field(ge=0, le=1)
    thesis: str
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    time_horizon: str
    vote: str
    reject_reason: str | None = None
    supporting_facts: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class ChairSummary(BaseModel):
    symbol: str
    direction: OrderIntent
    confidence: float = Field(ge=0, le=1)
    time_horizon: str
    vote: str
    summary: str
    dissenting_risks: list[str] = Field(default_factory=list)


class CommitteeDecision(BaseModel):
    symbol: str
    direction: OrderIntent
    confidence: float = Field(ge=0, le=1)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    time_horizon: str
    status: RiskDecision
    thesis: str
    reject_reason: str | None = None
    market_vote: str | None = None
    news_vote: str | None = None
    chair_vote: str | None = None
    risk_notes: list[str] = Field(default_factory=list)
    committee_notes: list[str] = Field(default_factory=list)
    agent_signals: list[AgentDecision] = Field(default_factory=list)
    model_name: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class RiskCheckResult(BaseModel):
    decision: RiskDecision
    approved_quantity: int = 0
    notes: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    id: str
    profile_id: int
    symbol: str
    status: RunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    decision_payload: dict | None = None


class ExecutionIntentResponse(BaseModel):
    id: str
    profile_id: int
    source_run_id: str | None = None
    intent_type: ExecutionIntentType
    mode: TradingMode
    status: ExecutionIntentStatus
    symbol: str | None = None
    direction: OrderIntent | None = None
    quantity: int | None = None
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    requires_human_approval: bool
    block_reason: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    failed_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    profile_id: int
    symbol: str
    mode: TradingMode
    direction: OrderIntent
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: int
    filled_quantity: int
    average_fill_price: float | None = None
    limit_price: float | None = None
    stop_loss: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    trailing_percent: float | None = None
    trailing_amount: float | None = None
    status: OrderStatus
    status_reason: str | None = None
    client_order_id: str
    broker_order_id: str | None = None
    parent_order_id: int | None = None
    replaced_by_order_id: int | None = None
    submitted_at: datetime | None = None
    last_broker_update_at: datetime | None = None


class OrderTransitionResponse(BaseModel):
    id: int
    profile_id: int
    order_id: int
    symbol: str
    from_status: OrderStatus | None = None
    to_status: OrderStatus
    transition_at: datetime
    source: str
    broker_event_id: str | None = None
    message: str
    payload: dict


class OrderFillResponse(BaseModel):
    id: int
    profile_id: int
    order_id: int
    broker_fill_id: str | None = None
    broker_order_id: str | None = None
    symbol: str
    side: str
    quantity: int
    price: float
    fee: float
    filled_at: datetime
    payload: dict


class PositionResponse(BaseModel):
    id: int
    profile_id: int
    symbol: str
    quantity: int
    average_entry_price: float
    market_value: float
    unrealized_pl: float
    side: str


class RiskEventResponse(BaseModel):
    id: int
    profile_id: int | None = None
    symbol: str | None = None
    severity: str
    code: str
    message: str
    payload: dict
    created_at: datetime


class MetricCounterResponse(BaseModel):
    name: str
    value: float
    tags: dict[str, str] = Field(default_factory=dict)


class MetricLatencyResponse(BaseModel):
    name: str
    samples: int
    avg_ms: float
    p95_ms: float
    max_ms: float
    tags: dict[str, str] = Field(default_factory=dict)


class PerformanceSummaryResponse(BaseModel):
    window_minutes: int
    total_trade_candidates: int
    rejected_trade_candidates: int
    rejection_rate: float
    malformed_events: int
    scan_failures: int
    kill_switch_enabled: bool
    live_enabled: bool
    mode: TradingMode
    portfolio_position_count: int = 0
    portfolio_gross_exposure: float = 0.0
    portfolio_net_exposure: float = 0.0
    portfolio_largest_position_notional: float = 0.0
    latest_equity: float = 0.0
    latest_buying_power: float = 0.0
    latest_daily_pl: float = 0.0
    counters: list[MetricCounterResponse] = Field(default_factory=list)
    latencies: list[MetricLatencyResponse] = Field(default_factory=list)


class ExecutionQualitySampleResponse(BaseModel):
    id: int
    order_id: int
    profile_id: int
    symbol: str
    broker_slug: str
    venue: str
    order_type: OrderType
    side: OrderIntent
    outcome_status: OrderStatus
    quantity: int
    filled_quantity: int
    fill_ratio: float
    intended_price: float | None = None
    realized_price: float | None = None
    expected_slippage_bps: float | None = None
    realized_slippage_bps: float | None = None
    expected_spread_bps: float | None = None
    spread_cost: float
    notional: float
    time_to_fill_seconds: float | None = None
    aggressiveness: str | None = None
    quality_score: float
    payload: dict[str, Any]
    created_at: datetime


class ExecutionQualitySummaryResponse(BaseModel):
    dimension: str
    key: str
    sample_count: int
    filled_count: int
    cancel_rate: float
    reject_rate: float
    avg_expected_slippage_bps: float
    avg_realized_slippage_bps: float
    avg_spread_cost: float
    avg_time_to_fill_seconds: float
    avg_fill_ratio: float
    avg_quality_score: float


class AuditLogResponse(BaseModel):
    id: int
    action: str
    actor: str
    actor_role: str
    session_id: str | None = None
    details: dict
    created_at: datetime


class ReconciliationMismatchResponse(BaseModel):
    id: int
    profile_id: int
    broker_slug: str
    symbol: str | None = None
    mismatch_type: str
    severity: str
    local_reference: str | None = None
    broker_reference: str | None = None
    details: dict
    resolved: bool
    resolved_at: datetime | None = None
    created_at: datetime


class OrderReplaceRequest(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    time_in_force: TimeInForce | None = None


class BacktestRequest(BaseModel):
    profile_id: int | None = Field(default=None, ge=1)
    symbols: list[str]
    start: datetime
    end: datetime
    interval_minutes: int = Field(default=5, ge=1, le=60)
    initial_equity: float = Field(default=100_000, gt=0)
    slippage_bps: float = Field(default=5.0, ge=0, le=200)
    commission_per_share: float = Field(default=0.005, ge=0, le=10)
    fill_delay_bars: int = Field(default=1, ge=0, le=20)
    reject_probability: float = Field(default=0.03, ge=0, le=1)
    max_holding_bars: int = Field(default=24, ge=1, le=500)
    random_seed: int = Field(default=42, ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_window(self) -> "BacktestRequest":
        if self.end <= self.start:
            raise ValueError("Backtest end must be after start.")
        return self


class BacktestResponse(BaseModel):
    accepted: bool
    task_id: str
    report_id: str


class BacktestSummaryResponse(BaseModel):
    id: str
    profile_id: int
    task_id: str | None = None
    status: str
    symbols: list[str]
    start_at: datetime
    end_at: datetime
    interval_minutes: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_trades: int
    rejected_orders: int
    final_equity: float
    total_return_pct: float
    win_rate: float
    expectancy: float
    sharpe_ratio: float
    max_drawdown_pct: float
    turnover: float
    avg_exposure_pct: float
    max_exposure_pct: float
    error_message: str | None = None


class BacktestTradeResponse(BaseModel):
    id: int
    symbol: str
    status: str
    regime: str
    signal_at: datetime
    entry_at: datetime | None = None
    exit_at: datetime | None = None
    quantity: int
    holding_bars: int
    entry_price: float | None = None
    exit_price: float | None = None
    gross_pnl: float
    net_pnl: float
    return_pct: float
    commission_paid: float
    slippage_paid: float
    notes: list[str]


class TradeReviewResponse(BaseModel):
    id: int
    profile_id: int
    source_run_id: str | None = None
    order_id: int
    symbol: str
    status: str
    model_name: str | None = None
    prompt_versions: dict[str, str]
    review_score: float
    pnl: float
    return_pct: float
    loss_cause: str | None = None
    summary: str
    recurring_pattern_key: str | None = None
    review_payload: dict[str, Any]
    reviewed_at: datetime | None = None
    created_at: datetime


class TradeReviewSummaryResponse(BaseModel):
    model_name: str
    prompt_signature: str
    reviewed_trades: int
    queued_reviews: int
    avg_score: float
    avg_return_pct: float
    loss_causes: dict[str, int]


class MarketEfficiencyReportResponse(BaseModel):
    window_minutes: int
    trade_candidates: int
    approved_candidates: int
    rejected_candidates: int
    approval_rate: float
    rejection_codes: dict[str, int]
    execution_quality: dict[str, Any]
    post_trade_reviews: dict[str, Any]
    recommendations: list[str]


class DecisionAuditResponse(BaseModel):
    run_id: str
    profile_id: int
    symbol: str
    status: str
    confidence: float
    model_name: str | None = None
    prompt_versions: dict[str, str]
    score: float
    issues: list[str]
    created_at: datetime


class BacktestDetailResponse(BacktestSummaryResponse):
    metrics: dict
    walk_forward: list[dict]
    regime_breakdown: list[dict]
    equity_curve: list[dict]
    symbol_breakdown: list[dict]
    trades: list[BacktestTradeResponse]


class LiveEnablePrepareResponse(BaseModel):
    profile_id: int
    approval_code: str
    expires_at: datetime
    live_trading_env_allowed: bool


class LiveEnableRequest(BaseModel):
    approval_code: str = Field(min_length=4, max_length=12)


class CurrentOperatorResponse(BaseModel):
    email: str
    role: OperatorRole
    expires_at: datetime
    session_id: str


class ActionResponse(BaseModel):
    accepted: bool = True
    detail: str


class FlattenResponse(BaseModel):
    canceled_orders: int
    flatten_submitted: int
