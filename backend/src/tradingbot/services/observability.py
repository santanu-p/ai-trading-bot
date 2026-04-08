from __future__ import annotations

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
_logging_configured = False


def get_request_id() -> str | None:
    return _request_id_var.get()


def get_run_id() -> str | None:
    return _run_id_var.get()


@contextmanager
def bind_request_id(request_id: str | None) -> Generator[None, None, None]:
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


@contextmanager
def bind_run_id(run_id: str | None) -> Generator[None, None, None]:
    token = _run_id_var.set(run_id)
    try:
        yield
    finally:
        _run_id_var.reset(token)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        run_id = get_run_id()
        if request_id:
            payload["request_id"] = request_id
        if run_id:
            payload["run_id"] = run_id

        for attr in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "symbol",
            "code",
            "provider",
            "service",
        ):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_structured_logging(level: int = logging.INFO) -> None:
    global _logging_configured
    if _logging_configured:
        return

    formatter = JsonLogFormatter()
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)

    _logging_configured = True
