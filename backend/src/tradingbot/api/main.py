from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import Response

from tradingbot.api.routers import auth, backtests, health, performance, settings, trading
from tradingbot.config import get_settings, validate_runtime_settings
from tradingbot.security import create_csrf_token, decode_signed_session, verify_csrf_token
from tradingbot.services.http_controls import rate_limiter
from tradingbot.services.metrics import observe_counter, observe_duration_ms
from tradingbot.services.observability import bind_request_id, configure_structured_logging


logger = logging.getLogger(__name__)
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = {"/auth/login"}
_CSRF_REFRESH_EXEMPT_PATHS = {"/auth/logout"}


def _normalize_path(path: str) -> str:
    parts = [item for item in path.split("/") if item.strip()]
    normalized: list[str] = []
    for part in parts[:4]:
        if part.isdigit() or ("-" in part and len(part) >= 16):
            normalized.append("*")
        else:
            normalized.append(part)
    return "/" if not normalized else "/" + "/".join(normalized)


def _origin_allowed(request: Request, expected_origin: str) -> bool:
    normalized_expected = expected_origin.rstrip("/")
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") == normalized_expected

    referer = request.headers.get("referer")
    if not referer:
        return True

    parsed = urlsplit(referer)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/") == normalized_expected


def _client_key(request: Request, session_payload: dict[str, object] | None) -> str:
    if session_payload is not None:
        session_id = session_payload.get("sid")
        subject = session_payload.get("sub")
        if isinstance(session_id, str) and session_id:
            return f"session:{session_id}"
        if isinstance(subject, str) and subject:
            return f"user:{subject}"
    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    return "anonymous"


def _request_too_large(request: Request, *, limit_bytes: int) -> bool:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return False
    try:
        return int(content_length) > limit_bytes
    except ValueError:
        return False


async def _enforce_request_size_limit(request: Request, *, limit_bytes: int) -> Request | JSONResponse:
    if _request_too_large(request, limit_bytes=limit_bytes):
        return JSONResponse(status_code=413, content={"detail": "Request body exceeds the configured limit."})

    body = await request.body()
    if len(body) > limit_bytes:
        return JSONResponse(status_code=413, content={"detail": "Request body exceeds the configured limit."})

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)


def _session_expiry(session_payload: dict[str, object] | None) -> datetime | None:
    if session_payload is None:
        return None
    exp = session_payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return datetime.fromtimestamp(float(exp), tz=UTC)


def create_app() -> FastAPI:
    settings_config = get_settings()
    validate_runtime_settings(settings_config, service_name="api")
    configure_structured_logging()
    app = FastAPI(title=settings_config.app_name, version="0.1.0")

    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        path = request.url.path
        session_cookie = request.cookies.get(settings_config.session_cookie_name)
        session_payload = decode_signed_session(session_cookie) if session_cookie else None
        session_id = session_payload.get("sid") if isinstance(session_payload, dict) else None

        if request.method not in _SAFE_METHODS:
            size_checked_request = await _enforce_request_size_limit(
                request,
                limit_bytes=settings_config.request_body_max_bytes,
            )
            if isinstance(size_checked_request, JSONResponse):
                size_checked_request.headers["x-request-id"] = request_id
                return size_checked_request
            request = size_checked_request

        limit_result = None
        if path != "/stream/operations" and not path.startswith("/health"):
            request_limit = settings_config.auth_rate_limit_per_minute if path == "/auth/login" else settings_config.api_rate_limit_per_minute
            limit_result = rate_limiter().consume(
                f"{request.method}:{_normalize_path(path)}:{_client_key(request, session_payload)}",
                limit=request_limit,
                window_seconds=settings_config.rate_limit_window_seconds,
            )
            if not limit_result.allowed:
                error_response = JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Retry later."})
                error_response.headers["Retry-After"] = str(limit_result.retry_after_seconds)
                error_response.headers["x-request-id"] = request_id
                error_response.headers["x-rate-limit-remaining"] = "0"
                return error_response

        if (
            request.method not in _SAFE_METHODS
            and path not in _CSRF_EXEMPT_PATHS
            and isinstance(session_id, str)
            and session_id
        ):
            if settings_config.csrf_origin_enforcement and not _origin_allowed(request, settings_config.web_origin):
                error_response = JSONResponse(status_code=403, content={"detail": "Origin check failed."})
                error_response.headers["x-request-id"] = request_id
                return error_response

            csrf_cookie = request.cookies.get(settings_config.csrf_cookie_name)
            csrf_header = request.headers.get(settings_config.csrf_header_name)
            if (
                not csrf_cookie
                or not csrf_header
                or not hmac.compare_digest(csrf_cookie, csrf_header)
                or not verify_csrf_token(csrf_header, session_id=session_id)
            ):
                error_response = JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})
                error_response.headers["x-request-id"] = request_id
                return error_response

        started = perf_counter()
        with bind_request_id(request_id):
            observe_counter(
                "http.request.total",
                tags={"method": request.method, "path": path},
            )
            logger.info(
                "request.start",
                extra={
                    "method": request.method,
                    "path": path,
                },
            )
            try:
                response: Response = await call_next(request)
            except Exception:
                duration_ms = (perf_counter() - started) * 1000
                observe_duration_ms(
                    "http.request.latency_ms",
                    duration_ms=duration_ms,
                    tags={"method": request.method, "path": path, "status_code": "500"},
                )
                observe_counter(
                    "http.request.error",
                    tags={"method": request.method, "path": path, "status_code": "500"},
                )
                logger.exception(
                    "request.error",
                    extra={
                        "method": request.method,
                        "path": path,
                        "status_code": 500,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                raise

            duration_ms = (perf_counter() - started) * 1000
            response.headers["x-request-id"] = request_id
            if limit_result is not None:
                response.headers["x-rate-limit-remaining"] = str(limit_result.remaining)
            if (
                isinstance(session_id, str)
                and session_id
                and path not in _CSRF_REFRESH_EXEMPT_PATHS
            ):
                response_csrf_token = response.headers.get(settings_config.csrf_header_name)
                if not response_csrf_token:
                    request_csrf_token = request.cookies.get(settings_config.csrf_cookie_name)
                    if request_csrf_token and verify_csrf_token(request_csrf_token, session_id=session_id):
                        response_csrf_token = request_csrf_token
                    else:
                        expires_at = _session_expiry(session_payload)
                        response_csrf_token = create_csrf_token(session_id, expires_at=expires_at)
                        response.set_cookie(
                            settings_config.csrf_cookie_name,
                            response_csrf_token,
                            expires=expires_at,
                            httponly=False,
                            secure=settings_config.session_cookie_secure,
                            samesite="lax",
                            path="/",
                        )
                response.headers[settings_config.csrf_header_name] = response_csrf_token
            observe_duration_ms(
                "http.request.latency_ms",
                duration_ms=duration_ms,
                tags={
                    "method": request.method,
                    "path": path,
                    "status_code": str(response.status_code),
                },
            )
            logger.info(
                "request.complete",
                extra={
                    "method": request.method,
                    "path": path,
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
