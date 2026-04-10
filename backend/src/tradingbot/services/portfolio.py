from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.models import PortfolioSnapshot, PositionRecord


@dataclass(frozen=True, slots=True)
class PortfolioHealthSummary:
    position_count: int
    gross_exposure: float
    net_exposure: float
    largest_position_notional: float
    latest_equity: float
    latest_buying_power: float
    latest_daily_pl: float


def summarize_portfolio_health(session: Session, *, profile_id: int | None = None) -> PortfolioHealthSummary:
    positions_query = select(PositionRecord)
    if profile_id is not None:
        positions_query = positions_query.where(PositionRecord.profile_id == profile_id)
    positions = session.scalars(positions_query).all()

    gross_exposure = sum(abs(float(item.market_value or 0.0)) for item in positions)
    net_exposure = sum(float(item.market_value or 0.0) for item in positions)
    largest_position = max((abs(float(item.market_value or 0.0)) for item in positions), default=0.0)

    snapshot_query = select(PortfolioSnapshot).order_by(PortfolioSnapshot.created_at.desc()).limit(1)
    if profile_id is not None:
        snapshot_query = snapshot_query.where(PortfolioSnapshot.profile_id == profile_id)
    latest_snapshot = session.scalars(snapshot_query).first()

    if latest_snapshot is None:
        return PortfolioHealthSummary(
            position_count=len(positions),
            gross_exposure=round(gross_exposure, 6),
            net_exposure=round(net_exposure, 6),
            largest_position_notional=round(largest_position, 6),
            latest_equity=0.0,
            latest_buying_power=0.0,
            latest_daily_pl=0.0,
        )

    return PortfolioHealthSummary(
        position_count=len(positions),
        gross_exposure=round(gross_exposure, 6),
        net_exposure=round(net_exposure, 6),
        largest_position_notional=round(largest_position, 6),
        latest_equity=round(float(latest_snapshot.equity or 0.0), 6),
        latest_buying_power=round(float(latest_snapshot.buying_power or 0.0), 6),
        latest_daily_pl=round(float(latest_snapshot.daily_pl or 0.0), 6),
    )
