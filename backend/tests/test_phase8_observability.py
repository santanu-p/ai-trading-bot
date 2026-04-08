from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import OrderIntent, RunStatus
from tradingbot.models import AgentRun, RiskEvent, TradeCandidate
from tradingbot.services.alerts import AlertService, AlertThresholds
from tradingbot.services.metrics import metrics_registry, observe_counter, observe_duration_ms


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_phase8_alert_service_emits_runtime_signals() -> None:
    session = _session()
    now = datetime.now(UTC)

    for index in range(3):
        session.add(
            AgentRun(
                symbol=f"SYM{index}",
                status=RunStatus.FAILED,
                created_at=now - timedelta(minutes=10),
                updated_at=now - timedelta(minutes=10),
            )
        )

    healthy_run = AgentRun(symbol="AAPL", status=RunStatus.SUCCEEDED)
    session.add(healthy_run)
    session.flush()

    for index in range(10):
        session.add(
            TradeCandidate(
                run_id=healthy_run.id,
                symbol=f"T{index}",
                direction=OrderIntent.BUY,
                confidence=0.75,
                status="rejected" if index < 8 else "approved",
                thesis="Phase 8 alert test candidate.",
                entry=100.0,
                stop_loss=97.0,
                take_profit=105.0,
                risk_notes=[],
                raw_payload={},
                created_at=now - timedelta(minutes=5),
                updated_at=now - timedelta(minutes=5),
            )
        )

    for _ in range(3):
        session.add(
            RiskEvent(
                symbol="AAPL",
                severity="warning",
                code="agent_output_malformed",
                message="Malformed specialist payload.",
                payload={},
                created_at=now - timedelta(minutes=2),
                updated_at=now - timedelta(minutes=2),
            )
        )

    session.commit()
    service = AlertService(
        session,
        thresholds=AlertThresholds(
            worker_failure_threshold=1,
            rejection_rate_threshold=0.1,
            rejection_rate_min_samples=1,
            malformed_threshold=1,
            dedupe_minutes=1,
        ),
    )
    emitted = service.evaluate_runtime_alerts(now=now)
    service.notify_kill_switch(source="unit_test")
    service.notify_reconciliation_unresolved(unresolved_mismatches=4, source="unit_test")
    session.commit()

    alert_codes = set(
        session.scalars(select(RiskEvent.code).where(RiskEvent.code.like("alert_%"))).all()
    )

    assert emitted >= 3
    assert "alert_worker_failures" in alert_codes
    assert "alert_high_rejection_rate" in alert_codes
    assert "alert_malformed_outputs" in alert_codes
    assert "alert_kill_switch_activated" in alert_codes
    assert "alert_reconciliation_unresolved" in alert_codes


def test_phase8_metrics_registry_summarizes_counter_and_latency() -> None:
    suffix = datetime.now(UTC).strftime("%H%M%S%f")
    counter_name = f"phase8.counter.{suffix}"
    latency_name = f"phase8.latency.{suffix}"

    observe_counter(counter_name, value=2, tags={"scope": "unit"})
    observe_counter(counter_name, value=3, tags={"scope": "unit"})
    observe_duration_ms(latency_name, duration_ms=10.0, tags={"scope": "unit"})
    observe_duration_ms(latency_name, duration_ms=30.0, tags={"scope": "unit"})

    counters, latencies = metrics_registry().summarize(window_minutes=10)

    counter_row = next(item for item in counters if item.name == counter_name)
    latency_row = next(item for item in latencies if item.name == latency_name)

    assert counter_row.value == 5.0
    assert counter_row.tags["scope"] == "unit"
    assert latency_row.samples == 2
    assert latency_row.avg_ms == 20.0
    assert latency_row.max_ms == 30.0
