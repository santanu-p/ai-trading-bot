from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.enums import ExecutionIntentStatus, ExecutionIntentType, InstrumentClass, OrderIntent, OrderStatus, OrderType, TradingMode
from tradingbot.models import AuditLog, BotSettings, ExecutionIntent, OrderFill, OrderRecord, OrderStateTransition, PositionRecord, RiskEvent
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import (
    BrokerFill,
    BrokerAPIError,
    BrokerOrder,
    BrokerPosition,
    ExecutionAdapter,
    OrderRequest,
    ReplaceOrderRequest,
    _to_datetime,
)
from tradingbot.services.calendar import MarketCalendarService
from tradingbot.services.contracts import ContractMasterService
from tradingbot.services.evaluation import TradeReviewService
from tradingbot.services.execution_quality import ExecutionQualityService
from tradingbot.services.metrics import observe_counter
from tradingbot.services.pretrade import PreTradeValidator
from tradingbot.services.risk import PortfolioRiskService, risk_policy_from_settings

TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.EXPIRED,
    OrderStatus.REPLACED,
    OrderStatus.REJECTED,
}

STATE_TRANSITIONS: dict[OrderStatus | None, set[OrderStatus]] = {
    None: {OrderStatus.NEW},
    OrderStatus.NEW: {
        OrderStatus.ACCEPTED,
        OrderStatus.PENDING_TRIGGER,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.SUSPENDED,
    },
    OrderStatus.ACCEPTED: {
        OrderStatus.PENDING_TRIGGER,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REPLACED,
        OrderStatus.REJECTED,
        OrderStatus.SUSPENDED,
    },
    OrderStatus.PENDING_TRIGGER: {
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.SUSPENDED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REPLACED,
        OrderStatus.REJECTED,
        OrderStatus.SUSPENDED,
    },
    OrderStatus.REPLACED: {
        OrderStatus.ACCEPTED,
        OrderStatus.PENDING_TRIGGER,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.SUSPENDED,
    },
    OrderStatus.SUSPENDED: {
        OrderStatus.ACCEPTED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.REJECTED: set(),
}


class ExecutionService:
    def __init__(self, session: Session, broker: ExecutionAdapter, settings_row: BotSettings | None = None) -> None:
        self.session = session
        self.broker = broker
        if settings_row is None:
            from tradingbot.services.store import ensure_bot_settings

            settings_row = ensure_bot_settings(session)
        self.settings_row = settings_row
        self.profile_id = settings_row.id if settings_row is not None else None
        self.contract_master = ContractMasterService(session, market_region=settings_row.market_region)
        self.pretrade = PreTradeValidator(session, self.contract_master, profile_id=self.profile_id)
        self.trade_reviews = TradeReviewService(session, profile_id=self.profile_id)
        default_venue = settings_row.broker_venue if settings_row is not None else "unknown"
        self.execution_quality = ExecutionQualityService(
            session,
            broker_slug=broker.broker_slug,
            profile_id=self.profile_id,
            default_venue=default_venue,
        )

    def _profile_order_query(self):
        query = select(OrderRecord)
        if self.profile_id is not None:
            query = query.where(OrderRecord.profile_id == self.profile_id)
        return query

    def _profile_position_query(self):
        query = select(PositionRecord)
        if self.profile_id is not None:
            query = query.where(PositionRecord.profile_id == self.profile_id)
        return query

    def _profile_fill_query(self):
        query = select(OrderFill)
        if self.profile_id is not None:
            query = query.where(OrderFill.profile_id == self.profile_id)
        return query

    def _profile_intent_query(self):
        query = select(ExecutionIntent)
        if self.profile_id is not None:
            query = query.where(ExecutionIntent.profile_id == self.profile_id)
        return query

    def queue_trade_intent(
        self,
        *,
        settings_row: BotSettings,
        run_id: str,
        decision: CommitteeDecision,
        decision_context: dict[str, object] | None = None,
        risk_result: RiskCheckResult,
        execution_allowed: bool,
        block_reason: str | None,
    ) -> ExecutionIntent:
        intent = self.session.scalar(
            self._profile_intent_query().where(ExecutionIntent.source_run_id == run_id)
        )
        if intent is not None:
            return intent

        requires_human_approval = settings_row.mode == TradingMode.LIVE
        status = ExecutionIntentStatus.PENDING_APPROVAL if requires_human_approval else ExecutionIntentStatus.APPROVED
        intent_id = str(uuid4())
        intent = ExecutionIntent(
            id=intent_id,
            profile_id=settings_row.id,
            source_run_id=run_id,
            intent_type=ExecutionIntentType.TRADE,
            mode=settings_row.mode,
            status=status,
            symbol=decision.symbol,
            direction=decision.direction,
            quantity=risk_result.approved_quantity,
            limit_price=decision.entry,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            requires_human_approval=requires_human_approval,
            idempotency_key=f"run:{run_id}",
            decision_payload=decision_context or decision.model_dump(mode="json"),
            risk_payload=risk_result.model_dump(mode="json"),
            block_reason=block_reason
            if execution_allowed
            else (block_reason or "Execution is blocked for the selected broker/profile combination."),
            metadata_json={
                "live_enabled_at_queue_time": settings_row.live_enabled,
                "execution_allowed": execution_allowed,
            },
        )
        self.session.add(intent)
        self.session.add(
            AuditLog(
                profile_id=settings_row.id,
                action="execution.intent_created",
                actor="system",
                actor_role="system",
                details={
                    "intent_id": intent.id,
                    "source_run_id": run_id,
                    "mode": settings_row.mode.value,
                    "requires_human_approval": requires_human_approval,
                    "symbol": decision.symbol,
                },
            )
        )
        self.session.commit()
        self.session.refresh(intent)
        return intent

    def approve_intent(self, intent_id: str, *, actor: str, actor_role: str, session_id: str | None = None) -> ExecutionIntent:
        intent = self._require_intent(intent_id)
        if intent.status != ExecutionIntentStatus.PENDING_APPROVAL:
            raise ValueError("Only pending intents can be approved.")
        intent.status = ExecutionIntentStatus.APPROVED
        intent.approved_by = actor
        intent.approved_at = datetime.now(UTC)
        intent.block_reason = None
        self.session.add(
            AuditLog(
                profile_id=intent.profile_id,
                action="execution.intent_approved",
                actor=actor,
                actor_role=actor_role,
                session_id=session_id,
                details={"intent_id": intent.id, "symbol": intent.symbol, "mode": intent.mode.value},
            )
        )
        self.session.commit()
        self.session.refresh(intent)
        return intent

    def reject_intent(
        self,
        intent_id: str,
        *,
        actor: str,
        actor_role: str,
        reason: str,
        session_id: str | None = None,
    ) -> ExecutionIntent:
        intent = self._require_intent(intent_id)
        if intent.status in {ExecutionIntentStatus.EXECUTED, ExecutionIntentStatus.EXECUTING}:
            raise ValueError("Executed intents cannot be rejected.")
        intent.status = ExecutionIntentStatus.REJECTED
        intent.block_reason = reason
        self.session.add(
            AuditLog(
                profile_id=intent.profile_id,
                action="execution.intent_rejected",
                actor=actor,
                actor_role=actor_role,
                session_id=session_id,
                details={"intent_id": intent.id, "symbol": intent.symbol, "reason": reason},
            )
        )
        self.session.commit()
        self.session.refresh(intent)
        return intent

    def execute_intent(self, intent_id: str, *, settings_row: BotSettings) -> OrderRecord | None:
        intent = self._require_intent(intent_id)
        if intent.status == ExecutionIntentStatus.EXECUTED:
            return self.session.scalar(
                self._profile_order_query().where(OrderRecord.execution_intent_id == intent.id)
            )
        if intent.status != ExecutionIntentStatus.APPROVED:
            raise ValueError("Only approved intents can be executed.")
        if intent.intent_type != ExecutionIntentType.TRADE:
            raise ValueError(f"Unsupported execution intent type: {intent.intent_type.value}")

        session_state = MarketCalendarService.for_settings(settings_row).session_state(
            trading_pattern=settings_row.trading_pattern,
            instrument_class=settings_row.instrument_class,
        )
        if settings_row.kill_switch_enabled:
            self._block_intent(intent, "Kill switch is enabled.")
            return None
        if settings_row.mode != intent.mode:
            self._block_intent(intent, "Bot mode changed after the intent was approved.")
            return None
        if intent.mode == TradingMode.LIVE and not settings_row.live_enabled:
            self._block_intent(intent, "Live execution is not enabled.")
            return None
        if intent.mode == TradingMode.LIVE:
            from tradingbot.services.store import live_trading_env_allowed

            if not live_trading_env_allowed(settings_row):
                self._block_intent(intent, "This environment is not allowlisted for live execution.")
                return None
        if not session_state.can_submit_orders:
            self._block_intent(intent, session_state.reason or "Order submission is blocked outside session hours.")
            return None

        try:
            self.broker.get_account_snapshot()
        except BrokerAPIError as exc:
            self._fail_intent(intent, f"Broker connectivity check failed: {exc}")
            return None

        decision = CommitteeDecision.model_validate(intent.decision_payload)
        risk_result = RiskCheckResult.model_validate(intent.risk_payload)
        intent.status = ExecutionIntentStatus.EXECUTING
        self.session.commit()

        order = self.submit_trade(
            mode=intent.mode,
            decision=decision,
            risk_result=risk_result,
            decision_context=intent.decision_payload,
            execution_allowed=True,
            block_reason=intent.block_reason,
            instrument_class=settings_row.instrument_class or InstrumentClass.CASH_EQUITY,
            execution_intent_id=intent.id,
        )
        if order is None or order.status == OrderStatus.REJECTED:
            self._fail_intent(intent, "Order submission did not complete successfully.")
            return None

        intent.status = ExecutionIntentStatus.EXECUTED
        intent.executed_at = datetime.now(UTC)
        intent.last_error = None
        self.session.add(
            AuditLog(
                profile_id=intent.profile_id,
                action="execution.intent_executed",
                actor="system",
                actor_role="system",
                details={"intent_id": intent.id, "order_id": order.id, "broker_order_id": order.broker_order_id},
            )
        )
        self.session.commit()
        self.session.refresh(order)
        return order

    def submit_trade(
        self,
        *,
        mode: TradingMode,
        decision: CommitteeDecision,
        risk_result: RiskCheckResult,
        decision_context: dict[str, object] | None = None,
        execution_allowed: bool = True,
        block_reason: str | None = None,
        instrument_class: InstrumentClass = InstrumentClass.CASH_EQUITY,
        execution_intent_id: str | None = None,
    ) -> OrderRecord | None:
        if not execution_allowed:
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=decision.symbol,
                    severity="warning",
                    code="analysis_only_profile",
                    message=block_reason or "The selected broker/profile combination is analysis-only.",
                    payload={},
                )
            )
            self.session.commit()
            return None

        if risk_result.decision.value != "approved":
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=decision.symbol,
                    severity="warning",
                    code="risk_rejected",
                    message="Trade was rejected by deterministic risk rules.",
                    payload={"notes": risk_result.notes},
                )
            )
            self.session.commit()
            return None

        feature_snapshot = _extract_feature_snapshot(decision_context)
        liquidity_snapshot = self._safe_liquidity_snapshot(decision.symbol)
        execution_preview = self.execution_quality.preview_order(
            symbol=decision.symbol,
            side=decision.direction,
            quantity=risk_result.approved_quantity,
            intended_price=decision.entry,
            feature_snapshot=feature_snapshot,
            liquidity_snapshot=liquidity_snapshot,
            preferred_venue=None,
        )
        if not execution_preview.accepted:
            observe_counter("execution.quality_rejected", tags={"symbol": decision.symbol})
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=decision.symbol,
                    severity="warning",
                    code="execution_quality_rejected",
                    message="Order blocked by execution-quality expectations before broker submission.",
                    payload=execution_preview.to_payload(),
                )
            )
            self.session.commit()
            return None

        client_order_id = f"{decision.symbol.lower()}-{uuid4().hex[:20]}"
        request = OrderRequest(
            symbol=decision.symbol,
            quantity=risk_result.approved_quantity,
            side=decision.direction,
            order_type=execution_preview.order_type,
            time_in_force=execution_preview.time_in_force,
            limit_price=execution_preview.entry_limit_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            reference_price=execution_preview.reference_price,
            client_order_id=client_order_id,
            metadata={"execution_quality": execution_preview.to_payload()},
        )

        account_snapshot = self.broker.get_account_snapshot()
        pretrade_result = self.pretrade.validate(
            order=request,
            instrument_class=instrument_class,
            account=account_snapshot,
        )
        if not pretrade_result.accepted:
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=decision.symbol,
                    severity="warning",
                    code="pretrade_rejected",
                    message="Order blocked by pre-trade broker/exchange validation.",
                    payload={"reasons": pretrade_result.reasons},
                )
            )
            self.session.commit()
            return None

        order = OrderRecord(
            profile_id=self.profile_id,
            execution_intent_id=execution_intent_id,
            symbol=decision.symbol,
            mode=mode,
            direction=request.side,
            order_type=request.order_type,
            time_in_force=request.time_in_force,
            quantity=risk_result.approved_quantity,
            limit_price=request.limit_price,
            stop_loss=decision.stop_loss,
            stop_price=decision.stop_loss,
            take_profit=decision.take_profit,
            status=OrderStatus.NEW,
            client_order_id=client_order_id,
            submitted_at=datetime.now(UTC),
            metadata_json={
                "decision": decision_context or decision.model_dump(mode="json"),
                "execution_quality": {
                    **execution_preview.to_payload(),
                    "broker_slug": self.broker.broker_slug.value,
                    "venue": execution_preview.venue,
                },
            },
        )
        self.session.add(order)
        self.session.flush()
        self._transition_order(
            order,
            to_status=OrderStatus.NEW,
            source="local",
            message="Local order intent created.",
            payload={"client_order_id": client_order_id},
            force=True,
        )

        try:
            broker_order = self.broker.place_order(request)
        except Exception as exc:  # noqa: BLE001
            observe_counter("execution.broker_submit_failed", tags={"symbol": decision.symbol})
            self._transition_order(
                order,
                to_status=OrderStatus.REJECTED,
                source="broker",
                message=f"Broker rejected order submission: {exc}",
                payload={"error": str(exc)},
                force=True,
            )
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=decision.symbol,
                    severity="critical",
                    code="broker_submit_failed",
                    message="Broker order submission failed.",
                    payload={"error": str(exc)},
                )
            )
            self._record_execution_sample(order, source="broker_submit")
            self.session.commit()
            return order

        self.apply_broker_order_update(order, broker_order, source="broker_submit")
        self._ingest_immediate_broker_fill(order, broker_order, source="broker_submit")
        self.session.commit()
        self.session.refresh(order)
        return order

    def replace_order(self, order_id: int, patch: ReplaceOrderRequest) -> OrderRecord:
        order = self._require_order(order_id)
        if not order.broker_order_id:
            raise ValueError("Cannot replace an order without a broker_order_id.")

        broker_order = self.broker.replace_order(order.broker_order_id, patch)
        self._transition_order(
            order,
            to_status=OrderStatus.REPLACED,
            source="broker",
            message="Replace request accepted by broker.",
            payload={"patch": _serialize_replace_patch(patch)},
            force=True,
        )
        self.apply_broker_order_update(order, broker_order, source="broker_replace")
        self.session.commit()
        self.session.refresh(order)
        return order

    def cancel_order(self, order_id: int) -> OrderRecord:
        order = self._require_order(order_id)
        if not order.broker_order_id:
            raise ValueError("Cannot cancel an order without a broker_order_id.")

        self.broker.cancel_order(order.broker_order_id)
        self._transition_order(
            order,
            to_status=OrderStatus.CANCELED,
            source="broker",
            message="Cancel request acknowledged.",
            payload={},
            force=True,
        )
        self._record_execution_sample(order, source="cancel_order")
        self.session.commit()
        self.session.refresh(order)
        return order

    def cancel_all_open_orders(self) -> int:
        canceled_count = self.broker.cancel_all_orders()
        local_open_orders = self.session.scalars(
            self._profile_order_query().where(OrderRecord.status.notin_(tuple(TERMINAL_STATUSES)))
        ).all()
        for order in local_open_orders:
            self._transition_order(
                order,
                to_status=OrderStatus.CANCELED,
                source="broker",
                message="Canceled by cancel-all command.",
                payload={},
                force=True,
            )
            self._record_execution_sample(order, source="cancel_all")
        self.session.commit()
        return canceled_count

    def apply_broker_order_update(self, order: OrderRecord, broker_order: BrokerOrder, *, source: str) -> bool:
        changed = False
        order.broker_order_id = broker_order.broker_order_id or order.broker_order_id
        order.status_reason = broker_order.status_reason
        order.quantity = broker_order.quantity or order.quantity
        order.filled_quantity = max(order.filled_quantity, broker_order.filled_quantity)
        order.average_fill_price = broker_order.average_fill_price or order.average_fill_price
        order.limit_price = broker_order.limit_price if broker_order.limit_price is not None else order.limit_price
        order.stop_price = broker_order.stop_price if broker_order.stop_price is not None else order.stop_price
        order.take_profit = broker_order.take_profit if broker_order.take_profit is not None else order.take_profit
        order.trailing_percent = (
            broker_order.trailing_percent if broker_order.trailing_percent is not None else order.trailing_percent
        )
        order.trailing_amount = broker_order.trailing_amount if broker_order.trailing_amount is not None else order.trailing_amount
        order.last_broker_update_at = broker_order.updated_at or datetime.now(UTC)
        order.metadata_json = {
            **(order.metadata_json or {}),
            "last_broker_snapshot": broker_order.raw,
        }

        if order.status != broker_order.status:
            changed = self._transition_order(
                order,
                to_status=broker_order.status,
                source=source,
                message=broker_order.status_reason or "Broker status update.",
                payload={"broker_order_id": broker_order.broker_order_id},
            )

        if broker_order.status in TERMINAL_STATUSES or order.status in TERMINAL_STATUSES:
            self._record_execution_sample(order, source=source)

        return changed

    def ingest_broker_fill(self, fill: BrokerFill, *, source: str) -> bool:
        if fill.broker_fill_id:
            existing = self.session.scalar(
                self._profile_fill_query().where(OrderFill.broker_fill_id == fill.broker_fill_id)
            )
            if existing is not None:
                return False

        order = None
        if fill.broker_order_id:
            order = self.session.scalar(
                self._profile_order_query().where(OrderRecord.broker_order_id == fill.broker_order_id)
            )
        if order is None:
            order = self.session.scalar(
                self._profile_order_query()
                .where(OrderRecord.symbol == fill.symbol)
                .where(OrderRecord.status.notin_(tuple(TERMINAL_STATUSES)))
                .order_by(OrderRecord.created_at.desc())
            )
        if order is None:
            return False

        self.session.add(
            OrderFill(
                profile_id=order.profile_id,
                order_id=order.id,
                broker_fill_id=fill.broker_fill_id,
                broker_order_id=fill.broker_order_id,
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                fee=fill.fee,
                filled_at=fill.filled_at,
                payload=fill.raw,
            )
        )

        order.filled_quantity = min(order.quantity, order.filled_quantity + fill.quantity)
        if order.average_fill_price is None:
            order.average_fill_price = fill.price
        else:
            weighted_total = (order.average_fill_price * max(order.filled_quantity - fill.quantity, 0)) + (
                fill.price * fill.quantity
            )
            order.average_fill_price = weighted_total / max(order.filled_quantity, 1)

        target_status = (
            OrderStatus.FILLED if order.filled_quantity >= order.quantity else OrderStatus.PARTIALLY_FILLED
        )
        self._transition_order(
            order,
            to_status=target_status,
            source=source,
            message="Broker fill ingested.",
            payload={"fill_id": fill.broker_fill_id, "qty": fill.quantity, "price": fill.price},
            force=True,
        )
        self._apply_fill_to_position(order.symbol, fill.quantity, fill.price, fill.side)
        self._record_execution_sample(order, source=source)
        if target_status == OrderStatus.FILLED and order.direction == OrderIntent.SELL:
            review = self.trade_reviews.queue_review_for_exit_order(order)
            if review is not None:
                self._portfolio_risk_service().upsert_cooldown_from_exit(
                    symbol=order.symbol,
                    pnl=review.pnl,
                    return_pct=review.return_pct,
                    review_payload=review.review_payload,
                    as_of=fill.filled_at,
                )
        return True

    def sync_positions_snapshot(self, broker_positions: list[BrokerPosition], *, source: str) -> None:
        local_positions = self.session.scalars(self._profile_position_query()).all()
        local_by_symbol = {row.symbol: row for row in local_positions}

        seen_symbols: set[str] = set()
        for broker_position in broker_positions:
            symbol = broker_position.symbol.upper().strip()
            seen_symbols.add(symbol)
            local = local_by_symbol.get(symbol)
            if local is None:
                local = PositionRecord(
                    profile_id=self.profile_id,
                    symbol=symbol,
                    quantity=broker_position.quantity,
                    average_entry_price=broker_position.average_entry_price,
                    market_value=broker_position.market_value,
                    unrealized_pl=broker_position.unrealized_pl,
                    side=broker_position.side,
                    broker_position_id=broker_position.broker_position_id,
                )
                self.session.add(local)
            else:
                local.quantity = broker_position.quantity
                local.average_entry_price = broker_position.average_entry_price
                local.market_value = broker_position.market_value
                local.unrealized_pl = broker_position.unrealized_pl
                local.side = broker_position.side
                local.broker_position_id = broker_position.broker_position_id

        for symbol, position in local_by_symbol.items():
            if symbol in seen_symbols:
                continue
            self.session.delete(position)

        self.session.flush()

    def repair_broken_child_orders(self) -> int:
        repaired = 0
        parent_orders = self.session.scalars(
            self._profile_order_query()
            .where(OrderRecord.order_type == OrderType.BRACKET)
            .where(OrderRecord.status.in_([OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED]))
            .where(OrderRecord.filled_quantity > 0)
        ).all()

        for parent in parent_orders:
            children = self.session.scalars(
                self._profile_order_query().where(OrderRecord.parent_order_id == parent.id)
            ).all()
            has_stop = any(child.order_type in {OrderType.STOP_MARKET, OrderType.STOP_LIMIT} for child in children)
            has_take_profit = any(child.order_type == OrderType.LIMIT for child in children)

            required_qty = parent.filled_quantity
            if required_qty <= 0:
                continue

            if not has_stop and parent.stop_loss:
                self._submit_child_order(
                    parent,
                    OrderRequest(
                        symbol=parent.symbol,
                        quantity=required_qty,
                        side=OrderIntent.SELL,
                        order_type=OrderType.STOP_MARKET,
                        stop_price=parent.stop_loss,
                    ),
                    reason="Repaired missing stop-loss child order.",
                )
                repaired += 1

            if not has_take_profit and parent.take_profit:
                self._submit_child_order(
                    parent,
                    OrderRequest(
                        symbol=parent.symbol,
                        quantity=required_qty,
                        side=OrderIntent.SELL,
                        order_type=OrderType.LIMIT,
                        limit_price=parent.take_profit,
                    ),
                    reason="Repaired missing take-profit child order.",
                )
                repaired += 1

        self.session.commit()
        return repaired

    def flatten_all_positions(
        self,
        *,
        mode: TradingMode,
        actor: str = "system",
        actor_role: str = "system",
        session_id: str | None = None,
        reason: str = "manual_flatten",
    ) -> int:
        local_positions = self.session.scalars(
            self._profile_position_query().where(PositionRecord.quantity > 0)
        ).all()
        flatten_submitted = self.broker.close_all_positions()
        for position in local_positions:
            self.session.delete(position)
        self.session.add(
            AuditLog(
                profile_id=self.profile_id,
                action="execution.flatten_all",
                actor=actor,
                actor_role=actor_role,
                session_id=session_id,
                details={"mode": mode.value, "flattened_positions": len(local_positions), "reason": reason},
            )
        )
        self.session.commit()
        return flatten_submitted

    def broker_kill(
        self,
        *,
        actor: str,
        actor_role: str,
        session_id: str | None = None,
        reason: str = "broker_kill",
    ) -> int:
        canceled_orders = self.cancel_all_open_orders()
        self.session.add(
            AuditLog(
                profile_id=self.profile_id,
                action="execution.broker_kill",
                actor=actor,
                actor_role=actor_role,
                session_id=session_id,
                details={"canceled_orders": canceled_orders, "reason": reason},
            )
        )
        self.session.commit()
        return canceled_orders

    def list_order_transitions(self, order_id: int) -> list[OrderStateTransition]:
        return list(
            self.session.scalars(
            select(OrderStateTransition)
            .where(OrderStateTransition.order_id == order_id)
            .where(OrderStateTransition.profile_id == self.profile_id)
            .order_by(OrderStateTransition.transition_at.asc())
            ).all()
        )

    def list_order_fills(self, order_id: int) -> list[OrderFill]:
        return list(
            self.session.scalars(
            select(OrderFill)
            .where(OrderFill.order_id == order_id)
            .where(OrderFill.profile_id == self.profile_id)
            .order_by(OrderFill.filled_at.asc())
            ).all()
        )

    def current_symbol_exposure(self, symbol: str) -> float:
        position = self.session.scalar(
            self._profile_position_query().where(PositionRecord.symbol == symbol.upper().strip())
        )
        return position.market_value if position else 0.0

    def execution_feedback_for_symbol(self, symbol: str) -> dict[str, object]:
        return self.execution_quality.feedback_for_symbol(symbol).to_payload()

    def execution_quality_summary(self, *, dimension: str, limit: int) -> list[dict[str, object]]:
        return self.execution_quality.summarize(dimension=dimension, limit=limit)

    def _require_order(self, order_id: int) -> OrderRecord:
        row = self.session.get(OrderRecord, order_id)
        if row is None or (self.profile_id is not None and row.profile_id != self.profile_id):
            raise ValueError(f"Order {order_id} was not found.")
        return row

    def _require_intent(self, intent_id: str) -> ExecutionIntent:
        row = self.session.get(ExecutionIntent, intent_id)
        if row is None or (self.profile_id is not None and row.profile_id != self.profile_id):
            raise ValueError(f"Execution intent {intent_id} was not found.")
        return row

    def _block_intent(self, intent: ExecutionIntent, reason: str) -> None:
        intent.status = ExecutionIntentStatus.BLOCKED
        intent.block_reason = reason
        intent.failed_at = datetime.now(UTC)
        observe_counter("execution.intent_blocked", tags={"mode": intent.mode.value})
        self.session.add(
            AuditLog(
                profile_id=intent.profile_id,
                action="execution.intent_blocked",
                actor="system",
                actor_role="system",
                details={"intent_id": intent.id, "reason": reason},
            )
        )
        self.session.commit()
        return None

    def _fail_intent(self, intent: ExecutionIntent, reason: str) -> None:
        intent.status = ExecutionIntentStatus.FAILED
        intent.last_error = reason
        intent.failed_at = datetime.now(UTC)
        observe_counter("execution.intent_failed", tags={"mode": intent.mode.value})
        self.session.add(
            AuditLog(
                profile_id=intent.profile_id,
                action="execution.intent_failed",
                actor="system",
                actor_role="system",
                details={"intent_id": intent.id, "reason": reason},
            )
        )
        self.session.commit()
        return None

    def _submit_child_order(self, parent: OrderRecord, request: OrderRequest, *, reason: str) -> None:
        client_order_id = f"child-{parent.id}-{uuid4().hex[:12]}"
        request.client_order_id = client_order_id
        local_child = OrderRecord(
            profile_id=parent.profile_id,
            symbol=request.symbol,
            mode=parent.mode,
            direction=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            status=OrderStatus.NEW,
            client_order_id=client_order_id,
            parent_order_id=parent.id,
            submitted_at=datetime.now(UTC),
            metadata_json={"repair_reason": reason},
        )
        self.session.add(local_child)
        self.session.flush()
        self._transition_order(
            local_child,
            to_status=OrderStatus.NEW,
            source="local",
            message=reason,
            payload={},
            force=True,
        )
        broker_child = self.broker.place_order(request)
        self.apply_broker_order_update(local_child, broker_child, source="repair")

    def _transition_order(
        self,
        order: OrderRecord,
        *,
        to_status: OrderStatus,
        source: str,
        message: str,
        payload: dict,
        force: bool = False,
    ) -> bool:
        current_status = order.status
        if current_status == to_status and not force:
            return False

        allowed = STATE_TRANSITIONS.get(current_status, set())
        if not force and to_status not in allowed:
            self.session.add(
                RiskEvent(
                    profile_id=order.profile_id,
                    symbol=order.symbol,
                    severity="warning",
                    code="order_invalid_transition",
                    message=(
                        f"Blocked invalid order-state transition from {current_status.value} to {to_status.value}."
                    ),
                    payload={"order_id": order.id, "source": source},
                )
            )
            to_status = OrderStatus.SUSPENDED
            message = f"Order moved to suspended due to invalid transition attempt: {message}"

        if current_status == to_status and not force:
            return False

        transition = OrderStateTransition(
            profile_id=order.profile_id,
            order_id=order.id,
            symbol=order.symbol,
            from_status=current_status,
            to_status=to_status,
            transition_at=datetime.now(UTC),
            source=source,
            message=message,
            payload=payload,
        )
        self.session.add(transition)
        order.status = to_status
        order.status_reason = message
        order.last_broker_update_at = datetime.now(UTC)
        return True

    def _apply_fill_to_position(self, symbol: str, quantity: int, price: float, side: str) -> None:
        normalized_symbol = symbol.upper().strip()
        position = self.session.scalar(
            self._profile_position_query().where(PositionRecord.symbol == normalized_symbol)
        )
        buy_fill = side.lower() == "buy"

        if position is None and not buy_fill:
            return

        if position is None:
            position = PositionRecord(
                profile_id=self.profile_id,
                symbol=normalized_symbol,
                quantity=quantity,
                average_entry_price=price,
                market_value=quantity * price,
                unrealized_pl=0.0,
                side="long",
            )
            self.session.add(position)
            return

        if buy_fill:
            new_qty = position.quantity + quantity
            weighted_total = (position.average_entry_price * position.quantity) + (price * quantity)
            position.quantity = new_qty
            position.average_entry_price = weighted_total / max(new_qty, 1)
            position.market_value = position.quantity * position.average_entry_price
            position.side = "long"
        else:
            position.quantity = max(position.quantity - quantity, 0)
            if position.quantity == 0:
                self.session.delete(position)
            else:
                position.market_value = position.quantity * position.average_entry_price

    def _portfolio_risk_service(self) -> PortfolioRiskService:
        return PortfolioRiskService(self.session, risk_policy_from_settings(self.settings_row), profile_id=self.profile_id)

    def _safe_liquidity_snapshot(self, symbol: str):
        getter = getattr(self.broker, "get_liquidity_snapshot", None)
        if not callable(getter):
            return None
        try:
            return getter(symbol)
        except Exception as exc:  # noqa: BLE001
            self.session.add(
                RiskEvent(
                    profile_id=self.profile_id,
                    symbol=symbol,
                    severity="warning",
                    code="execution_liquidity_unavailable",
                    message="Failed to fetch liquidity snapshot for execution-quality checks.",
                    payload={"error": str(exc)},
                )
            )
            return None

    def _record_execution_sample(self, order: OrderRecord, *, source: str) -> None:
        try:
            self.execution_quality.upsert_order_sample(order)
        except Exception as exc:  # noqa: BLE001
            self.session.add(
                RiskEvent(
                    profile_id=order.profile_id,
                    symbol=order.symbol,
                    severity="warning",
                    code="execution_quality_capture_failed",
                    message="Failed to persist execution-quality analytics for order.",
                    payload={"order_id": order.id, "source": source, "error": str(exc)},
                )
            )

    def _ingest_immediate_broker_fill(self, order: OrderRecord, broker_order: BrokerOrder, *, source: str) -> None:
        if broker_order.filled_quantity <= 0 or broker_order.average_fill_price is None:
            return
        fill_id = str(
            broker_order.raw.get("fill_id")
            or broker_order.raw.get("broker_fill_id")
            or f"{broker_order.broker_order_id}-fill"
        )
        fill_time = _to_datetime(
            broker_order.raw.get("filled_at")
            or broker_order.raw.get("fill_time")
            or broker_order.raw.get("updated_at")
        ) or broker_order.updated_at or datetime.now(UTC)
        self.ingest_broker_fill(
            BrokerFill(
                broker_fill_id=fill_id,
                broker_order_id=broker_order.broker_order_id,
                symbol=broker_order.symbol,
                side=broker_order.side.value,
                quantity=broker_order.filled_quantity,
                price=broker_order.average_fill_price,
                fee=0.0,
                filled_at=fill_time,
                raw=broker_order.raw,
            ),
            source=source,
        )



def _serialize_replace_patch(patch: ReplaceOrderRequest) -> dict[str, object]:
    payload: dict[str, object] = {}
    if patch.quantity is not None:
        payload["quantity"] = patch.quantity
    if patch.limit_price is not None:
        payload["limit_price"] = patch.limit_price
    if patch.stop_price is not None:
        payload["stop_price"] = patch.stop_price
    if patch.take_profit is not None:
        payload["take_profit"] = patch.take_profit
    if patch.time_in_force is not None:
        payload["time_in_force"] = patch.time_in_force.value
    return payload


def _extract_feature_snapshot(decision_context: dict[str, object] | None) -> dict[str, float]:
    if not isinstance(decision_context, dict):
        return {}
    raw = decision_context.get("feature_snapshot")
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, float] = {}
    for key, value in raw.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized
