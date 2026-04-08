from __future__ import annotations

from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class BrokerSlug(str, Enum):
    ALPACA = "alpaca"


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


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    BRACKET = "bracket"
    OCO = "oco"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(str, Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    PENDING_TRIGGER = "pending_trigger"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRole(str, Enum):
    MARKET = "market"
    NEWS = "news"
    RISK = "risk"
    COMMITTEE = "committee"


class OperatorRole(str, Enum):
    REVIEWER = "reviewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class ExecutionIntentStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELED = "canceled"


class ExecutionIntentType(str, Enum):
    TRADE = "trade"
    FLATTEN_ALL = "flatten_all"
    BROKER_KILL = "broker_kill"


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


class OptionRight(str, Enum):
    CALL = "call"
    PUT = "put"


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
