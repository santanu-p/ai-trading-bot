from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator
from tradingbot.enums import TradingMode
from tradingbot.models import RiskEvent, TradeCandidate
from tradingbot.schemas.trading import (
    MetricCounterResponse,
    MetricLatencyResponse,
    PerformanceSummaryResponse,
    RiskEventResponse,
)
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
