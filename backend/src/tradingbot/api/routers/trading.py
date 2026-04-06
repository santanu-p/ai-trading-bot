from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import db_session_dependency, get_current_operator
from tradingbot.enums import BotStatus, TradingMode
from tradingbot.models import AgentRun, AuditLog, BotSettings, OrderRecord, PositionRecord, RiskEvent, TradeCandidate
from tradingbot.schemas.settings import BotModeUpdate, BotStatusResponse
from tradingbot.schemas.trading import (
    BacktestRequest,
    BacktestResponse,
    CommitteeDecision,
    OrderResponse,
    PositionResponse,
    RiskEventResponse,
    RunResponse,
)
from tradingbot.services.store import ensure_bot_settings, resolve_execution_support, strategy_profile_completed
from tradingbot.worker.tasks import enqueue_backtest

router = APIRouter(tags=["trading"])


def _settings_response(row: BotSettings) -> BotStatusResponse:
    return BotStatusResponse(
        status=row.status,
        mode=row.mode,
        kill_switch_enabled=row.kill_switch_enabled,
    )


@router.post("/bot/start", response_model=BotStatusResponse)
def start_bot(
    operator: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    if not strategy_profile_completed(settings_row):
        raise HTTPException(status_code=400, detail="Complete the trading-pattern intake before starting the bot.")
    support = resolve_execution_support(settings_row)
    if settings_row.mode == TradingMode.LIVE and not support.live_start_allowed:
        raise HTTPException(
            status_code=400,
            detail=support.analysis_only_downgrade_reason
            or "The selected broker/profile combination cannot be started in live mode.",
        )
    settings_row.status = BotStatus.RUNNING
    session.add(AuditLog(action="bot.start", actor=operator, details={}))
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/stop", response_model=BotStatusResponse)
def stop_bot(
    operator: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    settings_row.status = BotStatus.STOPPED
    session.add(AuditLog(action="bot.stop", actor=operator, details={}))
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/mode", response_model=BotStatusResponse)
def update_mode(
    payload: BotModeUpdate,
    operator: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    if payload.mode == TradingMode.LIVE:
        support = resolve_execution_support(settings_row)
        if not support.live_start_allowed:
            raise HTTPException(
                status_code=400,
                detail=support.analysis_only_downgrade_reason
                or "The selected broker/profile combination cannot be switched to live mode.",
            )
    settings_row.mode = payload.mode
    session.add(AuditLog(action="bot.mode", actor=operator, details={"mode": payload.mode.value}))
    session.commit()
    return _settings_response(settings_row)


@router.post("/bot/kill-switch", response_model=BotStatusResponse)
def toggle_kill_switch(
    enabled: bool,
    operator: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotStatusResponse:
    settings_row = ensure_bot_settings(session)
    settings_row.kill_switch_enabled = enabled
    session.add(AuditLog(action="bot.kill_switch", actor=operator, details={"enabled": enabled}))
    session.commit()
    return _settings_response(settings_row)


@router.get("/runs", response_model=list[RunResponse])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[RunResponse]:
    rows = session.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return [RunResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/decisions", response_model=list[CommitteeDecision])
def list_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    _: str = Depends(get_current_operator),
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
            reject_reason=row.raw_payload.get("reject_reason"),
        )
        for row in rows
    ]


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[OrderResponse]:
    rows = session.scalars(select(OrderRecord).order_by(OrderRecord.created_at.desc()).limit(limit)).all()
    return [OrderResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/positions", response_model=list[PositionResponse])
def list_positions(
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[PositionResponse]:
    rows = session.scalars(select(PositionRecord).order_by(PositionRecord.symbol)).all()
    return [PositionResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/risk-events", response_model=list[RiskEventResponse])
def list_risk_events(
    limit: int = Query(default=20, ge=1, le=100),
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[RiskEventResponse]:
    rows = session.scalars(select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(limit)).all()
    return [RiskEventResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/backtests", response_model=BacktestResponse)
def launch_backtest(
    payload: BacktestRequest,
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BacktestResponse:
    if not payload.symbols:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")
    task = enqueue_backtest(payload)
    session.add(AuditLog(action="backtest.queued", actor="admin", details={"task_id": task.id, "symbols": payload.symbols}))
    session.commit()
    return BacktestResponse(accepted=True, task_id=task.id)
