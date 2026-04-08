from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import OrderStatus, TradingMode
from tradingbot.models import BotSettings, OrderFill, OrderRecord, ReconciliationMismatch, RiskEvent
from tradingbot.services.adapters import BrokerAPIError, ExecutionAdapter
from tradingbot.services.alerts import AlertService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.metrics import observe_counter

TERMINAL_ORDER_STATES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.EXPIRED,
    OrderStatus.REPLACED,
    OrderStatus.REJECTED,
}


@dataclass(slots=True)
class ReconciliationReport:
    transitions_applied: int
    fills_ingested: int
    mismatches_created: int
    unresolved_mismatches: int
    live_paused: bool


class ReconciliationService:
    def __init__(
        self,
        *,
        session: Session,
        settings_row: BotSettings,
        execution: ExecutionService,
        adapter: ExecutionAdapter,
    ) -> None:
        self.session = session
        self.settings_row = settings_row
        self.execution = execution
        self.adapter = adapter

    def reconcile(self) -> ReconciliationReport:
        transitions = 0
        fills_ingested = 0
        mismatches_created = 0
        alerts = AlertService(self.session)

        local_orders = self.session.scalars(
            select(OrderRecord).where(OrderRecord.broker_order_id.is_not(None)).order_by(OrderRecord.id.asc())
        ).all()
        local_by_broker_id = {order.broker_order_id: order for order in local_orders if order.broker_order_id}

        broker_open_orders = self.adapter.list_open_orders()
        broker_open_ids = {order.broker_order_id for order in broker_open_orders}

        for broker_order in broker_open_orders:
            local = local_by_broker_id.get(broker_order.broker_order_id)
            if local is None:
                created = self._record_mismatch(
                    mismatch_type="local_missing_order",
                    symbol=broker_order.symbol,
                    local_reference=None,
                    broker_reference=broker_order.broker_order_id,
                    details={"broker_order": broker_order.raw},
                )
                mismatches_created += int(created)
                continue

            changed = self.execution.apply_broker_order_update(
                local,
                broker_order,
                source="reconciliation",
            )
            transitions += int(changed)
            self._resolve_mismatch(
                mismatch_type="local_missing_order",
                local_reference=None,
                broker_reference=broker_order.broker_order_id,
            )

        for local in local_orders:
            if local.status in TERMINAL_ORDER_STATES:
                continue
            if not local.broker_order_id:
                continue
            if local.broker_order_id in broker_open_ids:
                continue
            try:
                broker_snapshot = self.adapter.get_order(local.broker_order_id)
            except BrokerAPIError as exc:
                if exc.category == "not_found":
                    created = self._record_mismatch(
                        mismatch_type="broker_missing_order",
                        symbol=local.symbol,
                        local_reference=str(local.id),
                        broker_reference=local.broker_order_id,
                        details={"error": str(exc)},
                    )
                    mismatches_created += int(created)
                continue

            changed = self.execution.apply_broker_order_update(local, broker_snapshot, source="reconciliation")
            transitions += int(changed)
            self._resolve_mismatch(
                mismatch_type="broker_missing_order",
                local_reference=str(local.id),
                broker_reference=local.broker_order_id,
            )

        last_fill_at = self.session.scalar(select(func.max(OrderFill.filled_at)))
        fills = self.adapter.fetch_fills(since=last_fill_at, limit=500)
        for fill in fills:
            if self.execution.ingest_broker_fill(fill, source="reconciliation"):
                fills_ingested += 1

        self.execution.sync_positions_snapshot(self.adapter.list_positions(), source="reconciliation")

        unresolved_count = self.session.scalar(
            select(func.count()).select_from(ReconciliationMismatch).where(ReconciliationMismatch.resolved.is_(False))
        )
        unresolved_count = int(unresolved_count or 0)

        live_paused = False
        if unresolved_count > 0 and self.settings_row.mode == TradingMode.LIVE:
            if not self.settings_row.kill_switch_enabled:
                self.settings_row.kill_switch_enabled = True
                self.session.add(
                    RiskEvent(
                        symbol=None,
                        severity="critical",
                        code="reconciliation_unresolved",
                        message="Live trading paused because broker reconciliation mismatches remain unresolved.",
                        payload={"count": unresolved_count},
                    )
                )
            alerts.notify_reconciliation_unresolved(
                unresolved_mismatches=unresolved_count,
                source="reconciliation_service",
                details={"mismatches_created": mismatches_created},
            )
            observe_counter("reconciliation.live_paused", tags={"unresolved": str(unresolved_count)})
            live_paused = True

        self.session.commit()
        return ReconciliationReport(
            transitions_applied=transitions,
            fills_ingested=fills_ingested,
            mismatches_created=mismatches_created,
            unresolved_mismatches=unresolved_count,
            live_paused=live_paused,
        )

    def _record_mismatch(
        self,
        *,
        mismatch_type: str,
        symbol: str | None,
        local_reference: str | None,
        broker_reference: str | None,
        details: dict,
    ) -> bool:
        existing = self.session.scalar(
            select(ReconciliationMismatch)
            .where(ReconciliationMismatch.broker_slug == self.settings_row.broker_slug)
            .where(ReconciliationMismatch.mismatch_type == mismatch_type)
            .where(ReconciliationMismatch.local_reference == local_reference)
            .where(ReconciliationMismatch.broker_reference == broker_reference)
            .where(ReconciliationMismatch.resolved.is_(False))
        )
        if existing is not None:
            existing.details = details
            return False

        self.session.add(
            ReconciliationMismatch(
                broker_slug=self.settings_row.broker_slug,
                symbol=symbol,
                mismatch_type=mismatch_type,
                severity="critical",
                local_reference=local_reference,
                broker_reference=broker_reference,
                details=details,
                resolved=False,
            )
        )
        return True

    def _resolve_mismatch(
        self,
        *,
        mismatch_type: str,
        local_reference: str | None,
        broker_reference: str | None,
    ) -> None:
        row = self.session.scalar(
            select(ReconciliationMismatch)
            .where(ReconciliationMismatch.broker_slug == self.settings_row.broker_slug)
            .where(ReconciliationMismatch.mismatch_type == mismatch_type)
            .where(ReconciliationMismatch.local_reference == local_reference)
            .where(ReconciliationMismatch.broker_reference == broker_reference)
            .where(ReconciliationMismatch.resolved.is_(False))
        )
        if row is None:
            return
        row.resolved = True
        row.resolved_at = datetime.now(UTC)
