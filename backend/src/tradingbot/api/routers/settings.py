from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tradingbot.api.dependencies import CurrentActor, db_session_dependency, get_current_operator, require_roles
from tradingbot.enums import OperatorRole
from tradingbot.schemas.settings import BotSettingsResponse, BotSettingsUpdate, MarketProfileSummaryResponse
from tradingbot.services.store import (
    apply_settings_update,
    ensure_bot_settings,
    list_market_profiles,
    serialize_market_profile_summary,
    serialize_settings,
)

router = APIRouter(tags=["settings"])


@router.get("/profiles", response_model=list[MarketProfileSummaryResponse])
def list_profiles_endpoint(
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> list[MarketProfileSummaryResponse]:
    return [serialize_market_profile_summary(item) for item in list_market_profiles(session)]


@router.get("/settings", response_model=BotSettingsResponse)
def get_settings_endpoint(
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    return serialize_settings(session, ensure_bot_settings(session))


@router.get("/profiles/{profile_id}/settings", response_model=BotSettingsResponse)
def get_profile_settings_endpoint(
    profile_id: int,
    _: CurrentActor = Depends(get_current_operator),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    return serialize_settings(session, ensure_bot_settings(session, profile_id=profile_id))


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


@router.put("/profiles/{profile_id}/settings", response_model=BotSettingsResponse)
def update_profile_settings_endpoint(
    profile_id: int,
    payload: BotSettingsUpdate,
    current: CurrentActor = Depends(require_roles(OperatorRole.ADMIN)),
    session: Session = Depends(db_session_dependency),
) -> BotSettingsResponse:
    updated = apply_settings_update(
        session,
        payload,
        profile_id=profile_id,
        actor=current.email,
        actor_role=current.role.value,
        session_id=current.session_id,
    )
    return serialize_settings(session, updated)
