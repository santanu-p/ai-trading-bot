from __future__ import annotations

from time import perf_counter

from celery.result import AsyncResult

from tradingbot.db import get_session_factory
from tradingbot.models import ExecutionIntent, ExecutionIntentStatus
from tradingbot.services.adapters import build_broker_adapter
from tradingbot.services.execution import ExecutionService
from tradingbot.services.metrics import observe_counter, observe_duration_ms
from tradingbot.services.store import ensure_bot_settings
from tradingbot.worker.celery_app import celery_app


def enqueue_execution_intent(intent_id: str) -> AsyncResult:
    return execute_intent.delay(intent_id)


def enqueue_session_flatten(reason: str) -> AsyncResult:
    return flatten_all_positions.delay(reason)


@celery_app.task(name="tradingbot.worker.execution_tasks.execute_intent")
def execute_intent(intent_id: str) -> dict[str, str]:
    started = perf_counter()
    observe_counter("worker.execute_intent.invocations")
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session)
        broker = build_broker_adapter(settings_row)
        service = ExecutionService(session, broker)
        order = service.execute_intent(intent_id, settings_row=settings_row)
        observe_counter("worker.execute_intent.completed")
        return {"intent_id": intent_id, "status": order.status.value if order else "blocked"}
    except Exception:
        observe_counter("worker.execute_intent.failures")
        raise
    finally:
        observe_duration_ms("worker.execute_intent.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()


@celery_app.task(name="tradingbot.worker.execution_tasks.flatten_all_positions")
def flatten_all_positions(reason: str) -> dict[str, int | str]:
    started = perf_counter()
    observe_counter("worker.flatten_all.invocations")
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session)
        broker = build_broker_adapter(settings_row)
        service = ExecutionService(session, broker)
        flattened = service.flatten_all_positions(mode=settings_row.mode, reason=reason)
        observe_counter("worker.flatten_all.completed")
        return {"flattened": flattened, "reason": reason}
    except Exception:
        observe_counter("worker.flatten_all.failures")
        raise
    finally:
        observe_duration_ms("worker.flatten_all.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()


@celery_app.task(name="tradingbot.worker.execution_tasks.dispatch_ready_intents")
def dispatch_ready_intents() -> dict[str, int]:
    started = perf_counter()
    observe_counter("worker.dispatch_intents.invocations")
    session = get_session_factory()()
    try:
        ready = session.query(ExecutionIntent).filter(ExecutionIntent.status == ExecutionIntentStatus.APPROVED).count()
        for intent in session.query(ExecutionIntent).filter(ExecutionIntent.status == ExecutionIntentStatus.APPROVED).all():
            execute_intent.delay(intent.id)
        observe_counter("worker.dispatch_intents.completed")
        return {"queued": ready}
    except Exception:
        observe_counter("worker.dispatch_intents.failures")
        raise
    finally:
        observe_duration_ms("worker.dispatch_intents.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()
