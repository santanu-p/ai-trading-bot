from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.config import get_settings
from tradingbot.models import AuditLog, BotSettings, WatchlistSymbol
from tradingbot.schemas.settings import BotSettingsResponse, BotSettingsUpdate, TradingProfile


def ensure_bot_settings(session: Session) -> BotSettings:
    settings_row = session.get(BotSettings, 1)
    if settings_row is not None:
        return settings_row

    defaults = get_settings()
    settings_row = BotSettings(
        id=1,
        scan_interval_minutes=defaults.scan_interval_minutes,
        consensus_threshold=defaults.consensus_threshold,
        openai_model=defaults.openai_model,
    )
    session.add(settings_row)
    session.commit()
    session.refresh(settings_row)
    return settings_row


def replace_watchlist(session: Session, symbols: list[str]) -> list[WatchlistSymbol]:
    existing = session.scalars(select(WatchlistSymbol)).all()
    for item in existing:
        session.delete(item)
    normalized = sorted({symbol.upper().strip() for symbol in symbols if symbol.strip()})
    rows = [WatchlistSymbol(symbol=symbol, enabled=True) for symbol in normalized]
    session.add_all(rows)
    return rows


def serialize_trading_profile(settings_row: BotSettings) -> TradingProfile:
    return TradingProfile(
        trading_pattern=settings_row.trading_pattern,
        instrument_class=settings_row.instrument_class,
        strategy_family=settings_row.strategy_family,
        risk_profile=settings_row.risk_profile,
        market_universe=settings_row.market_universe,
        profile_notes=settings_row.profile_notes or "",
    )


def strategy_profile_completed(settings_row: BotSettings) -> bool:
    return all(
        [
            settings_row.trading_pattern,
            settings_row.instrument_class,
            settings_row.strategy_family,
            settings_row.risk_profile,
            settings_row.market_universe,
        ]
    )


def execution_support_status(settings_row: BotSettings) -> str:
    if not strategy_profile_completed(settings_row):
        return "complete_agent_intake_first"
    if settings_row.instrument_class.value != "cash_equity":
        return "analysis_only_for_selected_instrument"
    if settings_row.trading_pattern.value in {
        "futures_directional",
        "futures_hedged",
        "options_buying",
        "options_selling",
    }:
        return "analysis_only_for_selected_pattern"
    return "broker_execution_supported"


def execution_block_reason(settings_row: BotSettings) -> str | None:
    status = execution_support_status(settings_row)
    if status == "complete_agent_intake_first":
        return "Complete the trading pattern intake before the agents can act."
    if status == "analysis_only_for_selected_instrument":
        return "The current Alpaca execution adapter only supports cash-equity execution; selected instruments will run in analysis mode."
    if status == "analysis_only_for_selected_pattern":
        return "The selected trading pattern is captured for agent analysis, but the current executor cannot place those orders yet."
    return None


def serialize_settings(session: Session, settings_row: BotSettings) -> BotSettingsResponse:
    watchlist = session.scalars(
        select(WatchlistSymbol.symbol).where(WatchlistSymbol.enabled.is_(True)).order_by(WatchlistSymbol.symbol)
    ).all()
    return BotSettingsResponse(
        status=settings_row.status,
        mode=settings_row.mode,
        kill_switch_enabled=settings_row.kill_switch_enabled,
        scan_interval_minutes=settings_row.scan_interval_minutes,
        consensus_threshold=settings_row.consensus_threshold,
        max_open_positions=settings_row.max_open_positions,
        max_daily_loss_pct=settings_row.max_daily_loss_pct,
        max_position_risk_pct=settings_row.max_position_risk_pct,
        max_symbol_notional_pct=settings_row.max_symbol_notional_pct,
        symbol_cooldown_minutes=settings_row.symbol_cooldown_minutes,
        openai_model=settings_row.openai_model,
        watchlist=list(watchlist),
        trading_profile=serialize_trading_profile(settings_row),
        strategy_profile_completed=strategy_profile_completed(settings_row),
        execution_support_status=execution_support_status(settings_row),
    )


def apply_settings_update(session: Session, payload: BotSettingsUpdate) -> BotSettings:
    settings_row = ensure_bot_settings(session)
    settings_row.scan_interval_minutes = payload.scan_interval_minutes
    settings_row.consensus_threshold = payload.consensus_threshold
    settings_row.max_open_positions = payload.max_open_positions
    settings_row.max_daily_loss_pct = payload.max_daily_loss_pct
    settings_row.max_position_risk_pct = payload.max_position_risk_pct
    settings_row.max_symbol_notional_pct = payload.max_symbol_notional_pct
    settings_row.symbol_cooldown_minutes = payload.symbol_cooldown_minutes
    settings_row.openai_model = payload.openai_model
    settings_row.trading_pattern = payload.trading_profile.trading_pattern
    settings_row.instrument_class = payload.trading_profile.instrument_class
    settings_row.strategy_family = payload.trading_profile.strategy_family
    settings_row.risk_profile = payload.trading_profile.risk_profile
    settings_row.market_universe = payload.trading_profile.market_universe
    settings_row.profile_notes = payload.trading_profile.profile_notes.strip()
    replace_watchlist(session, payload.watchlist)
    session.add(
        AuditLog(
            action="settings.updated",
            actor="admin",
            details={
                "watchlist_size": len(payload.watchlist),
                "openai_model": payload.openai_model,
                "trading_pattern": payload.trading_profile.trading_pattern.value if payload.trading_profile.trading_pattern else None,
                "instrument_class": payload.trading_profile.instrument_class.value if payload.trading_profile.instrument_class else None,
            },
        )
    )
    session.commit()
    session.refresh(settings_row)
    return settings_row
