"""Public Prometheus metrics endpoint and detailed health checks.

The ``/metrics`` endpoint is intentionally unauthenticated so that
Prometheus, Datadog Agent, or Grafana Cloud can scrape it directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter, Response

from tradingbot.config import get_settings
from tradingbot.db import get_session_factory
from tradingbot.services.metrics import prometheus_export
from tradingbot.services.otel import recent_spans

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
def prometheus_scrape() -> Response:
    """Prometheus-compatible metrics endpoint (public, no auth)."""
    body = prometheus_export(window_minutes=60)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health/detailed")
def health_detailed() -> dict:
    """Component-level health status for monitoring dashboards."""
    started = perf_counter()
    settings = get_settings()
    checks: dict[str, dict] = {}

    # Database connectivity
    try:
        session = get_session_factory()()
        try:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["database"] = {"status": "healthy", "backend": "postgresql"}
        except Exception as exc:
            checks["database"] = {"status": "unhealthy", "error": str(exc)}
        finally:
            session.close()
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": str(exc)}

    # Redis connectivity
    try:
        import redis as _redis_module

        client = _redis_module.from_url(settings.redis_url, socket_timeout=3)
        client.ping()
        checks["redis"] = {"status": "healthy", "url": settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url}
        client.close()
    except Exception as exc:
        checks["redis"] = {"status": "degraded", "error": str(exc), "note": "Redis check failed; worker tasks may be unavailable."}

    # LLM provider availability
    llm_provider = "none"
    if settings.openai_api_key:
        llm_provider = "openai"
    elif settings.gemini_api_key:
        llm_provider = "gemini"
    checks["llm"] = {"status": "healthy" if llm_provider != "none" else "degraded", "provider": llm_provider}

    # Broker credentials
    broker_configured = bool(settings.alpaca_api_key or settings.alpaca_paper_api_key)
    checks["broker"] = {
        "status": "healthy" if broker_configured else "degraded",
        "provider": "alpaca" if broker_configured else "none",
    }

    # Recent trace spans summary
    spans = recent_spans(limit=50)
    error_spans = [s for s in spans if s.status == "error"]
    checks["tracing"] = {
        "status": "healthy",
        "recent_spans": len(spans),
        "recent_errors": len(error_spans),
    }

    overall_status = "healthy"
    if any(c.get("status") == "unhealthy" for c in checks.values()):
        overall_status = "unhealthy"
    elif any(c.get("status") == "degraded" for c in checks.values()):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "components": checks,
    }
