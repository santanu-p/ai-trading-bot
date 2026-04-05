from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tradingbot.enums import OrderIntent, RiskDecision, RunStatus, TradingMode


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


class OrderResponse(BaseModel):
    id: int
    symbol: str
    mode: TradingMode
    direction: OrderIntent
    quantity: int
    limit_price: float
    stop_loss: float
    take_profit: float
    status: str
    client_order_id: str
    broker_order_id: str | None = None
    submitted_at: datetime | None = None


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


class BacktestRequest(BaseModel):
    symbols: list[str]
    start: datetime
    end: datetime
    interval_minutes: int = Field(default=5, ge=1, le=60)


class BacktestResponse(BaseModel):
    accepted: bool
    task_id: str

