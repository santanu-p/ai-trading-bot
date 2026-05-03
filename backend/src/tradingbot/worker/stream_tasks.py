"""Celery tasks for managing broker stream supervisors.

Provides lifecycle management (start/stop/health-check) for the
WebSocket stream supervisors via the Celery task queue.
"""

from __future__ import annotations

from time import perf_counter

from tradingbot.db import get_session_factory
from tradingbot.enums import TradingMode
from tradingbot.services.metrics import observe_counter, observe_duration_ms
from tradingbot.services.store import ensure_bot_settings
from tradingbot.services.stream_supervisor import (
    StreamConfig,
    all_supervisor_statuses,
    start_supervisor,
    stop_supervisor,
    supervisor_status,
)
from tradingbot.worker.celery_app import celery_app


@celery_app.task(name="tradingbot.worker.stream_tasks.start_stream")
def start_stream(profile_id: int | None = None) -> dict:
    """Start a stream supervisor for the given profile."""
    started = perf_counter()
    observe_counter("worker.stream.start_invocations")
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session, profile_id=profile_id)
        mode = settings_row.mode or TradingMode.PAPER
        config = StreamConfig(profile_id=settings_row.id)
        status = start_supervisor(profile_id=settings_row.id, mode=mode, config=config)
        observe_counter("worker.stream.start_completed")
        return {"profile_id": settings_row.id, "mode": mode.value, "status": status.to_payload()}
    except Exception:
        observe_counter("worker.stream.start_failures")
        session.rollback()
        raise
    finally:
        observe_duration_ms("worker.stream.start_latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()


@celery_app.task(name="tradingbot.worker.stream_tasks.stop_stream")
def stop_stream(profile_id: int | None = None) -> dict:
    """Stop a running stream supervisor."""
    started = perf_counter()
    observe_counter("worker.stream.stop_invocations")
    try:
        status = stop_supervisor(profile_id=profile_id)
        observe_counter("worker.stream.stop_completed")
        return {
            "profile_id": profile_id,
            "status": status.to_payload() if status else "not_found",
        }
    except Exception:
        observe_counter("worker.stream.stop_failures")
        raise
    finally:
        observe_duration_ms("worker.stream.stop_latency_ms", duration_ms=(perf_counter() - started) * 1000)


@celery_app.task(name="tradingbot.worker.stream_tasks.check_stream_health")
def check_stream_health() -> dict:
    """Check health of all stream supervisors and restart dead ones."""
    started = perf_counter()
    observe_counter("worker.stream.health_check_invocations")
    session = get_session_factory()()
    try:
        statuses = all_supervisor_statuses()
        restarts = 0

        # Check all enabled profiles for supervisors that should be running
        from tradingbot.services.store import list_enabled_profiles

        for profile in list_enabled_profiles(session):
            status = supervisor_status(profile_id=profile.id)
            if status is None or (status.stopped_at is not None and status.started_at is not None):
                # Supervisor is dead — restart if profile is enabled and not in kill-switch mode
                if profile.enabled and not profile.kill_switch_enabled:
                    start_supervisor(
                        profile_id=profile.id,
                        mode=profile.mode or TradingMode.PAPER,
                        config=StreamConfig(profile_id=profile.id),
                    )
                    restarts += 1
                    observe_counter("worker.stream.auto_restart", tags={"profile_id": str(profile.id)})

        observe_counter("worker.stream.health_check_completed")
        return {
            "supervisors": statuses,
            "restarts": restarts,
        }
    except Exception:
        observe_counter("worker.stream.health_check_failures")
        session.rollback()
        raise
    finally:
        observe_duration_ms("worker.stream.health_check_latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()
