from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import db_session_dependency
from tradingbot.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


def _redis_ready() -> bool:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        return bool(client.ping())
    except RedisError:
        return False
    finally:
        client.close()


@router.get("/health/ready")
def ready(db: Session = Depends(db_session_dependency)) -> dict[str, object]:
    checks = {"database": "ok", "redis": "ok"}
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        checks["database"] = "failed"

    if not _redis_ready():
        checks["redis"] = "failed"

    if checks["database"] == "ok" and checks["redis"] == "ok":
        return {"status": "ok", "checks": checks}
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"status": "degraded", "checks": checks},
    )
