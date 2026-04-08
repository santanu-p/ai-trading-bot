from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import sqrt
from random import Random
from statistics import mean, stdev
from typing import Any

from tradingbot.schemas.settings import TradingProfile
from tradingbot.services.adapters import BarPoint, MarketDataAdapter, NewsAdapter, NewsItem
from tradingbot.services.indicators import bar_summary

POSITIVE_NEWS_TERMS = {"beats", "upgrade", "partnership", "growth", "surge", "record", "expands", "raises"}
NEGATIVE_NEWS_TERMS = {"misses", "downgrade", "lawsuit", "probe", "cuts", "drops", "fraud", "bankruptcy"}


@dataclass(slots=True)
class BacktestSimulationConfig:
    initial_equity: float = 100_000
    slippage_bps: float = 5.0
    commission_per_share: float = 0.005
    fill_delay_bars: int = 1
    reject_probability: float = 0.03
    max_holding_bars: int = 24
    random_seed: int = 42


@dataclass(slots=True)
class EquityPoint:
    timestamp: datetime
    equity: float
    notional: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "equity": round(self.equity, 6),
            "notional": round(self.notional, 6),
        }


@dataclass(slots=True)
class SimulatedTrade:
    symbol: str
    status: str
    regime: str
    signal_at: datetime
    entry_at: datetime | None
    exit_at: datetime | None
    quantity: int
    holding_bars: int
    entry_price: float | None
    exit_price: float | None
    gross_pnl: float
    net_pnl: float
    return_pct: float
    commission_paid: float
    slippage_paid: float
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "regime": self.regime,
            "signal_at": self.signal_at.astimezone(UTC).isoformat(),
            "entry_at": self.entry_at.astimezone(UTC).isoformat() if self.entry_at else None,
            "exit_at": self.exit_at.astimezone(UTC).isoformat() if self.exit_at else None,
            "quantity": self.quantity,
            "holding_bars": self.holding_bars,
            "entry_price": round(self.entry_price, 6) if self.entry_price is not None else None,
            "exit_price": round(self.exit_price, 6) if self.exit_price is not None else None,
            "gross_pnl": round(self.gross_pnl, 6),
            "net_pnl": round(self.net_pnl, 6),
            "return_pct": round(self.return_pct, 6),
            "commission_paid": round(self.commission_paid, 6),
            "slippage_paid": round(self.slippage_paid, 6),
            "notes": self.notes,
        }


@dataclass(slots=True)
class BacktestResearchResult:
    metrics: dict[str, Any]
    equity_curve: list[EquityPoint]
    trades: list[SimulatedTrade]
    walk_forward: list[dict[str, Any]]
    regime_breakdown: list[dict[str, Any]]
    symbol_breakdown: list[dict[str, Any]]

    def equity_curve_payload(self) -> list[dict[str, Any]]:
        return [point.to_payload() for point in self.equity_curve]

    def trades_payload(self) -> list[dict[str, Any]]:
        return [trade.to_payload() for trade in self.trades]


@dataclass(slots=True)
class PendingEntry:
    signal_at: datetime
    fill_index: int
    regime: str
    stop_loss: float
    take_profit: float
    notes: list[str]


@dataclass(slots=True)
class OpenPosition:
    signal_at: datetime
    entry_at: datetime
    regime: str
    quantity: int
    entry_price: float
    stop_loss: float
    take_profit: float
    commission_entry: float
    entry_slippage: float
    holding_bars: int = 0


class BacktestService:
    def __init__(
        self,
        market_data: MarketDataAdapter,
        news_data: NewsAdapter,
        agent_runner: object | None = None,
        committee_service: object | None = None,
        risk_engine: object | None = None,
    ) -> None:
        self.market_data = market_data
        self.news_data = news_data
        self.agent_runner = agent_runner
        self.committee_service = committee_service
        self.risk_engine = risk_engine

    def run_research(
        self,
        *,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval_minutes: int,
        trading_profile: TradingProfile,
        config: BacktestSimulationConfig,
    ) -> BacktestResearchResult:
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            raise ValueError("At least one symbol is required for backtesting.")
        if interval_minutes <= 0:
            raise ValueError("Interval must be positive.")
        start_utc = _utc(start)
        end_utc = _utc(end)
        if end_utc <= start_utc:
            raise ValueError("Backtest end must be after start.")

        full_result = self._simulate(
            symbols=normalized_symbols,
            start=start_utc,
            end=end_utc,
            interval_minutes=interval_minutes,
            trading_profile=trading_profile,
            config=config,
        )

        walk_forward: list[dict[str, Any]] = []
        for window_name, window_start, window_end in _walk_forward_windows(start_utc, end_utc):
            window_result = self._simulate(
                symbols=normalized_symbols,
                start=window_start,
                end=window_end,
                interval_minutes=interval_minutes,
                trading_profile=trading_profile,
                config=config,
            )
            walk_forward.append(
                {
                    "window": window_name,
                    "start": window_start.astimezone(UTC).isoformat(),
                    "end": window_end.astimezone(UTC).isoformat(),
                    "trades": int(window_result.metrics["total_trades"]),
                    "rejected_orders": int(window_result.metrics["rejected_orders"]),
                    "total_return_pct": float(window_result.metrics["total_return_pct"]),
                    "win_rate": float(window_result.metrics["win_rate"]),
                    "expectancy": float(window_result.metrics["expectancy"]),
                    "sharpe_ratio": float(window_result.metrics["sharpe_ratio"]),
                    "max_drawdown_pct": float(window_result.metrics["max_drawdown_pct"]),
                }
            )

        return BacktestResearchResult(
            metrics=full_result.metrics,
            equity_curve=full_result.equity_curve,
            trades=full_result.trades,
            walk_forward=walk_forward,
            regime_breakdown=full_result.regime_breakdown,
            symbol_breakdown=full_result.symbol_breakdown,
        )

    def _simulate(
        self,
        *,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval_minutes: int,
        trading_profile: TradingProfile,
        config: BacktestSimulationConfig,
    ) -> BacktestResearchResult:
        allocated_equity = config.initial_equity / max(len(symbols), 1)
        all_trades: list[SimulatedTrade] = []
        symbol_curves: list[list[EquityPoint]] = []
        symbol_turnover = 0.0
        symbol_breakdown: list[dict[str, Any]] = []

        for offset, symbol in enumerate(symbols):
            bars = sorted(
                self.market_data.get_intraday_bars(
                    symbol,
                    start=start,
                    end=end,
                    interval_minutes=interval_minutes,
                ),
                key=lambda row: row.timestamp,
            )
            news = self._historical_news(symbol, start=start, end=end)
            curve, trades, rejected_orders, turnover = self._simulate_symbol(
                symbol=symbol,
                bars=bars,
                news_items=news,
                interval_minutes=interval_minutes,
                trading_profile=trading_profile,
                config=config,
                allocated_equity=allocated_equity,
                seed_offset=offset,
            )
            filled_trades = [item for item in trades if item.status == "filled"]
            final_equity = curve[-1].equity if curve else allocated_equity
            symbol_breakdown.append(
                {
                    "symbol": symbol,
                    "total_trades": len(filled_trades),
                    "rejected_orders": rejected_orders,
                    "final_equity": round(final_equity, 6),
                    "total_return_pct": round(((final_equity - allocated_equity) / max(allocated_equity, 1e-6)) * 100, 6),
                    "win_rate": round((sum(item.net_pnl > 0 for item in filled_trades) / max(len(filled_trades), 1)) * 100, 6)
                    if filled_trades
                    else 0.0,
                }
            )
            all_trades.extend(trades)
            symbol_curves.append(curve)
            symbol_turnover += turnover

        combined_curve = _combine_curves(symbol_curves, start=start, initial_equity=config.initial_equity)
        metrics = _portfolio_metrics(
            curve=combined_curve,
            trades=all_trades,
            turnover_notional=symbol_turnover,
            interval_minutes=interval_minutes,
            initial_equity=config.initial_equity,
        )
        regimes = _regime_breakdown(all_trades)
        return BacktestResearchResult(
            metrics=metrics,
            equity_curve=combined_curve,
            trades=all_trades,
            walk_forward=[],
            regime_breakdown=regimes,
            symbol_breakdown=symbol_breakdown,
        )

    def _simulate_symbol(
        self,
        *,
        symbol: str,
        bars: list[BarPoint],
        news_items: list[NewsItem],
        interval_minutes: int,
        trading_profile: TradingProfile,
        config: BacktestSimulationConfig,
        allocated_equity: float,
        seed_offset: int,
    ) -> tuple[list[EquityPoint], list[SimulatedTrade], int, float]:
        if not bars:
            return [EquityPoint(timestamp=datetime.now(UTC), equity=allocated_equity, notional=0.0)], [], 0, 0.0

        normalized_bars = [_normalize_bar(item) for item in bars]
        cash = allocated_equity
        slippage_rate = config.slippage_bps / 10_000
        rng = Random(config.random_seed + (seed_offset + 1) * _stable_symbol_seed(symbol))
        pending: PendingEntry | None = None
        open_position: OpenPosition | None = None
        curve: list[EquityPoint] = [EquityPoint(timestamp=normalized_bars[0].timestamp, equity=cash, notional=0.0)]
        trades: list[SimulatedTrade] = []
        rejected_orders = 0
        turnover = 0.0
        risk_budget_pct = _risk_budget_pct(trading_profile)
        news_by_bucket = _bucket_news(news_items, interval_minutes)
        warmup_bars = 10

        for index, bar in enumerate(normalized_bars):
            recent_news = _recent_news(news_by_bucket, bar.timestamp, interval_minutes)

            if pending and pending.fill_index == index:
                entry_price = bar.open * (1 + slippage_rate)
                if rng.random() < config.reject_probability:
                    rejected_orders += 1
                    trades.append(
                        SimulatedTrade(
                            symbol=symbol,
                            status="rejected",
                            regime=pending.regime,
                            signal_at=pending.signal_at,
                            entry_at=None,
                            exit_at=None,
                            quantity=0,
                            holding_bars=0,
                            entry_price=None,
                            exit_price=None,
                            gross_pnl=0.0,
                            net_pnl=0.0,
                            return_pct=0.0,
                            commission_paid=0.0,
                            slippage_paid=0.0,
                            notes=pending.notes + ["Simulated broker rejection."],
                        )
                    )
                    pending = None
                elif open_position is None:
                    stop_distance = max(entry_price - pending.stop_loss, 0.01)
                    risk_budget = cash * risk_budget_pct
                    quantity = max(int(risk_budget // stop_distance), 1)
                    affordable = int(cash // max(entry_price + config.commission_per_share, 0.01))
                    quantity = min(quantity, affordable)
                    if quantity <= 0:
                        rejected_orders += 1
                        trades.append(
                            SimulatedTrade(
                                symbol=symbol,
                                status="rejected",
                                regime=pending.regime,
                                signal_at=pending.signal_at,
                                entry_at=None,
                                exit_at=None,
                                quantity=0,
                                holding_bars=0,
                                entry_price=None,
                                exit_price=None,
                                gross_pnl=0.0,
                                net_pnl=0.0,
                                return_pct=0.0,
                                commission_paid=0.0,
                                slippage_paid=0.0,
                                notes=pending.notes + ["Rejected due to insufficient capital."],
                            )
                        )
                        pending = None
                    else:
                        commission_entry = quantity * config.commission_per_share
                        entry_slippage = quantity * max(entry_price - bar.open, 0.0)
                        cash -= (quantity * entry_price) + commission_entry
                        open_position = OpenPosition(
                            signal_at=pending.signal_at,
                            entry_at=bar.timestamp,
                            regime=pending.regime,
                            quantity=quantity,
                            entry_price=entry_price,
                            stop_loss=pending.stop_loss,
                            take_profit=pending.take_profit,
                            commission_entry=commission_entry,
                            entry_slippage=entry_slippage,
                        )
                        pending = None

            if open_position is not None:
                open_position.holding_bars += 1
                exit_reason, raw_exit = _resolve_exit(open_position, bar, config.max_holding_bars)
                if exit_reason:
                    exit_price = raw_exit * (1 - slippage_rate)
                    commission_exit = open_position.quantity * config.commission_per_share
                    exit_slippage = open_position.quantity * max(raw_exit - exit_price, 0.0)
                    gross_pnl = (exit_price - open_position.entry_price) * open_position.quantity
                    net_pnl = gross_pnl - open_position.commission_entry - commission_exit
                    return_pct = net_pnl / max(open_position.entry_price * open_position.quantity, 1e-6)
                    cash += (open_position.quantity * exit_price) - commission_exit
                    turnover += (open_position.quantity * open_position.entry_price) + (open_position.quantity * exit_price)
                    trades.append(
                        SimulatedTrade(
                            symbol=symbol,
                            status="filled",
                            regime=open_position.regime,
                            signal_at=open_position.signal_at,
                            entry_at=open_position.entry_at,
                            exit_at=bar.timestamp,
                            quantity=open_position.quantity,
                            holding_bars=open_position.holding_bars,
                            entry_price=open_position.entry_price,
                            exit_price=exit_price,
                            gross_pnl=gross_pnl,
                            net_pnl=net_pnl,
                            return_pct=return_pct,
                            commission_paid=open_position.commission_entry + commission_exit,
                            slippage_paid=open_position.entry_slippage + exit_slippage,
                            notes=[exit_reason],
                        )
                    )
                    open_position = None

            if (
                open_position is None
                and pending is None
                and index >= warmup_bars
                and index + config.fill_delay_bars < len(normalized_bars)
            ):
                indicators = bar_summary(normalized_bars[max(0, index - 20) : index + 1])
                regime = _classify_regime(
                    bar=bar,
                    previous=normalized_bars[index - 1] if index > 0 else None,
                    indicators=indicators,
                    recent_news=recent_news,
                )
                sentiment = _news_sentiment(recent_news)
                if _should_enter(indicators=indicators, regime=regime, sentiment=sentiment):
                    stop_loss, take_profit = _targets(entry=bar.close, regime=regime)
                    pending = PendingEntry(
                        signal_at=bar.timestamp,
                        fill_index=index + config.fill_delay_bars,
                        regime=regime,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        notes=[f"sentiment={sentiment:.3f}", f"regime={regime}"],
                    )

            notional = open_position.quantity * bar.close if open_position is not None else 0.0
            curve.append(EquityPoint(timestamp=bar.timestamp, equity=cash + notional, notional=notional))

        if open_position is not None:
            final_bar = normalized_bars[-1]
            exit_price = final_bar.close * (1 - slippage_rate)
            commission_exit = open_position.quantity * config.commission_per_share
            exit_slippage = open_position.quantity * max(final_bar.close - exit_price, 0.0)
            gross_pnl = (exit_price - open_position.entry_price) * open_position.quantity
            net_pnl = gross_pnl - open_position.commission_entry - commission_exit
            return_pct = net_pnl / max(open_position.entry_price * open_position.quantity, 1e-6)
            cash += (open_position.quantity * exit_price) - commission_exit
            turnover += (open_position.quantity * open_position.entry_price) + (open_position.quantity * exit_price)
            trades.append(
                SimulatedTrade(
                    symbol=symbol,
                    status="filled",
                    regime=open_position.regime,
                    signal_at=open_position.signal_at,
                    entry_at=open_position.entry_at,
                    exit_at=final_bar.timestamp,
                    quantity=open_position.quantity,
                    holding_bars=open_position.holding_bars,
                    entry_price=open_position.entry_price,
                    exit_price=exit_price,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    return_pct=return_pct,
                    commission_paid=open_position.commission_entry + commission_exit,
                    slippage_paid=open_position.entry_slippage + exit_slippage,
                    notes=["Forced session close."],
                )
            )
            curve.append(EquityPoint(timestamp=final_bar.timestamp, equity=cash, notional=0.0))

        return curve, trades, rejected_orders, turnover

    def _historical_news(self, symbol: str, *, start: datetime, end: datetime) -> list[NewsItem]:
        if hasattr(self.news_data, "get_news_between"):
            try:
                items = self.news_data.get_news_between(symbol, start=start, end=end, limit=400)
                return sorted((_normalize_news(item) for item in items), key=lambda item: item.created_at)
            except Exception:  # noqa: BLE001
                pass
        fallback = [_normalize_news(item) for item in self.news_data.get_recent_news(symbol, limit=50)]
        return [item for item in fallback if start <= item.created_at <= end]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize_bar(item: BarPoint) -> BarPoint:
    return BarPoint(timestamp=_utc(item.timestamp), open=item.open, high=item.high, low=item.low, close=item.close, volume=item.volume)


def _normalize_news(item: NewsItem) -> NewsItem:
    return NewsItem(
        headline=item.headline,
        summary=item.summary,
        source=item.source,
        created_at=_utc(item.created_at),
        sentiment_hint=item.sentiment_hint,
    )


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in symbols:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def _walk_forward_windows(start: datetime, end: datetime) -> list[tuple[str, datetime, datetime]]:
    total_seconds = (end - start).total_seconds()
    if total_seconds <= 0:
        return []
    train_end = start + timedelta(seconds=total_seconds * 0.6)
    validation_end = start + timedelta(seconds=total_seconds * 0.8)
    if not (start < train_end < validation_end < end):
        return []
    return [("train", start, train_end), ("validation", train_end, validation_end), ("test", validation_end, end)]


def _bucket_news(news_items: list[NewsItem], interval_minutes: int) -> dict[datetime, list[NewsItem]]:
    buckets: dict[datetime, list[NewsItem]] = defaultdict(list)
    for item in news_items:
        buckets[_bucket_time(item.created_at, interval_minutes)].append(item)
    return buckets


def _bucket_time(value: datetime, interval_minutes: int) -> datetime:
    timestamp = _utc(value)
    interval = max(interval_minutes, 1)
    minute = (timestamp.minute // interval) * interval
    return timestamp.replace(minute=minute, second=0, microsecond=0)


def _recent_news(news_by_bucket: dict[datetime, list[NewsItem]], timestamp: datetime, interval_minutes: int) -> list[NewsItem]:
    current_bucket = _bucket_time(timestamp, interval_minutes)
    rows: list[NewsItem] = []
    for step in range(3):
        rows.extend(news_by_bucket.get(current_bucket - timedelta(minutes=step * interval_minutes), []))
    return rows


def _news_sentiment(news_items: list[NewsItem]) -> float:
    if not news_items:
        return 0.0
    score = 0
    for item in news_items:
        text = f"{item.headline} {item.summary} {item.sentiment_hint}".lower()
        score += sum(term in text for term in POSITIVE_NEWS_TERMS)
        score -= sum(term in text for term in NEGATIVE_NEWS_TERMS)
    normalized = (score / max(len(news_items), 1)) / 4
    return max(min(normalized, 1.0), -1.0)


def _classify_regime(*, bar: BarPoint, previous: BarPoint | None, indicators: dict[str, float], recent_news: list[NewsItem]) -> str:
    if previous is not None:
        gap = abs(bar.open - previous.close) / max(previous.close, 1e-6)
        if gap >= 0.01:
            return "gap_driven"
    if recent_news:
        return "event_heavy"
    trend = abs(indicators["sma_10"] - indicators["sma_20"]) / max(indicators["sma_20"], 1e-6)
    if trend >= 0.003 and abs(indicators["momentum_pct"]) >= 0.2:
        return "trend"
    return "chop"


def _should_enter(*, indicators: dict[str, float], regime: str, sentiment: float) -> bool:
    if indicators["sma_10"] <= indicators["sma_20"]:
        return False
    if indicators["momentum_pct"] < 0.08:
        return False
    if not 40 <= indicators["rsi_14"] <= 90:
        return False
    if sentiment < -0.2:
        return False
    if regime == "chop" and indicators["momentum_pct"] < 0.12:
        return False
    return True


def _targets(*, entry: float, regime: str) -> tuple[float, float]:
    if regime == "trend":
        return entry * (1 - 0.0045), entry * (1 + 0.0105)
    if regime == "event_heavy":
        return entry * (1 - 0.0065), entry * (1 + 0.012)
    if regime == "gap_driven":
        return entry * (1 - 0.006), entry * (1 + 0.011)
    return entry * (1 - 0.0055), entry * (1 + 0.0075)


def _resolve_exit(position: OpenPosition, bar: BarPoint, max_holding_bars: int) -> tuple[str | None, float]:
    if bar.low <= position.stop_loss:
        return "Stop loss hit.", position.stop_loss
    if bar.high >= position.take_profit:
        return "Take profit hit.", position.take_profit
    if position.holding_bars >= max_holding_bars:
        return "Max holding bars reached.", bar.close
    return None, bar.close


def _combine_curves(curves: list[list[EquityPoint]], *, start: datetime, initial_equity: float) -> list[EquityPoint]:
    if not curves:
        return [EquityPoint(timestamp=start, equity=initial_equity, notional=0.0)]
    all_timestamps = sorted({point.timestamp for curve in curves for point in curve})
    if not all_timestamps:
        return [EquityPoint(timestamp=start, equity=initial_equity, notional=0.0)]
    positions = [0 for _ in curves]
    combined: list[EquityPoint] = []
    for timestamp in all_timestamps:
        total_equity = 0.0
        total_notional = 0.0
        for idx, curve in enumerate(curves):
            while positions[idx] + 1 < len(curve) and curve[positions[idx] + 1].timestamp <= timestamp:
                positions[idx] += 1
            point = curve[positions[idx]]
            total_equity += point.equity
            total_notional += point.notional
        combined.append(EquityPoint(timestamp=timestamp, equity=total_equity, notional=total_notional))
    return combined


def _portfolio_metrics(
    *,
    curve: list[EquityPoint],
    trades: list[SimulatedTrade],
    turnover_notional: float,
    interval_minutes: int,
    initial_equity: float,
) -> dict[str, Any]:
    filled = [trade for trade in trades if trade.status == "filled"]
    rejected = sum(trade.status == "rejected" for trade in trades)
    final_equity = curve[-1].equity if curve else initial_equity
    total_return_pct = ((final_equity - initial_equity) / max(initial_equity, 1e-6)) * 100
    returns = [
        (curve[idx].equity - curve[idx - 1].equity) / curve[idx - 1].equity
        for idx in range(1, len(curve))
        if curve[idx - 1].equity > 0
    ]
    if len(returns) >= 2 and stdev(returns) > 0:
        annualization = sqrt((390 / max(interval_minutes, 1)) * 252)
        sharpe = (mean(returns) / stdev(returns)) * annualization
    else:
        sharpe = 0.0
    peak = curve[0].equity if curve else initial_equity
    max_drawdown = 0.0
    exposures: list[float] = []
    for point in curve:
        peak = max(peak, point.equity)
        max_drawdown = max(max_drawdown, (peak - point.equity) / max(peak, 1e-6))
        exposures.append(point.notional / max(point.equity, 1e-6) if point.equity > 0 else 0.0)
    wins = sum(trade.net_pnl > 0 for trade in filled)
    win_rate = (wins / max(len(filled), 1)) * 100 if filled else 0.0
    expectancy = mean([trade.net_pnl for trade in filled]) if filled else 0.0
    avg_equity = mean([point.equity for point in curve]) if curve else initial_equity
    return {
        "total_trades": len(filled),
        "rejected_orders": int(rejected),
        "final_equity": round(final_equity, 6),
        "total_return_pct": round(total_return_pct, 6),
        "win_rate": round(win_rate, 6),
        "expectancy": round(expectancy, 6),
        "sharpe_ratio": round(sharpe, 6),
        "max_drawdown_pct": round(max_drawdown * 100, 6),
        "turnover": round(turnover_notional / max(avg_equity, 1e-6), 6),
        "avg_exposure_pct": round((mean(exposures) * 100) if exposures else 0.0, 6),
        "max_exposure_pct": round((max(exposures) * 100) if exposures else 0.0, 6),
    }


def _regime_breakdown(trades: list[SimulatedTrade]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SimulatedTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.regime].append(trade)
    rows: list[dict[str, Any]] = []
    for regime, regime_trades in sorted(grouped.items()):
        filled = [trade for trade in regime_trades if trade.status == "filled"]
        wins = sum(trade.net_pnl > 0 for trade in filled)
        rows.append(
            {
                "regime": regime,
                "trades": len(filled),
                "rejected_orders": sum(trade.status == "rejected" for trade in regime_trades),
                "win_rate": round((wins / max(len(filled), 1)) * 100, 6) if filled else 0.0,
                "expectancy": round(mean([trade.net_pnl for trade in filled]), 6) if filled else 0.0,
                "avg_return_pct": round(mean([trade.return_pct for trade in filled]) * 100, 6) if filled else 0.0,
                "net_pnl": round(sum(trade.net_pnl for trade in filled), 6),
            }
        )
    return rows


def _stable_symbol_seed(symbol: str) -> int:
    return sum((idx + 1) * ord(char) for idx, char in enumerate(symbol.upper()))


def _risk_budget_pct(profile: TradingProfile) -> float:
    if profile.risk_profile is None:
        return 0.005
    if profile.risk_profile.value == "conservative":
        return 0.003
    if profile.risk_profile.value == "aggressive":
        return 0.008
    return 0.005
