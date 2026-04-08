from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator, require_roles
from tradingbot.enums import OperatorRole
from tradingbot.schemas.settings import BotSettingsResponse, BotSettingsUpdate
from tradingbot.services.store import apply_settings_update, ensure_bot_settings, serialize_settings

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=BotSettingsResponse)
def get_settings_endpoint(
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    return serialize_settings(session, ensure_bot_settings(session))


@router.put("/settings", response_model=BotSettingsResponse)
def update_settings_endpoint(
    payload: BotSettingsUpdate,
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    updated = apply_settings_update(
        session,
        payload,
        actor=current.email,
        actor_role=current.role.value,
        session_id=current.session_id,
    )
    return serialize_settings(session, updated)
