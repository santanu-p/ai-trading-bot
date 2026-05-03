"""Multi-channel alert dispatch with severity-based routing.

Routes alerts to different channels based on severity:
- info     → webhook only
- warning  → webhook + Slack (if configured)
- critical → webhook + Slack + PagerDuty/Opsgenie (if configured)
- page     → all channels + auto-halt trigger

Supports suppression / deduplication to avoid alert fatigue.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tradingbot.config import get_settings
from tradingbot.services.metrics import observe_counter, observe_duration_ms

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert routing configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AlertChannel:
    """A single webhook-based alert destination."""

    name: str
    url: str
    min_severity: str = "info"  # only receive alerts at or above this level
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 5


@dataclass(frozen=True, slots=True)
class AlertRoutingConfig:
    """Describes all available alert channels and routing rules."""

    channels: list[AlertChannel] = field(default_factory=list)
    default_suppression_minutes: int = 30
    escalation_order: tuple[str, ...] = ("info", "warning", "critical", "page", "auto_halt")


SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "critical": 2,
    "page": 3,
    "auto_halt": 4,
}


# ---------------------------------------------------------------------------
# Suppression registry (in-process deduplication)
# ---------------------------------------------------------------------------
_suppression_lock = Lock()
_suppression_registry: dict[str, datetime] = {}


def _is_suppressed(alert_key: str, *, suppression_minutes: int) -> bool:
    """Return True if this alert_key was dispatched within the suppression window."""
    now = datetime.now(UTC)
    with _suppression_lock:
        last_sent = _suppression_registry.get(alert_key)
        if last_sent is not None and (now - last_sent) < timedelta(minutes=suppression_minutes):
            return True
        _suppression_registry[alert_key] = now
    return False


def _prune_suppression_registry(*, max_age_minutes: int = 120) -> None:
    """Remove stale entries from the suppression registry."""
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    with _suppression_lock:
        stale_keys = [k for k, v in _suppression_registry.items() if v < cutoff]
        for key in stale_keys:
            del _suppression_registry[key]


# ---------------------------------------------------------------------------
# Channel builders
# ---------------------------------------------------------------------------
def build_routing_config() -> AlertRoutingConfig:
    """Build routing configuration from environment settings."""
    settings = get_settings()
    channels: list[AlertChannel] = []

    # Standard webhooks (existing behavior)
    for url in (settings.alert_webhook_urls or []):
        channels.append(AlertChannel(name="webhook", url=url, min_severity="info"))

    # Slack webhook (optional)
    slack_url = getattr(settings, "slack_webhook_url", None) or ""
    if slack_url:
        channels.append(AlertChannel(name="slack", url=slack_url, min_severity="warning"))

    # PagerDuty Events API v2 (optional)
    pagerduty_url = getattr(settings, "pagerduty_webhook_url", None) or ""
    if pagerduty_url:
        channels.append(AlertChannel(name="pagerduty", url=pagerduty_url, min_severity="critical"))

    # Opsgenie (optional)
    opsgenie_url = getattr(settings, "opsgenie_webhook_url", None) or ""
    if opsgenie_url:
        channels.append(AlertChannel(name="opsgenie", url=opsgenie_url, min_severity="critical"))

    return AlertRoutingConfig(channels=channels)


# ---------------------------------------------------------------------------
# Payload formatters
# ---------------------------------------------------------------------------
def _format_slack_payload(payload: dict[str, object]) -> bytes:
    """Format alert payload for Slack Incoming Webhook."""
    severity = str(payload.get("severity", "info"))
    code = str(payload.get("code", "unknown"))
    message = str(payload.get("message", ""))
    emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴", "page": "🚨", "auto_halt": "🛑"}.get(severity, "📢")
    text = f"{emoji} *[{severity.upper()}]* `{code}`\n{message}"
    return json.dumps({"text": text}, default=str).encode("utf-8")


def _format_pagerduty_payload(payload: dict[str, object]) -> bytes:
    """Format alert payload for PagerDuty Events API v2."""
    severity_map = {"info": "info", "warning": "warning", "critical": "critical", "page": "critical", "auto_halt": "critical"}
    return json.dumps(
        {
            "routing_key": str(payload.get("routing_key", "")),
            "event_action": "trigger",
            "payload": {
                "summary": str(payload.get("message", "")),
                "source": "tradingbot",
                "severity": severity_map.get(str(payload.get("severity", "warning")), "warning"),
                "custom_details": payload,
            },
        },
        default=str,
    ).encode("utf-8")


def _format_default_payload(payload: dict[str, object]) -> bytes:
    """Format alert payload as a standard JSON webhook."""
    return json.dumps(payload, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Dispatch engine
# ---------------------------------------------------------------------------
def dispatch_alert_webhooks(
    payload: dict[str, object],
    *,
    suppression_minutes: int | None = None,
) -> int:
    """Dispatch an alert to all configured channels matching the severity.

    Returns the number of channels successfully delivered to.
    """
    config = build_routing_config()
    severity = str(payload.get("severity", "info"))
    severity_rank = SEVERITY_RANK.get(severity, 0)
    code = str(payload.get("code", "unknown"))

    # Suppression / deduplication
    suppression_window = suppression_minutes or config.default_suppression_minutes
    alert_key = f"{code}:{severity}"
    if _is_suppressed(alert_key, suppression_minutes=suppression_window):
        observe_counter("alerts.webhook.suppressed", tags={"code": code, "severity": severity})
        return 0

    # Periodically prune old suppression entries
    _prune_suppression_registry()

    # Enrich payload
    enriched = {
        **payload,
        "environment": get_settings().environment,
        "dispatched_at": datetime.now(UTC).isoformat(),
    }

    delivered = 0
    for channel in config.channels:
        channel_min_rank = SEVERITY_RANK.get(channel.min_severity, 0)
        if severity_rank < channel_min_rank:
            continue

        started = perf_counter()
        try:
            if channel.name == "slack":
                body = _format_slack_payload(enriched)
            elif channel.name == "pagerduty":
                body = _format_pagerduty_payload(enriched)
            else:
                body = _format_default_payload(enriched)

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                **channel.headers,
            }
            request = Request(channel.url, data=body, method="POST", headers=headers)
            with urlopen(request, timeout=channel.timeout_seconds):
                observe_counter("alerts.webhook.delivered", tags={"channel": channel.name, "severity": severity})
                delivered += 1
        except (HTTPError, URLError, OSError) as exc:
            observe_counter("alerts.webhook.failed", tags={"channel": channel.name, "severity": severity})
            logger.warning(
                "alert.dispatch_failed",
                extra={"channel": channel.name, "code": code, "severity": severity, "service": "alert_dispatch"},
                exc_info=exc,
            )
        finally:
            observe_duration_ms(
                "alerts.webhook.latency_ms",
                duration_ms=(perf_counter() - started) * 1000,
                tags={"channel": channel.name},
            )

    return delivered
