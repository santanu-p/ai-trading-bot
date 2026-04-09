from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import InstrumentClass, OrderStatus
from tradingbot.models import OrderRecord
from tradingbot.services.adapters import AccountSnapshot, OrderRequest
from tradingbot.services.contracts import ContractMasterService


@dataclass(slots=True)
class PreTradeValidationResult:
    accepted: bool
    reasons: list[str]
    normalized_notional: float
    contract_symbol: str | None


class PreTradeValidator:
    def __init__(self, session: Session, contract_master: ContractMasterService) -> None:
        self.session = session
        self.contract_master = contract_master

    def validate(
        self,
        *,
        order: OrderRequest,
        instrument_class: InstrumentClass,
        account: AccountSnapshot,
        existing_margin_usage: float = 0.0,
        max_open_orders: int = 250,
    ) -> PreTradeValidationResult:
        reasons: list[str] = []

        if order.quantity <= 0:
            reasons.append("Order quantity must be positive.")

        contract_check = self.contract_master.validate_contract(
            symbol=order.symbol,
            instrument_class=instrument_class,
            as_of=datetime.now(UTC),
        )
        if not contract_check.accepted:
            reasons.extend(contract_check.reasons)
            return PreTradeValidationResult(
                accepted=False,
                reasons=reasons,
                normalized_notional=0.0,
                contract_symbol=contract_check.contract.symbol if contract_check.contract else None,
            )

        contract = contract_check.contract
        assert contract is not None

        if order.quantity % contract.lot_size != 0:
            reasons.append(f"Quantity must be a multiple of lot size {contract.lot_size}.")

        reference_price = _reference_price(order)
        if reference_price <= 0:
            reasons.append("Order requires a valid positive reference price.")

        for label, candidate in [
            ("Limit price", order.limit_price),
            ("Stop price", order.stop_price),
            ("Stop loss", order.stop_loss),
            ("Take profit", order.take_profit),
        ]:
            if candidate is None:
                continue
            if not _is_tick_aligned(candidate, contract.tick_size):
                reasons.append(f"{label} must align to tick size {contract.tick_size:g}.")

        if instrument_class == InstrumentClass.OPTIONS and not contract.option_chain_available:
            reasons.append("Option-chain metadata is unavailable for this contract.")

        if order.side.value == "sell" and not contract.shortable:
            reasons.append("Instrument is not marked shortable for sell orders.")

        normalized_notional = order.quantity * reference_price * contract.contract_multiplier
        if order.side.value == "buy" and normalized_notional > account.buying_power:
            reasons.append("Insufficient buying power for the requested order size.")

        margin_rate = float(contract.metadata_json.get("margin_rate", 1.0)) if isinstance(contract.metadata_json, dict) else 1.0
        required_margin = normalized_notional * max(margin_rate, 0.0)
        if existing_margin_usage + required_margin > account.equity * 2:
            reasons.append("Margin usage would exceed exchange-account limits.")

        open_order_count = self.session.scalar(
            select(func.count())
            .select_from(OrderRecord)
            .where(
                OrderRecord.status.notin_(
                    (
                        OrderStatus.FILLED,
                        OrderStatus.CANCELED,
                        OrderStatus.EXPIRED,
                        OrderStatus.REPLACED,
                        OrderStatus.REJECTED,
                    )
                )
            )
        ) or 0
        if open_order_count >= max_open_orders:
            reasons.append("Exchange order cap reached for this account session.")

        if contract.price_band_low is not None and reference_price < contract.price_band_low:
            reasons.append(
                f"Order price {reference_price:.4f} is below the contract lower price band {contract.price_band_low:.4f}."
            )
        if contract.price_band_high is not None and reference_price > contract.price_band_high:
            reasons.append(
                f"Order price {reference_price:.4f} is above the contract upper price band {contract.price_band_high:.4f}."
            )

        return PreTradeValidationResult(
            accepted=not reasons,
            reasons=reasons,
            normalized_notional=normalized_notional,
            contract_symbol=contract.symbol,
        )



def _reference_price(order: OrderRequest) -> float:
    if order.reference_price is not None:
        return float(order.reference_price)
    if order.limit_price is not None:
        return float(order.limit_price)
    if order.stop_price is not None:
        return float(order.stop_price)
    if order.stop_loss is not None:
        return float(order.stop_loss)
    if order.take_profit is not None:
        return float(order.take_profit)
    return 0.0


def _is_tick_aligned(price: float, tick_size: float) -> bool:
    if tick_size <= 0:
        return False
    ticks = round(price / tick_size)
    return abs((ticks * tick_size) - price) < max(tick_size * 1e-6, 1e-8)
