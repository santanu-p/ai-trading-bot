from __future__ import annotations

import json
import logging
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tradingbot.config import get_settings
from tradingbot.services.metrics import observe_counter, observe_duration_ms


logger = logging.getLogger(__name__)


def dispatch_alert_webhooks(payload: dict[str, object]) -> None:
    settings = get_settings()
    if not settings.alert_webhook_urls:
        return

    body = json.dumps(payload, default=str).encode("utf-8")
    for url in settings.alert_webhook_urls:
        started = perf_counter()
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=settings.alert_webhook_timeout_seconds):
                observe_counter("alerts.webhook.delivered", tags={"target": url})
        except (HTTPError, URLError, OSError) as exc:
            observe_counter("alerts.webhook.failed", tags={"target": url})
            logger.warning(
                "alert.webhook_failed",
                extra={"code": payload.get("code"), "service": "alert_webhook"},
                exc_info=exc,
            )
        finally:
            observe_duration_ms(
                "alerts.webhook.latency_ms",
                duration_ms=(perf_counter() - started) * 1000,
                tags={"target": url},
            )
