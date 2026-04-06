from tradingbot.enums import BrokerSlug, InstrumentClass, MarketUniverse, RiskProfile, StrategyFamily, TradingMode, TradingPattern
from tradingbot.models import BotSettings
from tradingbot.services.store import (
    execution_block_reason,
    execution_support_status,
    resolve_execution_support,
    strategy_profile_completed,
)


def test_strategy_profile_completion_requires_all_core_choices() -> None:
    settings = BotSettings()
    assert not strategy_profile_completed(settings)

    settings.trading_pattern = TradingPattern.INTRADAY
    settings.instrument_class = InstrumentClass.CASH_EQUITY
    settings.strategy_family = StrategyFamily.MOMENTUM_BREAKOUT
    settings.risk_profile = RiskProfile.BALANCED
    settings.market_universe = MarketUniverse.CUSTOM_WATCHLIST

    assert strategy_profile_completed(settings)


def test_execution_support_for_cash_equity_intraday() -> None:
    settings = BotSettings(
        broker_slug=BrokerSlug.ALPACA,
        trading_pattern=TradingPattern.INTRADAY,
        instrument_class=InstrumentClass.CASH_EQUITY,
        strategy_family=StrategyFamily.MOMENTUM_BREAKOUT,
        risk_profile=RiskProfile.BALANCED,
        market_universe=MarketUniverse.CUSTOM_WATCHLIST,
    )
    support = resolve_execution_support(settings)
    assert execution_support_status(settings) == "broker_execution_supported"
    assert execution_block_reason(settings) is None
    assert support.supported_for_execution is not None
    assert support.live_start_allowed is True


def test_execution_support_for_delivery_scope_is_analysis_only() -> None:
    settings = BotSettings(
        broker_slug=BrokerSlug.ALPACA,
        trading_pattern=TradingPattern.DELIVERY,
        instrument_class=InstrumentClass.CASH_EQUITY,
        strategy_family=StrategyFamily.PRICE_ACTION,
        risk_profile=RiskProfile.BALANCED,
        market_universe=MarketUniverse.LARGE_CAP,
    )
    support = resolve_execution_support(settings)
    assert execution_support_status(settings) == "analysis_only_for_selected_broker"
    assert support.supported_for_execution is None
    assert execution_block_reason(settings) is not None
    assert "same-session cash-equity workflows" in execution_block_reason(settings)


def test_live_start_is_blocked_for_unsupported_broker_scope() -> None:
    settings = BotSettings(
        broker_slug=BrokerSlug.ALPACA,
        mode=TradingMode.LIVE,
        trading_pattern=TradingPattern.OPTIONS_BUYING,
        instrument_class=InstrumentClass.OPTIONS,
        strategy_family=StrategyFamily.EVENT_DRIVEN,
        risk_profile=RiskProfile.AGGRESSIVE,
        market_universe=MarketUniverse.INDEX_ONLY,
    )
    support = resolve_execution_support(settings)
    assert support.live_start_allowed is False
    assert support.analysis_only_downgrade_reason is not None
