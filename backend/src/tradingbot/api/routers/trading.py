from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import randbelow

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator, require_roles
from tradingbot.config import get_settings
from tradingbot.enums import BotStatus, ExecutionIntentStatus, OperatorRole, OrderStatus, TradingMode
from tradingbot.models import (
    AgentRun,
    AuditLog,
    BotSettings,
    ExecutionQualitySample,
    ExecutionIntent,
    OrderFill,
    OrderRecord,
    OrderStateTransition,
    PositionRecord,
    ReconciliationMismatch,
    RiskEvent,
    TradeReview,
    TradeCandidate,
)
from tradingbot.schemas.settings import BotModeUpdate, BotStatusResponse
from tradingbot.schemas.trading import (
    ActionResponse,
    AgentDecision,
    AuditLogResponse,
    CommitteeDecision,
    CurrentOperatorResponse,
    ExecutionIntentResponse,
    ExecutionQualitySampleResponse,
    ExecutionQualitySummaryResponse,
    FlattenResponse,
    LiveEnablePrepareResponse,
    LiveEnableRequest,
    OrderFillResponse,
    OrderReplaceRequest,
    OrderResponse,
    OrderTransitionResponse,
    PositionResponse,
    ReconciliationMismatchResponse,
    RiskEventResponse,
    RunResponse,
    TradeReviewResponse,
    TradeReviewSummaryResponse,
)
from tradingbot.services.adapters import ReplaceOrderRequest, build_broker_adapter
from tradingbot.services.alerts import AlertService
from tradingbot.services.evaluation import TradeReviewService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.reconciliation import ReconciliationService
from tradingbot.services.store import ensure_bot_settings, live_trading_env_allowed, resolve_execution_support, strategy_profile_completed
from tradingbot.security import hash_password, verify_password
from tradingbot.worker.execution_tasks import enqueue_execution_intent

router = APIRouter(tags=["trading"])


def _settings_response(row: BotSettings) -> BotStatusResponse:
    return BotStatusResponse(
        status=row.status,
        mode=row.mode,
        kill_switch_enabled=row.kill_switch_enabled,
        live_enabled=row.live_enabled,
    )


def _build_execution_service(session: Session) -> tuple[BotSettings, ExecutionService]:
    settings_row = ensure_bot_settings(session)
    return settings_row, ExecutionService(session, build_broker_adapter(settings_row))


def _build_replace_request(payload: OrderReplaceRequest) -> ReplaceOrderRequest:
    return ReplaceOrderRequest(
        quantity=payload.quantity,
        limit_price=payload.limit_price,
        stop_price=payload.stop_price,
        take_profit=payload.take_profit,
        time_in_force=payload.time_in_force,
    )


@router.post("/bot/start", response_model=BotStatusResponse)
def start_bot(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    if not strategy_profile_completed(settings_row):
        raise HTTPException(status_code=400, detail="Complete the trading-pattern intake before starting the bot.")
    support = resolve_execution_support(settings_row)
    if settings_row.mode == TradingMode.LIVE and (not support.live_start_allowed or not live_trading_env_allowed(settings_row)):
        raise HTTPException(
            status_code=400,
            detail=support.analysis_only_downgrade_reason
            or "The selected broker/profile combination cannot be started in live mode.",
        )
    settings_row.status = BotStatus.RUNNING
    session.add(
        AuditLog(
            action="bot.start",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/stop", response_model=BotStatusResponse)
def stop_bot(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    settings_row.status = BotStatus.STOPPED
    session.add(
        AuditLog(
            action="bot.stop",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/mode", response_model=BotStatusResponse)
def update_mode(
    payload: BotModeUpdate,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    if payload.mode == TradingMode.LIVE:
        support = resolve_execution_support(settings_row)
        if not support.live_start_allowed or not live_trading_env_allowed(settings_row):
            raise HTTPException(
                status_code=400,
                detail=support.analysis_only_downgrade_reason
                or "The selected broker/profile combination cannot be switched to live mode.",
            )
    settings_row.mode = payload.mode
    if payload.mode == TradingMode.PAPER:
        settings_row.live_enabled = False
    session.add(
        AuditLog(
            action="bot.mode",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"mode": payload.mode.value},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/kill-switch", response_model=BotStatusResponse)
def toggle_kill_switch(
    enabled: bool,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    settings_row.kill_switch_enabled = enabled
    if enabled:
        settings_row.live_enabled = False
        AlertService(session).notify_kill_switch(
            source="api_toggle",
            details={"actor": current.email, "actor_role": current.role.value},
        )
    session.add(
        AuditLog(
            action="bot.kill_switch",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"enabled": enabled},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/live/prepare", response_model=LiveEnablePrepareResponse)
def prepare_live_enablement(
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> LiveEnablePrepareResponse:
    settings_row = ensure_bot_settings(session)
    support = resolve_execution_support(settings_row)
    if settings_row.mode != TradingMode.LIVE:
        raise HTTPException(status_code=400, detail="Switch the bot into live mode before enabling live execution.")
    if not support.live_start_allowed or not live_trading_env_allowed(settings_row):
        raise HTTPException(status_code=400, detail="This environment or broker scope is not eligible for live execution.")
    approval_code = f"{randbelow(10**6):06d}"
    expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().live_enable_code_ttl_minutes)
    settings_row.live_enable_code_hash = hash_password(approval_code)
    settings_row.live_enable_code_expires_at = expires_at
    session.add(
        AuditLog(
            action="bot.live_prepare",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"expires_at": expires_at.isoformat()},
        )
    )
    session.commit()
    return LiveEnablePrepareResponse(
        approval_code=approval_code,
        expires_at=expires_at,
        live_trading_env_allowed=True,
    )


@router.post("/bot/live/enable", response_model=BotStatusResponse)
def enable_live_execution(
    payload: LiveEnableRequest,
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    if settings_row.live_enable_code_hash is None or settings_row.live_enable_code_expires_at is None:
        raise HTTPException(status_code=400, detail="Prepare live enablement first.")
    if settings_row.live_enable_code_expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Live enablement code has expired.")
    if not verify_password(payload.approval_code, settings_row.live_enable_code_hash):
        raise HTTPException(status_code=400, detail="Invalid live enablement code.")
    settings_row.live_enabled = True
    settings_row.live_enable_code_hash = None
    settings_row.live_enable_code_expires_at = None
    session.add(
        AuditLog(
            action="bot.live_enable",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/live/disable", response_model=BotStatusResponse)
def disable_live_execution(
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    settings_row.live_enabled = False
    settings_row.live_enable_code_hash = None
    settings_row.live_enable_code_expires_at = None
    session.add(
        AuditLog(
            action="bot.live_disable",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={},
        )
    )
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/flatten-all", response_model=FlattenResponse)
def flatten_all_positions(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> FlattenResponse:
    settings_row, execution = _build_execution_service(session)
    canceled_orders = execution.cancel_all_open_orders()
    flatten_submitted = execution.flatten_all_positions(
        mode=settings_row.mode,
        actor=current.email,
        actor_role=current.role.value,
        session_id=current.session_id,
        reason="manual_flatten",
    )
    return FlattenResponse(canceled_orders=canceled_orders, flatten_submitted=flatten_submitted)


@router.post("/bot/broker-kill", response_model=ActionResponse)
def broker_kill(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> ActionResponse:
    settings_row, execution = _build_execution_service(session)
    settings_row.kill_switch_enabled = True
    settings_row.live_enabled = False
    canceled_orders = execution.broker_kill(
        actor=current.email,
        actor_role=current.role.value,
        session_id=current.session_id,
    )
    AlertService(session).notify_kill_switch(
        source="broker_kill",
        details={"actor": current.email, "actor_role": current.role.value, "canceled_orders": canceled_orders},
    )
    session.commit()
    return ActionResponse(detail=f"Broker kill activated. Canceled {canceled_orders} open orders.")


@router.get("/runs", response_model=list[RunResponse])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[RunResponse]:
    rows = session.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return [RunResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/decisions", response_model=list[CommitteeDecision])
def list_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[CommitteeDecision]:
    rows = session.scalars(select(TradeCandidate).order_by(TradeCandidate.created_at.desc()).limit(limit)).all()
    return [
        CommitteeDecision(
            symbol=row.symbol,
            direction=row.direction,
            confidence=row.confidence,
            entry=row.entry,
            stop_loss=row.stop_loss,
            take_profit=row.take_profit,
            time_horizon="intraday",
            status=row.status,
            thesis=row.thesis,
            risk_notes=row.risk_notes,
            market_vote=row.raw_payload.get("market_vote"),
            news_vote=row.raw_payload.get("news_vote"),
            chair_vote=row.raw_payload.get("chair_vote"),
            reject_reason=row.raw_payload.get("reject_reason"),
            committee_notes=row.raw_payload.get("committee_notes", []),
            agent_signals=[AgentDecision.model_validate(item) for item in row.raw_payload.get("agent_signals", [])],
            model_name=row.raw_payload.get("model_name"),
            prompt_versions=row.raw_payload.get("prompt_versions", {}),
        )
        for row in rows
    ]


@router.get("/authz/current", response_model=CurrentOperatorResponse)
def current_operator(current: CurrentActor = Depends(get_current_operator)) -> CurrentOperatorResponse:
    return CurrentOperatorResponse(
        email=current.email,
        role=current.role,
        expires_at=current.expires_at,
        session_id=current.session_id,
    )


@router.get("/execution-intents", response_model=list[ExecutionIntentResponse])
def list_execution_intents(
    status: ExecutionIntentStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[ExecutionIntentResponse]:
    query = select(ExecutionIntent).order_by(ExecutionIntent.created_at.desc())
    if status is not None:
        query = query.where(ExecutionIntent.status == status)
    rows = session.scalars(query.limit(limit)).all()
    return [ExecutionIntentResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/execution-intents/{intent_id}/approve", response_model=ExecutionIntentResponse)
def approve_execution_intent(
    intent_id: str,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> ExecutionIntentResponse:
    settings_row = ensure_bot_settings(session)
    if settings_row.mode == TradingMode.LIVE and not settings_row.live_enabled:
        raise HTTPException(status_code=409, detail="Enable live execution before approving live intents.")
    _, execution = _build_execution_service(session)
    try:
        intent = execution.approve_intent(
            intent_id,
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enqueue_execution_intent(intent.id)
    return ExecutionIntentResponse.model_validate(intent, from_attributes=True)


@router.post("/execution-intents/{intent_id}/reject", response_model=ExecutionIntentResponse)
def reject_execution_intent(
    intent_id: str,
    detail: str = Query(default="Rejected by operator."),
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> ExecutionIntentResponse:
    _, execution = _build_execution_service(session)
    try:
        intent = execution.reject_intent(
            intent_id,
            actor=current.email,
            actor_role=current.role.value,
            reason=detail,
            session_id=current.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExecutionIntentResponse.model_validate(intent, from_attributes=True)


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[OrderResponse]:
    rows = session.scalars(select(OrderRecord).order_by(OrderRecord.created_at.desc()).limit(limit)).all()
    return [OrderResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/orders/{order_id}/transitions", response_model=list[OrderTransitionResponse])
def list_order_transitions(
    order_id: int,
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[OrderTransitionResponse]:
    rows = session.scalars(
        select(OrderStateTransition)
        .where(OrderStateTransition.order_id == order_id)
        .order_by(OrderStateTransition.transition_at.asc())
    ).all()
    return [OrderTransitionResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/orders/{order_id}/fills", response_model=list[OrderFillResponse])
def list_order_fills(
    order_id: int,
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[OrderFillResponse]:
    rows = session.scalars(select(OrderFill).where(OrderFill.order_id == order_id).order_by(OrderFill.filled_at.asc())).all()
    return [OrderFillResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/orders/{order_id}/replace", response_model=OrderResponse)
def replace_order(
    order_id: int,
    payload: OrderReplaceRequest,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> OrderResponse:
    _, execution = _build_execution_service(session)
    try:
        row = execution.replace_order(order_id, _build_replace_request(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.add(
        AuditLog(
            action="order.replace",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"order_id": order_id},
        )
    )
    session.commit()
    return OrderResponse.model_validate(row, from_attributes=True)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> OrderResponse:
    _, execution = _build_execution_service(session)
    try:
        row = execution.cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.add(
        AuditLog(
            action="order.cancel",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"order_id": order_id},
        )
    )
    session.commit()
    return OrderResponse.model_validate(row, from_attributes=True)


@router.post("/orders/cancel-all", response_model=FlattenResponse)
def cancel_all_orders(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> FlattenResponse:
    _, execution = _build_execution_service(session)
    canceled_orders = execution.cancel_all_open_orders()
    session.add(
        AuditLog(
            action="orders.cancel_all",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"canceled_orders": canceled_orders},
        )
    )
    session.commit()
    return FlattenResponse(canceled_orders=canceled_orders, flatten_submitted=0)


@router.get("/positions", response_model=list[PositionResponse])
def list_positions(
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[PositionResponse]:
    rows = session.scalars(select(PositionRecord).order_by(PositionRecord.symbol)).all()
    return [PositionResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/risk-events", response_model=list[RiskEventResponse])
def list_risk_events(
    limit: int = Query(default=20, ge=1, le=100),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[RiskEventResponse]:
    rows = session.scalars(select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(limit)).all()
    return [RiskEventResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/execution-quality/samples", response_model=list[ExecutionQualitySampleResponse])
def list_execution_quality_samples(
    symbol: str | None = None,
    outcome_status: OrderStatus | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[ExecutionQualitySampleResponse]:
    query = select(ExecutionQualitySample).order_by(ExecutionQualitySample.created_at.desc())
    if symbol:
        query = query.where(ExecutionQualitySample.symbol == symbol.upper().strip())
    if outcome_status is not None:
        query = query.where(ExecutionQualitySample.outcome_status == outcome_status)
    rows = session.scalars(query.limit(limit)).all()
    return [
        ExecutionQualitySampleResponse(
            id=row.id,
            order_id=row.order_id,
            symbol=row.symbol,
            broker_slug=row.broker_slug.value,
            venue=row.venue,
            order_type=row.order_type,
            side=row.side,
            outcome_status=row.outcome_status,
            quantity=row.quantity,
            filled_quantity=row.filled_quantity,
            fill_ratio=row.fill_ratio,
            intended_price=row.intended_price,
            realized_price=row.realized_price,
            expected_slippage_bps=row.expected_slippage_bps,
            realized_slippage_bps=row.realized_slippage_bps,
            expected_spread_bps=row.expected_spread_bps,
            spread_cost=row.spread_cost,
            notional=row.notional,
            time_to_fill_seconds=row.time_to_fill_seconds,
            aggressiveness=row.aggressiveness,
            quality_score=row.quality_score,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/execution-quality/summary", response_model=list[ExecutionQualitySummaryResponse])
def summarize_execution_quality(
    dimension: str = Query(default="symbol", pattern="^(symbol|venue|broker|order_type)$"),
    limit: int = Query(default=20, ge=1, le=200),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[ExecutionQualitySummaryResponse]:
    _, execution = _build_execution_service(session)
    try:
        rows = execution.execution_quality_summary(dimension=dimension, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [ExecutionQualitySummaryResponse.model_validate(item) for item in rows]


@router.get("/trade-reviews", response_model=list[TradeReviewResponse])
def list_trade_reviews(
    status: str | None = None,
    loss_cause: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[TradeReviewResponse]:
    query = select(TradeReview).order_by(TradeReview.created_at.desc())
    if status:
        query = query.where(TradeReview.status == status)
    if loss_cause:
        query = query.where(TradeReview.loss_cause == loss_cause)
    rows = session.scalars(query.limit(limit)).all()
    return [
        TradeReviewResponse(
            id=row.id,
            source_run_id=row.source_run_id,
            order_id=row.order_id,
            symbol=row.symbol,
            status=row.status,
            model_name=row.model_name,
            prompt_versions=row.prompt_versions_json,
            review_score=row.review_score,
            pnl=row.pnl,
            return_pct=row.return_pct,
            loss_cause=row.loss_cause,
            summary=row.summary,
            recurring_pattern_key=row.recurring_pattern_key,
            review_payload=row.review_payload,
            reviewed_at=row.reviewed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/trade-reviews/summary", response_model=list[TradeReviewSummaryResponse])
def summarize_trade_reviews(
    limit: int = Query(default=100, ge=1, le=1000),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[TradeReviewSummaryResponse]:
    service = TradeReviewService(session)
    rows = service.summarize_model_performance(limit=limit)
    return [TradeReviewSummaryResponse.model_validate(item) for item in rows]


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[AuditLogResponse]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.where(AuditLog.action == action)
    if actor:
        query = query.where(AuditLog.actor == actor)
    rows = session.scalars(query.limit(limit)).all()
    return [AuditLogResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/reconciliation/mismatches", response_model=list[ReconciliationMismatchResponse])
def list_reconciliation_mismatches(
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[ReconciliationMismatchResponse]:
    query = select(ReconciliationMismatch)
    if not include_resolved:
        query = query.where(ReconciliationMismatch.resolved.is_(False))
    rows = session.scalars(query.order_by(ReconciliationMismatch.created_at.desc()).limit(limit)).all()
    payload: list[ReconciliationMismatchResponse] = []
    for row in rows:
        serialized = ReconciliationMismatchResponse.model_validate(row, from_attributes=True)
        payload.append(serialized.model_copy(update={"broker_slug": row.broker_slug.value}))
    return payload


@router.post("/reconciliation/run")
def run_reconciliation_now(
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> dict[str, int]:
    settings_row, execution = _build_execution_service(session)
    service = ReconciliationService(
        session=session,
        settings_row=settings_row,
        execution=execution,
        adapter=execution.broker,
    )
    report = service.reconcile()
    alerts = AlertService(session)
    alerts.evaluate_runtime_alerts()
    if report.live_paused:
        alerts.notify_reconciliation_unresolved(
            unresolved_mismatches=report.unresolved_mismatches,
            source="api_reconciliation",
            details={"mismatches_created": report.mismatches_created},
        )
    session.add(
        AuditLog(
            action="reconciliation.run",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={
                "transitions_applied": report.transitions_applied,
                "fills_ingested": report.fills_ingested,
                "mismatches_created": report.mismatches_created,
                "unresolved_mismatches": report.unresolved_mismatches,
                "live_paused": report.live_paused,
            },
        )
    )
    session.commit()
    return {
        "transitions_applied": report.transitions_applied,
        "fills_ingested": report.fills_ingested,
        "mismatches_created": report.mismatches_created,
        "unresolved_mismatches": report.unresolved_mismatches,
        "live_paused": int(report.live_paused),
    }


