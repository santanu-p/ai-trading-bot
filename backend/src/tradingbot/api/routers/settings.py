from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import db_session_dependency, get_current_operator
from tradingbot.schemas.settings import BotSettingsResponse, BotSettingsUpdate
from tradingbot.services.store import apply_settings_update, ensure_bot_settings, serialize_settings

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=BotSettingsResponse)
def get_settings_endpoint(
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    return serialize_settings(session, ensure_bot_settings(session))


@router.put("/settings", response_model=BotSettingsResponse)
def update_settings_endpoint(
    payload: BotSettingsUpdate,
    _: str = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    updated = apply_settings_update(session, payload)
    return serialize_settings(session, updated)

