from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.config import get_settings
from tradingbot.enums import BrokerSlug, MarketRegion
from tradingbot.models import AuditLog, BotSettings, WatchlistSymbol
from tradingbot.schemas.settings import (
    BotSettingsResponse,
    BotSettingsUpdate,
    BrokerCapability,
    BrokerSettings,
    MarketProfileSummaryResponse,
    MarketSessionResponse,
    TradingProfile,
)
from tradingbot.services.broker_capabilities import (
    ExecutionSupportSummary,
    get_broker_definition,
    normalize_permissions,
    resolve_execution_support as resolve_profile_execution_support,
)
from tradingbot.services.calendar import MarketCalendarService

DEFAULT_US_PROFILE_KEY = "us-alpaca"
DEFAULT_INDIA_PROFILE_KEY = "india-paper"

def _normalize_string_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted({item.strip().upper() for item in values if item and item.strip()})


def _seed_profile(
    *,
    defaults,
    profile_key: str,
    display_name: str,
    market_region: MarketRegion,
    broker_slug: BrokerSlug,
    execution_provider_kind: str,
    data_provider_kind: str,
    enabled_exchanges: list[str],
    benchmark_symbols: list[str],
    news_optional: bool,
    is_default: bool,
) -> BotSettings:
    broker_definition = get_broker_definition(broker_slug)
    return BotSettings(
        profile_key=profile_key,
        display_name=display_name,
        market_region=market_region,
        execution_provider_kind=execution_provider_kind,
        data_provider_kind=data_provider_kind,
        enabled=True,
        is_default=is_default,
        enabled_exchanges=enabled_exchanges,
        benchmark_symbols=benchmark_symbols,
        news_optional=news_optional,
        scan_interval_minutes=defaults.scan_interval_minutes,
        consensus_threshold=defaults.consensus_threshold,
        openai_model=defaults.openai_model,
        broker_slug=broker_definition.slug,
        broker_account_type=broker_definition.default_account_type,
        broker_venue=broker_definition.default_venue,
        broker_timezone=broker_definition.default_timezone,
        broker_base_currency=broker_definition.default_base_currency,
        broker_permissions=list(broker_definition.default_permissions),
    )


def ensure_market_profiles(session: Session) -> list[BotSettings]:
    rows = list(session.scalars(select(BotSettings).order_by(BotSettings.id.asc())).all())
    defaults = get_settings()
    if not rows:
        session.add_all(
            [
                _seed_profile(
                    defaults=defaults,
                    profile_key=DEFAULT_US_PROFILE_KEY,
                    display_name="US Alpaca",
                    market_region=MarketRegion.US,
                    broker_slug=BrokerSlug.ALPACA,
                    execution_provider_kind="alpaca",
                    data_provider_kind="alpaca",
                    enabled_exchanges=["NASDAQ", "NYSE", "ARCA"],
                    benchmark_symbols=["SPY", "QQQ"],
                    news_optional=False,
                    is_default=True,
                ),
                _seed_profile(
                    defaults=defaults,
                    profile_key=DEFAULT_INDIA_PROFILE_KEY,
                    display_name="India Paper",
                    market_region=MarketRegion.IN,
                    broker_slug=BrokerSlug.INTERNAL_PAPER,
                    execution_provider_kind="internal_paper",
                    data_provider_kind="imported_files",
                    enabled_exchanges=["NSE", "BSE", "MCX"],
                    benchmark_symbols=["NIFTY 50", "BANKNIFTY", "SENSEX"],
                    news_optional=True,
                    is_default=False,
                ),
            ]
        )
        session.commit()
        return list(session.scalars(select(BotSettings).order_by(BotSettings.id.asc())).all())

    changed = False
    by_key = {row.profile_key: row for row in rows if row.profile_key}
    us_profile = by_key.get(DEFAULT_US_PROFILE_KEY)
    if us_profile is None:
        us_profile = rows[0]
        us_profile.profile_key = DEFAULT_US_PROFILE_KEY
        us_profile.display_name = us_profile.display_name or "US Alpaca"
        us_profile.market_region = us_profile.market_region or MarketRegion.US
        us_profile.execution_provider_kind = us_profile.execution_provider_kind or "alpaca"
        us_profile.data_provider_kind = us_profile.data_provider_kind or "alpaca"
        us_profile.enabled = True if us_profile.enabled is None else us_profile.enabled
        us_profile.is_default = True
        us_profile.enabled_exchanges = _normalize_string_list(us_profile.enabled_exchanges or ["NASDAQ", "NYSE", "ARCA"])
        us_profile.benchmark_symbols = _normalize_string_list(us_profile.benchmark_symbols or ["SPY", "QQQ"])
        us_profile.news_optional = False if us_profile.news_optional is None else us_profile.news_optional
        changed = True

    if DEFAULT_INDIA_PROFILE_KEY not in by_key:
        session.add(
            _seed_profile(
                defaults=defaults,
                profile_key=DEFAULT_INDIA_PROFILE_KEY,
                display_name="India Paper",
                market_region=MarketRegion.IN,
                broker_slug=BrokerSlug.INTERNAL_PAPER,
                execution_provider_kind="internal_paper",
                data_provider_kind="imported_files",
                enabled_exchanges=["NSE", "BSE", "MCX"],
                benchmark_symbols=["NIFTY 50", "BANKNIFTY", "SENSEX"],
                news_optional=True,
                is_default=False,
            )
        )
        changed = True

    if not any(row.is_default for row in rows):
        us_profile.is_default = True
        changed = True

    if changed:
        session.commit()
        rows = list(session.scalars(select(BotSettings).order_by(BotSettings.id.asc())).all())
    return rows


def ensure_bot_settings(
    session: Session,
    *,
    profile_id: int | None = None,
    profile_key: str | None = None,
) -> BotSettings:
    ensure_market_profiles(session)
    query = select(BotSettings)
    if profile_id is not None:
        query = query.where(BotSettings.id == profile_id)
    elif profile_key is not None:
        query = query.where(BotSettings.profile_key == profile_key)
    else:
        query = query.where(BotSettings.is_default.is_(True))
    settings_row = session.scalar(query.limit(1))
    if settings_row is None:
        raise ValueError("Requested market profile was not found.")
    return settings_row


def list_market_profiles(session: Session) -> list[BotSettings]:
    ensure_market_profiles(session)
    return list(session.scalars(select(BotSettings).order_by(BotSettings.id.asc())).all())


def list_enabled_profiles(session: Session) -> list[BotSettings]:
    ensure_market_profiles(session)
    return list(
        session.scalars(
        select(BotSettings).where(BotSettings.enabled.is_(True)).order_by(BotSettings.id.asc())
        ).all()
    )


def replace_watchlist(session: Session, settings_row: BotSettings, symbols: list[str]) -> list[WatchlistSymbol]:
    existing = session.scalars(select(WatchlistSymbol).where(WatchlistSymbol.profile_id == settings_row.id)).all()
    for item in existing:
        session.delete(item)
    normalized = _normalize_string_list(symbols)
    rows = [WatchlistSymbol(profile_id=settings_row.id, symbol=symbol, enabled=True) for symbol in normalized]
    session.add_all(rows)
    return rows


def serialize_selected_for_analysis(settings_row: BotSettings) -> TradingProfile:
    return TradingProfile(
        trading_pattern=settings_row.trading_pattern,
        instrument_class=settings_row.instrument_class,
        strategy_family=settings_row.strategy_family,
        risk_profile=settings_row.risk_profile,
        market_universe=settings_row.market_universe,
        profile_notes=settings_row.profile_notes or "",
    )


def serialize_trading_profile(settings_row: BotSettings) -> TradingProfile:
    return serialize_selected_for_analysis(settings_row)


def serialize_broker_settings(settings_row: BotSettings) -> BrokerSettings:
    broker_definition = get_broker_definition(settings_row.broker_slug)
    return BrokerSettings(
        broker=settings_row.broker_slug,
        account_type=settings_row.broker_account_type or broker_definition.default_account_type,
        venue=settings_row.broker_venue or broker_definition.default_venue,
        timezone=settings_row.broker_timezone or broker_definition.default_timezone,
        base_currency=settings_row.broker_base_currency or broker_definition.default_base_currency,
        permissions=normalize_permissions(settings_row.broker_permissions, broker_definition),
    )


def serialize_market_profile_summary(settings_row: BotSettings) -> MarketProfileSummaryResponse:
    return MarketProfileSummaryResponse(
        profile_id=settings_row.id,
        profile_key=settings_row.profile_key,
        display_name=settings_row.display_name,
        market_region=settings_row.market_region,
        execution_provider_kind=settings_row.execution_provider_kind,
        data_provider_kind=settings_row.data_provider_kind,
        enabled=settings_row.enabled,
        is_default=settings_row.is_default,
        mode=settings_row.mode,
        live_enabled=settings_row.live_enabled,
        enabled_exchanges=list(settings_row.enabled_exchanges or []),
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


def resolve_execution_support(settings_row: BotSettings) -> ExecutionSupportSummary:
    broker_definition = get_broker_definition(settings_row.broker_slug)
    return resolve_profile_execution_support(serialize_selected_for_analysis(settings_row), broker_definition)


def live_trading_env_allowed(settings_row: BotSettings) -> bool:
    settings = get_settings()
    if not settings.allow_live_trading:
        return False
    if not settings.live_trading_allowed_brokers:
        return False
    return settings_row.broker_slug.value in settings.live_trading_allowed_brokers


def execution_support_status(settings_row: BotSettings) -> str:
    return resolve_execution_support(settings_row).status


def execution_block_reason(settings_row: BotSettings) -> str | None:
    support = resolve_execution_support(settings_row)
    if support.status == "complete_agent_intake_first":
        return "Complete the trading pattern intake before the agents can act."
    return support.analysis_only_downgrade_reason


def serialize_settings(session: Session, settings_row: BotSettings) -> BotSettingsResponse:
    watchlist = session.scalars(
        select(WatchlistSymbol.symbol)
        .where(WatchlistSymbol.profile_id == settings_row.id)
        .where(WatchlistSymbol.enabled.is_(True))
        .order_by(WatchlistSymbol.symbol)
    ).all()
    broker_definition = get_broker_definition(settings_row.broker_slug)
    support = resolve_execution_support(settings_row)
    session_state = MarketCalendarService.for_settings(settings_row).session_state(
        trading_pattern=settings_row.trading_pattern,
        instrument_class=settings_row.instrument_class,
    )
    live_mode_allowed = support.live_start_allowed and live_trading_env_allowed(settings_row)
    return BotSettingsResponse(
        profile_id=settings_row.id,
        profile_key=settings_row.profile_key,
        display_name=settings_row.display_name,
        market_region=settings_row.market_region,
        execution_provider_kind=settings_row.execution_provider_kind,
        data_provider_kind=settings_row.data_provider_kind,
        enabled=settings_row.enabled,
        is_default=settings_row.is_default,
        enabled_exchanges=list(settings_row.enabled_exchanges or []),
        benchmark_symbols=list(settings_row.benchmark_symbols or []),
        news_optional=settings_row.news_optional,
        status=settings_row.status,
        mode=settings_row.mode,
        kill_switch_enabled=settings_row.kill_switch_enabled,
        live_enabled=settings_row.live_enabled,
        live_trading_env_allowed=live_trading_env_allowed(settings_row),
        scan_interval_minutes=settings_row.scan_interval_minutes,
        consensus_threshold=settings_row.consensus_threshold,
        max_open_positions=settings_row.max_open_positions,
        max_daily_loss_pct=settings_row.max_daily_loss_pct,
        max_position_risk_pct=settings_row.max_position_risk_pct,
        max_symbol_notional_pct=settings_row.max_symbol_notional_pct,
        max_gross_exposure_pct=settings_row.max_gross_exposure_pct,
        max_sector_exposure_pct=settings_row.max_sector_exposure_pct,
        max_correlation_exposure_pct=settings_row.max_correlation_exposure_pct,
        max_event_cluster_positions=settings_row.max_event_cluster_positions,
        volatility_target_pct=settings_row.volatility_target_pct,
        atr_sizing_multiplier=settings_row.atr_sizing_multiplier,
        equity_curve_throttle_start_pct=settings_row.equity_curve_throttle_start_pct,
        equity_curve_throttle_min_scale=settings_row.equity_curve_throttle_min_scale,
        intraday_drawdown_pause_pct=settings_row.intraday_drawdown_pause_pct,
        loss_streak_reduction_threshold=settings_row.loss_streak_reduction_threshold,
        loss_streak_size_scale=settings_row.loss_streak_size_scale,
        execution_failure_review_threshold=settings_row.execution_failure_review_threshold,
        severe_anomaly_kill_switch_threshold=settings_row.severe_anomaly_kill_switch_threshold,
        symbol_cooldown_minutes=settings_row.symbol_cooldown_minutes,
        symbol_cooldown_profit_minutes=settings_row.symbol_cooldown_profit_minutes,
        symbol_cooldown_stopout_minutes=settings_row.symbol_cooldown_stopout_minutes,
        symbol_cooldown_event_minutes=settings_row.symbol_cooldown_event_minutes,
        symbol_cooldown_whipsaw_minutes=settings_row.symbol_cooldown_whipsaw_minutes,
        openai_model=settings_row.openai_model,
        watchlist=list(watchlist),
        broker_settings=serialize_broker_settings(settings_row),
        broker_capability_matrix=[
            BrokerCapability(
                key=item.key,
                label=item.label,
                description=item.description,
                supported=item.supported,
            )
            for item in broker_definition.capabilities
        ],
        selected_for_analysis=support.selected_for_analysis,
        supported_for_execution=support.supported_for_execution,
        strategy_profile_completed=strategy_profile_completed(settings_row),
        execution_support_status=support.status,
        live_start_allowed=live_mode_allowed,
        analysis_only_downgrade_reason=settings_row.analysis_only_downgrade_reason
        or support.analysis_only_downgrade_reason,
        market_session=MarketSessionResponse(
            venue=session_state.venue,
            timezone=session_state.timezone,
            status=session_state.status,
            reason=session_state.reason,
            is_half_day=session_state.is_half_day,
            can_scan=session_state.can_scan,
            can_submit_orders=session_state.can_submit_orders,
            should_flatten_positions=session_state.should_flatten_positions,
            session_opens_at=session_state.session_opens_at,
            session_closes_at=session_state.session_closes_at,
            next_session_opens_at=session_state.next_session_opens_at,
        ),
    )


def apply_settings_update(
    session: Session,
    payload: BotSettingsUpdate,
    *,
    profile_id: int | None = None,
    profile_key: str | None = None,
    actor: str = "admin",
    actor_role: str = "admin",
    session_id: str | None = None,
) -> BotSettings:
    settings_row = ensure_bot_settings(session, profile_id=profile_id, profile_key=profile_key)
    settings_row.display_name = payload.display_name.strip()
    settings_row.enabled = payload.enabled
    settings_row.enabled_exchanges = _normalize_string_list(payload.enabled_exchanges)
    settings_row.benchmark_symbols = _normalize_string_list(payload.benchmark_symbols)
    settings_row.news_optional = payload.news_optional
    settings_row.scan_interval_minutes = payload.scan_interval_minutes
    settings_row.consensus_threshold = payload.consensus_threshold
    settings_row.max_open_positions = payload.max_open_positions
    settings_row.max_daily_loss_pct = payload.max_daily_loss_pct
    settings_row.max_position_risk_pct = payload.max_position_risk_pct
    settings_row.max_symbol_notional_pct = payload.max_symbol_notional_pct
    settings_row.max_gross_exposure_pct = payload.max_gross_exposure_pct
    settings_row.max_sector_exposure_pct = payload.max_sector_exposure_pct
    settings_row.max_correlation_exposure_pct = payload.max_correlation_exposure_pct
    settings_row.max_event_cluster_positions = payload.max_event_cluster_positions
    settings_row.volatility_target_pct = payload.volatility_target_pct
    settings_row.atr_sizing_multiplier = payload.atr_sizing_multiplier
    settings_row.equity_curve_throttle_start_pct = payload.equity_curve_throttle_start_pct
    settings_row.equity_curve_throttle_min_scale = payload.equity_curve_throttle_min_scale
    settings_row.intraday_drawdown_pause_pct = payload.intraday_drawdown_pause_pct
    settings_row.loss_streak_reduction_threshold = payload.loss_streak_reduction_threshold
    settings_row.loss_streak_size_scale = payload.loss_streak_size_scale
    settings_row.execution_failure_review_threshold = payload.execution_failure_review_threshold
    settings_row.severe_anomaly_kill_switch_threshold = payload.severe_anomaly_kill_switch_threshold
    settings_row.symbol_cooldown_minutes = payload.symbol_cooldown_minutes
    settings_row.symbol_cooldown_profit_minutes = payload.symbol_cooldown_profit_minutes
    settings_row.symbol_cooldown_stopout_minutes = payload.symbol_cooldown_stopout_minutes
    settings_row.symbol_cooldown_event_minutes = payload.symbol_cooldown_event_minutes
    settings_row.symbol_cooldown_whipsaw_minutes = payload.symbol_cooldown_whipsaw_minutes
    settings_row.openai_model = payload.openai_model
    broker_definition = get_broker_definition(payload.broker_settings.broker)
    settings_row.broker_slug = payload.broker_settings.broker
    settings_row.broker_account_type = payload.broker_settings.account_type.strip()
    settings_row.broker_venue = payload.broker_settings.venue.strip()
    settings_row.broker_timezone = payload.broker_settings.timezone.strip()
    settings_row.broker_base_currency = payload.broker_settings.base_currency.strip().upper()
    settings_row.broker_permissions = normalize_permissions(payload.broker_settings.permissions, broker_definition)
    settings_row.trading_pattern = payload.selected_for_analysis.trading_pattern
    settings_row.instrument_class = payload.selected_for_analysis.instrument_class
    settings_row.strategy_family = payload.selected_for_analysis.strategy_family
    settings_row.risk_profile = payload.selected_for_analysis.risk_profile
    settings_row.market_universe = payload.selected_for_analysis.market_universe
    settings_row.profile_notes = payload.selected_for_analysis.profile_notes.strip()
    settings_row.analysis_only_downgrade_reason = resolve_execution_support(settings_row).analysis_only_downgrade_reason
    if not live_trading_env_allowed(settings_row) or resolve_execution_support(settings_row).supported_for_execution is None:
        settings_row.live_enabled = False
    settings_row.live_enable_code_hash = None
    settings_row.live_enable_code_expires_at = None
    replace_watchlist(session, settings_row, payload.watchlist)
    session.add(
        AuditLog(
            profile_id=settings_row.id,
            action="settings.updated",
            actor=actor,
            actor_role=actor_role,
            session_id=session_id,
            details={
                "profile_key": settings_row.profile_key,
                "watchlist_size": len(payload.watchlist),
                "openai_model": payload.openai_model,
                "broker": payload.broker_settings.broker.value,
                "trading_pattern": payload.selected_for_analysis.trading_pattern.value
                if payload.selected_for_analysis.trading_pattern
                else None,
                "instrument_class": payload.selected_for_analysis.instrument_class.value
                if payload.selected_for_analysis.instrument_class
                else None,
            },
        )
    )
    session.commit()
    session.refresh(settings_row)
    return settings_row
