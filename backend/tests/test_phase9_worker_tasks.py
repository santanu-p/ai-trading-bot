from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import pytest

pytest.importorskip("celery")

from tradingbot.db import Base
from tradingbot.enums import ExecutionIntentStatus, TradingMode
from tradingbot.models import ExecutionIntent
from tradingbot.worker import execution_tasks
from tradingbot.worker.replay_tasks import run_replay_regression


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _intent(intent_id: str, *, status: ExecutionIntentStatus) -> ExecutionIntent:
    return ExecutionIntent(
        id=intent_id,
        mode=TradingMode.PAPER,
        status=status,
        idempotency_key=f"{intent_id}-idempotency",
        requires_human_approval=False,
        decision_payload={},
        risk_payload={},
        metadata_json={},
    )


def test_phase9_dispatch_ready_intents_enqueues_all_approved(monkeypatch) -> None:
    factory = _session_factory()
    session = factory()
    session.add_all(
        [
            _intent("phase9-approved-1", status=ExecutionIntentStatus.APPROVED),
            _intent("phase9-approved-2", status=ExecutionIntentStatus.APPROVED),
            _intent("phase9-pending", status=ExecutionIntentStatus.PENDING_APPROVAL),
        ]
    )
    session.commit()
    session.close()

    queued_ids: list[str] = []

    def _fake_delay(intent_id: str) -> None:
        queued_ids.append(intent_id)

    monkeypatch.setattr(execution_tasks, "get_session_factory", lambda: factory)
    monkeypatch.setattr(execution_tasks.execute_intent, "delay", _fake_delay)

    result = execution_tasks.dispatch_ready_intents()

    assert result["queued"] == 2
    assert set(queued_ids) == {"phase9-approved-1", "phase9-approved-2"}


def test_phase9_replay_worker_task_returns_digest_and_snapshot() -> None:
    report = run_replay_regression("AAPL")

    assert report["symbol"] == "AAPL"
    assert isinstance(report["digest"], str)
    assert len(report["digest"]) == 64
    assert isinstance(report["snapshot"], dict)
