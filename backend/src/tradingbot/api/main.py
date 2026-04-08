from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tradingbot.api.routers import auth, backtests, health, performance, settings, trading
from tradingbot.config import get_settings
from tradingbot.services.metrics import observe_counter, observe_duration_ms
from tradingbot.services.observability import bind_request_id, configure_structured_logging


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings_config = get_settings()
    configure_structured_logging()
    app = FastAPI(title=settings_config.app_name, version="0.1.0")

    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started = perf_counter()
        with bind_request_id(request_id):
            observe_counter(
                "http.request.total",
                tags={"method": request.method, "path": request.url.path},
            )
            logger.info(
                "request.start",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            try:
                response: Response = await call_next(request)
            except Exception:
                duration_ms = (perf_counter() - started) * 1000
                observe_duration_ms(
                    "http.request.latency_ms",
                    duration_ms=duration_ms,
                    tags={"method": request.method, "path": request.url.path, "status_code": "500"},
                )
                observe_counter(
                    "http.request.error",
                    tags={"method": request.method, "path": request.url.path, "status_code": "500"},
                )
                logger.exception(
                    "request.error",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": 500,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                raise

            duration_ms = (perf_counter() - started) * 1000
            response.headers["x-request-id"] = request_id
            observe_duration_ms(
                "http.request.latency_ms",
                duration_ms=duration_ms,
                tags={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": str(response.status_code),
                },
            )
            logger.info(
                "request.complete",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings_config.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(performance.router)
    app.include_router(backtests.router)
    app.include_router(trading.router)
    return app


app = create_app()

