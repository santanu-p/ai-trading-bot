from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.models import PortfolioSnapshot, PositionRecord
from tradingbot.services.portfolio import summarize_portfolio_health


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_phase9_portfolio_service_summarizes_positions_and_snapshot() -> None:
    session = _session()
    session.add_all(
        [
            PositionRecord(
                symbol="AAPL",
                quantity=10,
                average_entry_price=100.0,
                market_value=1_250.0,
                unrealized_pl=50.0,
                side="long",
            ),
            PositionRecord(
                symbol="MSFT",
                quantity=5,
                average_entry_price=200.0,
                market_value=900.0,
                unrealized_pl=-20.0,
                side="long",
            ),
            PortfolioSnapshot(
                equity=105_000.0,
                cash=25_000.0,
                buying_power=75_000.0,
                daily_pl=320.0,
                exposure=2_150.0,
                source="unit",
            ),
        ]
    )
    session.commit()

    summary = summarize_portfolio_health(session)

    assert summary.position_count == 2
    assert summary.gross_exposure == 2_150.0
    assert summary.net_exposure == 2_150.0
    assert summary.largest_position_notional == 1_250.0
    assert summary.latest_equity == 105_000.0
    assert summary.latest_buying_power == 75_000.0
    assert summary.latest_daily_pl == 320.0
