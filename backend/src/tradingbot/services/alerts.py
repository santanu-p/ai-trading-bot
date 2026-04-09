from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import RunStatus
from tradingbot.models import AgentRun, AuditLog, BotSettings, RiskEvent, TradeCandidate
from tradingbot.services.alert_dispatch import dispatch_alert_webhooks
from tradingbot.services.metrics import observe_counter


@dataclass(slots=True)
class AlertThresholds:
    worker_failure_threshold: int = 3
    worker_failure_window_minutes: int = 30
    rejection_rate_threshold: float = 0.65
    rejection_rate_min_samples: int = 8
    rejection_window_minutes: int = 60
    malformed_threshold: int = 3
    malformed_window_minutes: int = 60
    dedupe_minutes: int = 30


class AlertService:
    def __init__(self, session: Session, *, thresholds: AlertThresholds | None = None) -> None:
        self.session = session
        self.thresholds = thresholds or AlertThresholds()

    def evaluate_runtime_alerts(self, *, now: datetime | None = None) -> int:
        as_of = now or datetime.now(UTC)
        emitted = 0
        emitted += int(self._alert_repeated_worker_failures(as_of=as_of))
        emitted += int(self._alert_high_rejection_rate(as_of=as_of))
        emitted += int(self._alert_malformed_rate(as_of=as_of))
        return emitted

    def notify_kill_switch(self, *, source: str, details: dict | None = None) -> bool:
        payload = {"source": source, **(details or {})}
        return self._emit_alert(
            code="alert_kill_switch_activated",
            severity="critical",
            message="Kill switch has been activated.",
            payload=payload,
            dedupe_minutes=10,
        )

    def notify_reconciliation_unresolved(
        self,
        *,
        unresolved_mismatches: int,
        source: str,
        details: dict | None = None,
    ) -> bool:
        payload = {
            "unresolved_mismatches": unresolved_mismatches,
            "source": source,
            **(details or {}),
        }
        return self._emit_alert(
            code="alert_reconciliation_unresolved",
            severity="critical",
            message="Unresolved reconciliation mismatches paused live operations.",
            payload=payload,
            dedupe_minutes=15,
        )

    def recent_alerts(self, *, limit: int = 50) -> list[RiskEvent]:
        query = (
            select(RiskEvent)
            .where(RiskEvent.code.like("alert_%"))
            .order_by(RiskEvent.created_at.desc())
            .limit(max(limit, 1))
        )
        return list(self.session.scalars(query).all())

    def _alert_repeated_worker_failures(self, *, as_of: datetime) -> bool:
        window_start = as_of - timedelta(minutes=self.thresholds.worker_failure_window_minutes)
        failure_count = self.session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.created_at >= window_start)
            .where(AgentRun.status == RunStatus.FAILED)
        )
        count = int(failure_count or 0)
        if count < self.thresholds.worker_failure_threshold:
            return False

        return self._emit_alert(
            code="alert_worker_failures",
            severity="critical",
            message="Worker runs are repeatedly failing in the recent window.",
            payload={
                "failures": count,
                "window_minutes": self.thresholds.worker_failure_window_minutes,
            },
        )

    def _alert_high_rejection_rate(self, *, as_of: datetime) -> bool:
        window_start = as_of - timedelta(minutes=self.thresholds.rejection_window_minutes)
        total = self.session.scalar(
            select(func.count())
            .select_from(TradeCandidate)
            .where(TradeCandidate.created_at >= window_start)
        )
        total_count = int(total or 0)
        if total_count < self.thresholds.rejection_rate_min_samples:
            return False

        rejected = self.session.scalar(
            select(func.count())
            .select_from(TradeCandidate)
            .where(TradeCandidate.created_at >= window_start)
            .where(TradeCandidate.status != "approved")
        )
        rejected_count = int(rejected or 0)
        rejection_rate = rejected_count / max(total_count, 1)
        if rejection_rate < self.thresholds.rejection_rate_threshold:
            return False

        return self._emit_alert(
            code="alert_high_rejection_rate",
            severity="warning",
            message="Trade rejection rate is unusually high in the recent window.",
            payload={
                "rejection_rate": round(rejection_rate, 6),
                "rejected": rejected_count,
                "total": total_count,
                "window_minutes": self.thresholds.rejection_window_minutes,
            },
        )

    def _alert_malformed_rate(self, *, as_of: datetime) -> bool:
        window_start = as_of - timedelta(minutes=self.thresholds.malformed_window_minutes)
        malformed_count = self.session.scalar(
            select(func.count())
            .select_from(RiskEvent)
            .where(RiskEvent.created_at >= window_start)
            .where(RiskEvent.code == "agent_output_malformed")
        )
        count = int(malformed_count or 0)
        if count < self.thresholds.malformed_threshold:
            return False

        return self._emit_alert(
            code="alert_malformed_outputs",
            severity="warning",
            message="Malformed specialist outputs exceeded the configured threshold.",
            payload={
                "malformed_events": count,
                "window_minutes": self.thresholds.malformed_window_minutes,
            },
        )

    def _emit_alert(
        self,
        *,
        code: str,
        severity: str,
        message: str,
        payload: dict,
        dedupe_minutes: int | None = None,
    ) -> bool:
        dedupe_window = dedupe_minutes if dedupe_minutes is not None else self.thresholds.dedupe_minutes
        cutoff = datetime.now(UTC) - timedelta(minutes=max(dedupe_window, 1))
        existing = self.session.scalar(
            select(RiskEvent)
            .where(RiskEvent.code == code)
            .where(RiskEvent.created_at >= cutoff)
            .order_by(RiskEvent.created_at.desc())
        )
        if existing is not None:
            return False

        self.session.add(
            RiskEvent(
                symbol=None,
                severity=severity,
                code=code,
                message=message,
                payload=payload,
            )
        )
        self.session.add(
            AuditLog(
                action="alert.emitted",
                actor="system",
                actor_role="system",
                details={"code": code, "severity": severity, **payload},
            )
        )
        observe_counter("alerts.emitted", tags={"code": code, "severity": severity})
        dispatch_alert_webhooks(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "payload": payload,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        return True


def settings_alert_snapshot(session: Session) -> dict[str, object]:
    settings_row = session.get(BotSettings, 1)
    if settings_row is None:
        return {
            "kill_switch_enabled": False,
            "live_enabled": False,
            "mode": "paper",
        }
    return {
        "kill_switch_enabled": settings_row.kill_switch_enabled,
        "live_enabled": settings_row.live_enabled,
        "mode": settings_row.mode.value,
    }
