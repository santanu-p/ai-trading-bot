from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import InstrumentClass, OptionRight
from tradingbot.services.contracts import ContractMasterService



def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()



def test_option_chain_selection_prefers_closest_expiry_and_strike() -> None:
    session = _session()
    service = ContractMasterService(session)

    target_expiry = datetime.now(UTC) + timedelta(days=21)
    service.upsert_contract(
        symbol="AAPL-C-200-20D",
        instrument_class=InstrumentClass.OPTIONS,
        underlying_symbol="AAPL",
        option_right=OptionRight.CALL,
        strike_price=200,
        expiry=target_expiry - timedelta(days=1),
        option_chain_available=True,
        is_active=True,
    )
    service.upsert_contract(
        symbol="AAPL-C-205-40D",
        instrument_class=InstrumentClass.OPTIONS,
        underlying_symbol="AAPL",
        option_right=OptionRight.CALL,
        strike_price=205,
        expiry=target_expiry + timedelta(days=19),
        option_chain_available=True,
        is_active=True,
    )

    selected = service.select_option_contract(
        underlying_symbol="AAPL",
        right=OptionRight.CALL,
        target_expiry=target_expiry,
        target_strike=201,
    )

    assert selected is not None
    assert selected.symbol == "AAPL-C-200-20D"



def test_futures_rollover_moves_to_next_active_contract() -> None:
    session = _session()
    service = ContractMasterService(session)

    near_expiry = datetime.now(UTC) + timedelta(days=5)
    far_expiry = datetime.now(UTC) + timedelta(days=35)

    service.upsert_contract(
        symbol="NQ-MAY",
        instrument_class=InstrumentClass.FUTURES,
        underlying_symbol="NQ",
        expiry=near_expiry,
        is_active=True,
    )
    service.upsert_contract(
        symbol="NQ-JUN",
        instrument_class=InstrumentClass.FUTURES,
        underlying_symbol="NQ",
        expiry=far_expiry,
        is_active=True,
    )

    rolled = service.resolve_futures_rollover("NQ-MAY")

    assert rolled is not None
    assert rolled.symbol == "NQ-JUN"
