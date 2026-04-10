from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.enums import InstrumentClass, MarketRegion, OptionRight
from tradingbot.models import InstrumentContract


@dataclass(slots=True)
class ContractValidationResult:
    contract: InstrumentContract | None
    accepted: bool
    reasons: list[str]


class ContractMasterService:
    def __init__(self, session: Session, *, market_region: MarketRegion = MarketRegion.US) -> None:
        self.session = session
        self.market_region = market_region

    def get_contract(self, symbol: str) -> InstrumentContract | None:
        normalized = symbol.upper().strip()
        if not normalized:
            return None
        return self.session.scalar(
            select(InstrumentContract)
            .where(InstrumentContract.market_region == self.market_region)
            .where(InstrumentContract.symbol == normalized)
        )

    def upsert_contract(
        self,
        *,
        symbol: str,
        instrument_class: InstrumentClass,
        market_region: MarketRegion | None = None,
        underlying_symbol: str | None = None,
        exchange: str = "UNKNOWN",
        tick_size: float = 0.01,
        lot_size: int = 1,
        contract_multiplier: float = 1.0,
        expiry: datetime | None = None,
        strike_price: float | None = None,
        option_right: OptionRight | None = None,
        shortable: bool = False,
        option_chain_available: bool = False,
        price_band_low: float | None = None,
        price_band_high: float | None = None,
        is_active: bool = True,
        metadata_json: dict | None = None,
    ) -> InstrumentContract:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            raise ValueError("Contract symbol is required.")

        target_region = market_region or self.market_region
        contract = self.session.scalar(
            select(InstrumentContract)
            .where(InstrumentContract.market_region == target_region)
            .where(InstrumentContract.symbol == normalized_symbol)
        )
        if contract is None:
            contract = InstrumentContract(
                market_region=target_region,
                symbol=normalized_symbol,
                instrument_class=instrument_class,
            )
            self.session.add(contract)

        contract.market_region = target_region
        contract.instrument_class = instrument_class
        contract.underlying_symbol = underlying_symbol.upper().strip() if underlying_symbol else None
        contract.exchange = exchange.strip() or "UNKNOWN"
        contract.tick_size = max(tick_size, 0.0001)
        contract.lot_size = max(lot_size, 1)
        contract.contract_multiplier = max(contract_multiplier, 0.0001)
        contract.expiry = expiry
        contract.strike_price = strike_price
        contract.option_right = option_right
        contract.shortable = shortable
        contract.option_chain_available = option_chain_available
        contract.price_band_low = price_band_low
        contract.price_band_high = price_band_high
        contract.is_active = is_active
        contract.metadata_json = metadata_json or {}
        self.session.flush()
        return contract

    def ensure_cash_equity_contract(self, symbol: str) -> InstrumentContract:
        normalized_symbol = symbol.upper().strip()
        contract = self.get_contract(normalized_symbol)
        if contract is not None:
            return contract

        contract = InstrumentContract(
            market_region=self.market_region,
            symbol=normalized_symbol,
            instrument_class=InstrumentClass.CASH_EQUITY,
            exchange="SMART",
            tick_size=0.01,
            lot_size=1,
            contract_multiplier=1.0,
            shortable=True,
            option_chain_available=True,
            is_active=True,
            metadata_json={"source": "autocreated_equity"},
        )
        self.session.add(contract)
        self.session.flush()
        return contract

    def validate_contract(
        self,
        *,
        symbol: str,
        instrument_class: InstrumentClass,
        as_of: datetime | None = None,
    ) -> ContractValidationResult:
        as_of_time = (as_of or datetime.now(UTC)).astimezone(UTC)
        normalized_symbol = symbol.upper().strip()

        contract: InstrumentContract | None
        if instrument_class == InstrumentClass.CASH_EQUITY:
            contract = self.ensure_cash_equity_contract(normalized_symbol)
        else:
            contract = self.get_contract(normalized_symbol)

        reasons: list[str] = []
        if contract is None:
            reasons.append(f"No contract found for {normalized_symbol}.")
            return ContractValidationResult(contract=None, accepted=False, reasons=reasons)

        if contract.instrument_class != instrument_class and instrument_class != InstrumentClass.MIXED:
            reasons.append(
                f"Instrument {normalized_symbol} is registered as {contract.instrument_class.value}, not {instrument_class.value}."
            )
        if not contract.is_active:
            reasons.append(f"Instrument {normalized_symbol} is marked inactive.")
        if contract.expiry and contract.expiry <= as_of_time:
            reasons.append(f"Instrument {normalized_symbol} is expired.")
        if contract.tick_size <= 0:
            reasons.append(f"Instrument {normalized_symbol} has invalid tick size.")
        if contract.lot_size <= 0:
            reasons.append(f"Instrument {normalized_symbol} has invalid lot size.")
        if contract.contract_multiplier <= 0:
            reasons.append(f"Instrument {normalized_symbol} has invalid contract multiplier.")

        return ContractValidationResult(contract=contract, accepted=not reasons, reasons=reasons)

    def select_option_contract(
        self,
        *,
        underlying_symbol: str,
        right: OptionRight,
        target_expiry: datetime,
        target_strike: float,
    ) -> InstrumentContract | None:
        normalized_underlying = underlying_symbol.upper().strip()
        rows = self.session.scalars(
            select(InstrumentContract)
            .where(InstrumentContract.market_region == self.market_region)
            .where(InstrumentContract.instrument_class == InstrumentClass.OPTIONS)
            .where(InstrumentContract.underlying_symbol == normalized_underlying)
            .where(InstrumentContract.option_right == right)
            .where(InstrumentContract.option_chain_available.is_(True))
            .where(InstrumentContract.is_active.is_(True))
        ).all()

        if not rows:
            return None

        target_expiry_utc = _normalize_datetime(target_expiry)

        def _score(contract: InstrumentContract) -> tuple[float, float]:
            contract_expiry = _normalize_datetime(contract.expiry) if contract.expiry else target_expiry_utc
            expiry_score = abs(contract_expiry - target_expiry_utc)
            strike_score = abs((contract.strike_price or target_strike) - target_strike)
            return (expiry_score.total_seconds(), strike_score)

        return sorted(rows, key=_score)[0]

    def resolve_futures_rollover(self, symbol: str, *, as_of: datetime | None = None) -> InstrumentContract | None:
        as_of_time = (as_of or datetime.now(UTC)).astimezone(UTC)
        current = self.get_contract(symbol)
        if current is None:
            return None
        if current.instrument_class != InstrumentClass.FUTURES:
            return current

        underlying = current.underlying_symbol or current.symbol
        candidates = self.session.scalars(
            select(InstrumentContract)
            .where(InstrumentContract.market_region == self.market_region)
            .where(InstrumentContract.instrument_class == InstrumentClass.FUTURES)
            .where(InstrumentContract.is_active.is_(True))
            .where(InstrumentContract.underlying_symbol == underlying)
            .where(InstrumentContract.expiry.is_not(None))
            .where(InstrumentContract.expiry >= as_of_time)
            .order_by(InstrumentContract.expiry.asc())
        ).all()

        if not candidates:
            return current

        for candidate in candidates:
            if current.expiry is None or (candidate.expiry and candidate.expiry > current.expiry):
                return candidate

        return candidates[-1]


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
