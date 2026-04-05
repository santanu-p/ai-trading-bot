from __future__ import annotations

from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class BotStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OrderIntent(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRole(str, Enum):
    MARKET = "market"
    NEWS = "news"
    RISK = "risk"
    COMMITTEE = "committee"


class TradingPattern(str, Enum):
    SCALPING = "scalping"
    INTRADAY = "intraday"
    DELIVERY = "delivery"
    SWING = "swing"
    POSITIONAL = "positional"
    BTST_STBT = "btst_stbt"
    FUTURES_DIRECTIONAL = "futures_directional"
    FUTURES_HEDGED = "futures_hedged"
    OPTIONS_BUYING = "options_buying"
    OPTIONS_SELLING = "options_selling"


class InstrumentClass(str, Enum):
    CASH_EQUITY = "cash_equity"
    FUTURES = "futures"
    OPTIONS = "options"
    MIXED = "mixed"


class StrategyFamily(str, Enum):
    MOMENTUM_BREAKOUT = "momentum_breakout"
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    EVENT_DRIVEN = "event_driven"
    PRICE_ACTION = "price_action"
    OPTION_PREMIUM_DECAY = "option_premium_decay"
    HEDGED_CARRY = "hedged_carry"
    MULTI_FACTOR = "multi_factor"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class MarketUniverse(str, Enum):
    LARGE_CAP = "large_cap"
    LARGE_MID_CAP = "large_mid_cap"
    INDEX_ONLY = "index_only"
    SECTOR_FOCUS = "sector_focus"
    CUSTOM_WATCHLIST = "custom_watchlist"
