from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator, require_roles
from tradingbot.enums import OperatorRole
from tradingbot.models import AuditLog, BacktestReport, BacktestTrade
from tradingbot.schemas.trading import (
    BacktestDetailResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestSummaryResponse,
    BacktestTradeResponse,
)
from tradingbot.worker.tasks import enqueue_backtest

router = APIRouter(tags=["backtests"])


def _serialize_backtest_summary(row: BacktestReport) -> BacktestSummaryResponse:
    return BacktestSummaryResponse(
        id=row.id,
        task_id=row.task_id,
        status=row.status,
        symbols=row.symbols,
        start_at=row.start_at,
        end_at=row.end_at,
        interval_minutes=row.interval_minutes,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        total_trades=row.total_trades,
        rejected_orders=row.rejected_orders,
        final_equity=row.final_equity,
        total_return_pct=row.total_return_pct,
        win_rate=row.win_rate,
        expectancy=row.expectancy,
        sharpe_ratio=row.sharpe_ratio,
        max_drawdown_pct=row.max_drawdown_pct,
        turnover=row.turnover,
        avg_exposure_pct=row.avg_exposure_pct,
        max_exposure_pct=row.max_exposure_pct,
        error_message=row.error_message,
    )


def _serialize_backtest_detail(row: BacktestReport, trades: list[BacktestTrade]) -> BacktestDetailResponse:
    summary = _serialize_backtest_summary(row)
    return BacktestDetailResponse(
        **summary.model_dump(),
        metrics=row.metrics_json,
        walk_forward=row.walk_forward_json,
        regime_breakdown=row.regime_breakdown_json,
        equity_curve=row.equity_curve_json,
        symbol_breakdown=row.symbol_breakdown_json,
        trades=[BacktestTradeResponse.model_validate(item, from_attributes=True) for item in trades],
    )


@router.get("/backtests", response_model=list[BacktestSummaryResponse])
def list_backtests(
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[BacktestSummaryResponse]:
    query = select(BacktestReport).order_by(BacktestReport.created_at.desc())
    if status:
        query = query.where(BacktestReport.status == status)
    rows = session.scalars(query.limit(limit)).all()
    return [_serialize_backtest_summary(row) for row in rows]


@router.get("/backtests/{report_id}", response_model=BacktestDetailResponse)
def get_backtest_report(
    report_id: str,
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BacktestDetailResponse:
    report = session.get(BacktestReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Backtest report {report_id} was not found.")
    trades = list(
        session.scalars(select(BacktestTrade).where(BacktestTrade.report_id == report_id).order_by(BacktestTrade.signal_at.desc())).all()
    )
    return _serialize_backtest_detail(report, trades)


@router.post("/backtests", response_model=BacktestResponse)
def launch_backtest(
    payload: BacktestRequest,
    current: CurrentActor = Depends(require_roles(OperatorRole.OPERATOR, OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BacktestResponse:
    normalized_symbols = [item.strip().upper() for item in payload.symbols if item.strip()]
    if not normalized_symbols:
        raise HTTPException(status_code=400, detail="At least one non-empty symbol is required.")

    report = BacktestReport(
        status="queued",
        symbols=normalized_symbols,
        start_at=payload.start,
        end_at=payload.end,
        interval_minutes=payload.interval_minutes,
        initial_equity=payload.initial_equity,
        slippage_bps=payload.slippage_bps,
        commission_per_share=payload.commission_per_share,
        fill_delay_bars=payload.fill_delay_bars,
        reject_probability=payload.reject_probability,
        max_holding_bars=payload.max_holding_bars,
        random_seed=payload.random_seed,
    )
    session.add(report)
    session.flush()

    task = enqueue_backtest(payload, report.id)
    report.task_id = task.id
    session.add(
        AuditLog(
            action="backtest.queued",
            actor=current.email,
            actor_role=current.role.value,
            session_id=current.session_id,
            details={"task_id": task.id, "report_id": report.id, "symbols": report.symbols},
        )
    )
    session.commit()
    return BacktestResponse(accepted=True, task_id=task.id, report_id=report.id)
