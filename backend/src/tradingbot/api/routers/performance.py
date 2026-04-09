from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator
from tradingbot.enums import TradingMode
from tradingbot.models import OrderFill, OrderStateTransition, ReconciliationMismatch, RiskEvent, TradeCandidate, TradeReview
from tradingbot.schemas.trading import (
    MetricCounterResponse,
    MetricLatencyResponse,
    OrderFillResponse,
    OrderTransitionResponse,
    PerformanceSummaryResponse,
    RiskEventResponse,
)
from tradingbot.config import get_settings
from tradingbot.services.alerts import AlertService, settings_alert_snapshot
from tradingbot.services.metrics import metrics_registry
from tradingbot.services.portfolio import summarize_portfolio_health

router = APIRouter(tags=["performance"])


@router.get("/alerts", response_model=list[RiskEventResponse])
def list_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[RiskEventResponse]:
    rows = AlertService(session).recent_alerts(limit=limit)
    return [RiskEventResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/performance/summary", response_model=PerformanceSummaryResponse)
def get_performance_summary(
    window_minutes: int = Query(default=60, ge=5, le=24 * 60),
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> PerformanceSummaryResponse:
    return _build_performance_summary(session, window_minutes=window_minutes)


def _build_performance_summary(session: Session, *, window_minutes: int) -> PerformanceSummaryResponse:
    counters, latencies = metrics_registry().summarize(window_minutes=window_minutes)
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)

    total_candidates = session.scalar(
        select(func.count()).select_from(TradeCandidate).where(TradeCandidate.created_at >= cutoff)
    )
    rejected_candidates = session.scalar(
        select(func.count())
        .select_from(TradeCandidate)
        .where(TradeCandidate.created_at >= cutoff)
        .where(TradeCandidate.status != "approved")
    )
    malformed_events = session.scalar(
        select(func.count())
        .select_from(RiskEvent)
        .where(RiskEvent.created_at >= cutoff)
        .where(RiskEvent.code == "agent_output_malformed")
    )
    scan_failures = session.scalar(
        select(func.count())
        .select_from(RiskEvent)
        .where(RiskEvent.created_at >= cutoff)
        .where(RiskEvent.code == "scan_failure")
    )

    total_count = int(total_candidates or 0)
    rejected_count = int(rejected_candidates or 0)
    state = settings_alert_snapshot(session)
    portfolio = summarize_portfolio_health(session)
    return PerformanceSummaryResponse(
        window_minutes=window_minutes,
        total_trade_candidates=total_count,
        rejected_trade_candidates=rejected_count,
        rejection_rate=(rejected_count / max(total_count, 1)) if total_count else 0.0,
        malformed_events=int(malformed_events or 0),
        scan_failures=int(scan_failures or 0),
        kill_switch_enabled=bool(state["kill_switch_enabled"]),
        live_enabled=bool(state["live_enabled"]),
        mode=TradingMode(str(state["mode"])),
        portfolio_position_count=portfolio.position_count,
        portfolio_gross_exposure=portfolio.gross_exposure,
        portfolio_net_exposure=portfolio.net_exposure,
        portfolio_largest_position_notional=portfolio.largest_position_notional,
        latest_equity=portfolio.latest_equity,
        latest_buying_power=portfolio.latest_buying_power,
        latest_daily_pl=portfolio.latest_daily_pl,
        counters=[
            MetricCounterResponse(name=item.name, value=item.value, tags=item.tags)
            for item in counters
        ],
        latencies=[
            MetricLatencyResponse(
                name=item.name,
                samples=item.samples,
                avg_ms=item.avg_ms,
                p95_ms=item.p95_ms,
                max_ms=item.max_ms,
                tags=item.tags,
            )
            for item in latencies
        ],
    )


def _operations_snapshot(session: Session) -> dict[str, object]:
    now = datetime.now(UTC)
    alerts = [
        RiskEventResponse.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in AlertService(session).recent_alerts(limit=5)
    ]
    fills = [
        OrderFillResponse.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in session.scalars(select(OrderFill).order_by(OrderFill.filled_at.desc()).limit(5)).all()
    ]
    transitions = [
        OrderTransitionResponse.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in session.scalars(
            select(OrderStateTransition).order_by(OrderStateTransition.transition_at.desc()).limit(5)
        ).all()
    ]
    unresolved_mismatches = int(
        session.scalar(
            select(func.count())
            .select_from(ReconciliationMismatch)
            .where(ReconciliationMismatch.resolved.is_(False))
        )
        or 0
    )
    queued_reviews = int(
        session.scalar(select(func.count()).select_from(TradeReview).where(TradeReview.status == "queued")) or 0
    )
    summary = _build_performance_summary(session, window_minutes=60)
    return {
        "generated_at": now.isoformat(),
        "state": settings_alert_snapshot(session),
        "counts": {
            "alerts": len(alerts),
            "fills": len(fills),
            "transitions": len(transitions),
            "unresolved_mismatches": unresolved_mismatches,
            "queued_trade_reviews": queued_reviews,
        },
        "performance": {
            "rejection_rate": summary.rejection_rate,
            "malformed_events": summary.malformed_events,
            "scan_failures": summary.scan_failures,
            "portfolio_position_count": summary.portfolio_position_count,
            "portfolio_gross_exposure": summary.portfolio_gross_exposure,
            "latest_equity": summary.latest_equity,
        },
        "alerts": alerts,
        "fills": fills,
        "transitions": transitions,
    }


def _snapshot_digest(snapshot: dict[str, object]) -> str:
    serialized = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@router.get("/stream/operations")
async def stream_operations(
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> StreamingResponse:
    interval_seconds = max(get_settings().stream_poll_interval_seconds, 1)

    async def event_generator():
        last_digest = ""
        try:
            while True:
                session.expire_all()
                snapshot = _operations_snapshot(session)
                digest = _snapshot_digest(snapshot)
                if digest != last_digest:
                    payload = json.dumps(snapshot, separators=(",", ":"), default=str)
                    yield f"event: operations.snapshot\ndata: {payload}\n\n"
                    last_digest = digest
                else:
                    heartbeat = json.dumps({"generated_at": snapshot["generated_at"]}, separators=(",", ":"))
                    yield f"event: heartbeat\ndata: {heartbeat}\n\n"
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
