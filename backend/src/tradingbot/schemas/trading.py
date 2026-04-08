from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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
    risk_notes: list[str] = Field(default_factory=list)


class RiskCheckResult(BaseModel):
    decision: RiskDecision
    approved_quantity: int = 0
    notes: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    id: str
    symbol: str
    status: RunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    decision_payload: dict | None = None


class ExecutionIntentResponse(BaseModel):
    id: str
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
    symbol: str
    quantity: int
    average_entry_price: float
    market_value: float
    unrealized_pl: float
    side: str


class RiskEventResponse(BaseModel):
    id: int
    symbol: str | None = None
    severity: str
    code: str
    message: str
    payload: dict
    created_at: datetime


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
    symbols: list[str]
    start: datetime
    end: datetime
    interval_minutes: int = Field(default=5, ge=1, le=60)


class BacktestResponse(BaseModel):
    accepted: bool
    task_id: str


class LiveEnablePrepareResponse(BaseModel):
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
