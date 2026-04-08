from __future__ import annotations

from celery import Celery

from tradingbot.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tradingbot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "tradingbot.worker.tasks",
        "tradingbot.worker.execution_tasks",
        "tradingbot.worker.replay_tasks",
    ],
)
celery_app.conf.timezone = settings.market_timezone
celery_app.conf.beat_schedule = {
    "market-scan-every-five-minutes": {
        "task": "tradingbot.worker.tasks.run_market_scan",
        "schedule": settings.scan_interval_minutes * 60,
    },
    "reconciliation-every-five-minutes": {
        "task": "tradingbot.worker.tasks.run_reconciliation",
        "schedule": settings.scan_interval_minutes * 60,
    },
    "dispatch-approved-intents-every-minute": {
        "task": "tradingbot.worker.execution_tasks.dispatch_ready_intents",
        "schedule": 60,
    },
}

