from tradingbot.enums import InstrumentClass, MarketUniverse, RiskProfile, StrategyFamily, TradingPattern
from tradingbot.models import BotSettings
from tradingbot.services.store import execution_block_reason, execution_support_status, strategy_profile_completed


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
        trading_pattern=TradingPattern.INTRADAY,
        instrument_class=InstrumentClass.CASH_EQUITY,
        strategy_family=StrategyFamily.MOMENTUM_BREAKOUT,
        risk_profile=RiskProfile.BALANCED,
        market_universe=MarketUniverse.CUSTOM_WATCHLIST,
    )
    assert execution_support_status(settings) == "broker_execution_supported"
    assert execution_block_reason(settings) is None


def test_execution_support_for_options_pattern_is_analysis_only() -> None:
    settings = BotSettings(
        trading_pattern=TradingPattern.OPTIONS_BUYING,
        instrument_class=InstrumentClass.OPTIONS,
        strategy_family=StrategyFamily.EVENT_DRIVEN,
        risk_profile=RiskProfile.AGGRESSIVE,
        market_universe=MarketUniverse.INDEX_ONLY,
    )
    assert execution_support_status(settings) == "analysis_only_for_selected_instrument"
    assert execution_block_reason(settings) is not None

