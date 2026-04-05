from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.enums import OrderIntent, TradingMode
from tradingbot.models import OrderRecord, PositionRecord, RiskEvent
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import BrokerAdapter, OrderSubmission


class ExecutionService:
    def __init__(self, session: Session, broker: BrokerAdapter) -> None:
        self.session = session
        self.broker = broker

    def submit_trade(
        self,
        *,
        mode: TradingMode,
        decision: CommitteeDecision,
        risk_result: RiskCheckResult,
    ) -> OrderRecord | None:
        if risk_result.decision.value != "approved":
            self.session.add(
                RiskEvent(
                    symbol=decision.symbol,
                    severity="warning",
                    code="risk_rejected",
                    message="Trade was rejected by deterministic risk rules.",
                    payload={"notes": risk_result.notes},
                )
            )
            self.session.commit()
            return None

        client_order_id = f"{decision.symbol.lower()}-{uuid4().hex[:20]}"
        submission = OrderSubmission(
            symbol=decision.symbol,
            quantity=risk_result.approved_quantity,
            limit_price=decision.entry,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            client_order_id=client_order_id,
        )
        broker_payload = self.broker.submit_bracket_order(submission)

        order = OrderRecord(
            symbol=decision.symbol,
            mode=mode,
            direction=OrderIntent.BUY,
            quantity=risk_result.approved_quantity,
            limit_price=decision.entry,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            status=broker_payload.get("status", "accepted"),
            client_order_id=client_order_id,
            broker_order_id=broker_payload.get("id"),
            submitted_at=datetime.now(UTC),
            metadata_json=broker_payload,
        )
        position = self.session.scalar(select(PositionRecord).where(PositionRecord.symbol == decision.symbol))
        if position is None:
            position = PositionRecord(
                symbol=decision.symbol,
                quantity=risk_result.approved_quantity,
                average_entry_price=decision.entry,
                market_value=decision.entry * risk_result.approved_quantity,
                unrealized_pl=0,
                side="long",
            )
            self.session.add(position)
        else:
            position.quantity += risk_result.approved_quantity
            position.average_entry_price = decision.entry
            position.market_value = position.quantity * decision.entry

        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def current_symbol_exposure(self, symbol: str) -> float:
        position = self.session.scalar(select(PositionRecord).where(PositionRecord.symbol == symbol))
        return position.market_value if position else 0.0

