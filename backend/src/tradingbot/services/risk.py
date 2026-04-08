from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.models import BotSettings, PortfolioSnapshot, RiskEvent, SymbolCooldown, TradeReview
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult

SECTOR_BUCKETS: dict[str, str] = {
    "AAPL": "XLK",
    "MSFT": "XLK",
    "NVDA": "SMH",
    "AMD": "SMH",
    "AMZN": "XLY",
    "TSLA": "XLY",
    "META": "XLC",
    "GOOGL": "XLC",
    "JPM": "XLF",
    "BAC": "XLF",
    "XOM": "XLE",
    "CVX": "XLE",
    "UNH": "XLV",
    "PFE": "XLV",
}

CORRELATION_BUCKETS: dict[str, str] = {
    "XLK": "growth",
    "SMH": "growth",
    "XLC": "growth",
    "XLY": "consumer_beta",
    "XLF": "rates",
    "XLE": "commodities",
    "XLV": "defensive",
}

EVENT_CLUSTER_TYPES = {"earnings_date", "macro_release", "economic_calendar"}
NEWS_WHIPSAW_TYPES = {"earnings_date", "macro_release", "analyst_action"}

EXECUTION_FAILURE_CODES = {
    "broker_submit_failed",
    "order_invalid_transition",
    "reconciliation_orphan_broker_order",
    "reconciliation_orphan_local_order",
}


@dataclass(slots=True)
class PositionExposure:
    symbol: str
    market_value: float
    side: str = "long"


@dataclass(slots=True)
class PortfolioRuntimeMetrics:
    positions: list[PositionExposure]
    portfolio_exposure: float
    equity_drawdown_pct: float
    loss_streak: int
    recent_execution_failures: int
    severe_anomaly_count: int


@dataclass(slots=True)
class RiskPolicy:
    max_open_positions: int
    max_daily_loss_pct: float
    max_position_risk_pct: float
    max_symbol_notional_pct: float
    symbol_cooldown_minutes: int
    max_gross_exposure_pct: float = 0.9
    max_sector_exposure_pct: float = 1.0
    max_correlation_exposure_pct: float = 1.0
    max_event_cluster_positions: int = 3
    volatility_target_pct: float = 1.2
    atr_sizing_multiplier: float = 1.0
    equity_curve_throttle_start_pct: float = 0.015
    equity_curve_throttle_min_scale: float = 0.4
    intraday_drawdown_pause_pct: float = 0.03
    loss_streak_reduction_threshold: int = 3
    loss_streak_size_scale: float = 0.6
    execution_failure_review_threshold: int = 3
    severe_anomaly_kill_switch_threshold: int = 4
    symbol_cooldown_profit_minutes: int = 20
    symbol_cooldown_stopout_minutes: int = 90
    symbol_cooldown_event_minutes: int = 180
    symbol_cooldown_whipsaw_minutes: int = 120


def risk_policy_from_settings(settings_row: BotSettings | None) -> RiskPolicy:
    if settings_row is None:
        return RiskPolicy(
            max_open_positions=6,
            max_daily_loss_pct=0.025,
            max_position_risk_pct=0.005,
            max_symbol_notional_pct=0.16,
            symbol_cooldown_minutes=45,
        )
    return RiskPolicy(
        max_open_positions=settings_row.max_open_positions,
        max_daily_loss_pct=settings_row.max_daily_loss_pct,
        max_position_risk_pct=settings_row.max_position_risk_pct,
        max_symbol_notional_pct=settings_row.max_symbol_notional_pct,
        symbol_cooldown_minutes=settings_row.symbol_cooldown_minutes,
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
        symbol_cooldown_profit_minutes=settings_row.symbol_cooldown_profit_minutes,
        symbol_cooldown_stopout_minutes=settings_row.symbol_cooldown_stopout_minutes,
        symbol_cooldown_event_minutes=settings_row.symbol_cooldown_event_minutes,
        symbol_cooldown_whipsaw_minutes=settings_row.symbol_cooldown_whipsaw_minutes,
    )


class RiskEngine:
    def __init__(self, policy: RiskPolicy) -> None:
        self.policy = policy

    def validate(
        self,
        decision: CommitteeDecision,
        *,
        equity: float,
        buying_power: float,
        open_positions: int,
        daily_loss_pct: float,
        active_symbol_exposure: float,
        is_symbol_in_cooldown: bool,
        portfolio_exposure: float | None = None,
        positions: Sequence[PositionExposure | dict[str, Any] | Any] | None = None,
        feature_snapshot: dict[str, float] | None = None,
        structured_events: list[dict[str, Any]] | None = None,
        equity_drawdown_pct: float = 0.0,
        loss_streak: int = 0,
        recent_execution_failures: int = 0,
        pretrade_notes: list[str] | None = None,
    ) -> RiskCheckResult:
        notes: list[str] = []
        feature_snapshot = feature_snapshot or {}
        structured_events = structured_events or []
        normalized_positions = _normalize_positions(positions or [])

        if decision.direction != OrderIntent.BUY:
            return RiskCheckResult(decision=RiskDecision.REJECTED, notes=["Only long entries are enabled in v1."])

        if decision.status != RiskDecision.APPROVED:
            return RiskCheckResult(
                decision=RiskDecision.REJECTED,
                notes=[decision.reject_reason or "Committee rejected the trade."],
            )

        if is_symbol_in_cooldown:
            notes.append("Symbol is in cooldown after a recent outcome-aware exit rule.")
        if open_positions >= self.policy.max_open_positions:
            notes.append("Maximum open positions reached.")
        if daily_loss_pct >= self.policy.max_daily_loss_pct:
            notes.append("Daily loss limit breached.")
        if equity_drawdown_pct >= self.policy.intraday_drawdown_pause_pct:
            notes.append("Intraday drawdown circuit breaker breached.")
        if recent_execution_failures >= self.policy.execution_failure_review_threshold:
            notes.append("Repeated execution failures require manual review before new entries.")

        stop_distance = max(decision.entry - decision.stop_loss, 0.0)
        if stop_distance <= 0:
            notes.append("Stop loss must be below entry for long trades.")

        atr_14 = max(_as_float(feature_snapshot.get("atr_14"), fallback=0.0), 0.0)
        effective_stop_distance = max(stop_distance, atr_14 * self.policy.atr_sizing_multiplier, 0.01)
        per_trade_risk_budget = max(equity, 0.0) * self.policy.max_position_risk_pct
        base_quantity = int(per_trade_risk_budget // effective_stop_distance)

        if base_quantity <= 0:
            notes.append("Risk budget does not allow any shares.")

        volatility_pct = _as_float(feature_snapshot.get("intraday_volatility_pct"), fallback=0.0)
        volatility_scale = self._volatility_scale(volatility_pct)
        confidence_scale = self._confidence_scale(decision.confidence)
        equity_curve_scale = self._equity_curve_scale(equity_drawdown_pct)
        streak_scale = self.policy.loss_streak_size_scale if loss_streak >= self.policy.loss_streak_reduction_threshold else 1.0
        total_scale = max(0.05, volatility_scale * confidence_scale * equity_curve_scale * streak_scale)
        approved_quantity = int(base_quantity * total_scale)
        notional = approved_quantity * decision.entry

        if approved_quantity <= 0:
            notes.append("Sizing throttles reduced position to zero.")
        if notional > buying_power:
            notes.append("Insufficient buying power.")
        if active_symbol_exposure + notional > equity * self.policy.max_symbol_notional_pct:
            notes.append("Symbol exposure cap breached.")

        total_portfolio_exposure = (
            portfolio_exposure if portfolio_exposure is not None else sum(max(item.market_value, 0.0) for item in normalized_positions)
        )
        if total_portfolio_exposure + notional > equity * self.policy.max_gross_exposure_pct:
            notes.append("Gross exposure cap breached.")

        candidate_sector = _resolve_sector_bucket(decision.symbol, structured_events)
        candidate_corr_bucket = _resolve_correlation_bucket(candidate_sector)
        sector_exposure = notional
        correlation_exposure = notional
        for item in normalized_positions:
            sector_bucket = _resolve_sector_bucket(item.symbol, [])
            corr_bucket = _resolve_correlation_bucket(sector_bucket)
            if sector_bucket == candidate_sector:
                sector_exposure += max(item.market_value, 0.0)
            if corr_bucket == candidate_corr_bucket:
                correlation_exposure += max(item.market_value, 0.0)

        if sector_exposure > equity * self.policy.max_sector_exposure_pct:
            notes.append(f"Sector exposure cap breached for {candidate_sector}.")
        if correlation_exposure > equity * self.policy.max_correlation_exposure_pct:
            notes.append("Correlation exposure cap breached.")
        if _has_event_cluster_risk(structured_events) and open_positions >= self.policy.max_event_cluster_positions:
            notes.append("Event clustering cap breached for elevated catalyst regime.")

        if pretrade_notes:
            notes.extend(pretrade_notes)

        if notes:
            return RiskCheckResult(decision=RiskDecision.REJECTED, notes=notes)

        return RiskCheckResult(
            decision=RiskDecision.APPROVED,
            approved_quantity=approved_quantity,
            notes=[
                "Risk checks passed.",
                (
                    f"Sizing scales applied: volatility={round(volatility_scale, 3)}, "
                    f"confidence={round(confidence_scale, 3)}, equity_curve={round(equity_curve_scale, 3)}, "
                    f"loss_streak={round(streak_scale, 3)}."
                ),
            ],
        )

    def _volatility_scale(self, volatility_pct: float) -> float:
        if volatility_pct <= 0:
            return 1.0
        target = max(self.policy.volatility_target_pct, 0.01)
        raw_scale = target / max(volatility_pct, 0.01)
        return min(max(raw_scale, 0.35), 1.25)

    def _confidence_scale(self, confidence: float) -> float:
        normalized = max(min(confidence, 1.0), 0.0)
        return 0.4 + (normalized * 0.6)

    def _equity_curve_scale(self, equity_drawdown_pct: float) -> float:
        start = max(self.policy.equity_curve_throttle_start_pct, 0.0)
        floor = max(min(self.policy.equity_curve_throttle_min_scale, 1.0), 0.05)
        if equity_drawdown_pct <= start:
            return 1.0
        if start >= 0.95:
            return floor
        relative = min(max((equity_drawdown_pct - start) / max(1.0 - start, 1e-6), 0.0), 1.0)
        return max(1.0 - relative, floor)


class PortfolioRiskService:
    def __init__(self, session: Session, policy: RiskPolicy) -> None:
        self.session = session
        self.policy = policy

    def compute_runtime_metrics(
        self,
        *,
        equity: float,
        positions: Sequence[PositionExposure | dict[str, Any] | Any],
        now: datetime | None = None,
    ) -> PortfolioRuntimeMetrics:
        as_of = now or datetime.now(UTC)
        normalized_positions = _normalize_positions(positions)
        return PortfolioRuntimeMetrics(
            positions=normalized_positions,
            portfolio_exposure=round(sum(max(item.market_value, 0.0) for item in normalized_positions), 6),
            equity_drawdown_pct=self._equity_drawdown_pct(current_equity=equity, now=as_of),
            loss_streak=self._loss_streak(),
            recent_execution_failures=self._recent_execution_failures(now=as_of),
            severe_anomaly_count=self._recent_severe_anomalies(now=as_of),
        )

    def active_cooldown(self, symbol: str, *, as_of: datetime | None = None) -> tuple[bool, list[str]]:
        now = as_of or datetime.now(UTC)
        row = self.session.scalar(
            select(SymbolCooldown)
            .where(SymbolCooldown.symbol == symbol.upper().strip())
            .where(SymbolCooldown.expires_at > now)
        )
        if row is None:
            return False, []
        return True, [
            (
                f"Symbol cooldown is active until {row.expires_at.astimezone(UTC).isoformat()} "
                f"({row.cooldown_type})."
            )
        ]

    def upsert_cooldown_from_exit(
        self,
        *,
        symbol: str,
        pnl: float,
        return_pct: float,
        review_payload: dict[str, Any] | None,
        as_of: datetime | None = None,
    ) -> SymbolCooldown | None:
        payload = review_payload or {}
        structured_events = payload.get("structured_events", [])
        feature_snapshot = payload.get("feature_snapshot", {})
        event_types = {
            str(item.get("event_type"))
            for item in structured_events
            if isinstance(item, dict) and item.get("event_type")
        }
        has_news_whipsaw = any(event_type in NEWS_WHIPSAW_TYPES for event_type in event_types)
        has_high_significance_event = any(
            isinstance(item, dict)
            and item.get("event_type") in EVENT_CLUSTER_TYPES
            and str(item.get("significance", "")).lower() == "high"
            for item in structured_events
        )
        intraday_volatility = _as_float(feature_snapshot.get("intraday_volatility_pct"), fallback=0.0)
        high_volatility_context = intraday_volatility >= max(self.policy.volatility_target_pct * 1.4, 1.8)

        cooldown_type = "profit_exit"
        cooldown_minutes = self.policy.symbol_cooldown_profit_minutes
        reason = "Cooldown after profitable exit."
        if pnl < 0:
            cooldown_type = "stop_out"
            cooldown_minutes = self.policy.symbol_cooldown_stopout_minutes
            reason = "Cooldown after losing exit."
            if has_news_whipsaw:
                cooldown_type = "news_whipsaw"
                cooldown_minutes = max(cooldown_minutes, self.policy.symbol_cooldown_whipsaw_minutes)
                reason = "Extended cooldown after potential news whipsaw."
            if has_high_significance_event and high_volatility_context:
                cooldown_type = "event_failure"
                cooldown_minutes = max(cooldown_minutes, self.policy.symbol_cooldown_event_minutes)
                reason = "Extended cooldown after high-volatility event failure."

        cooldown_minutes = max(cooldown_minutes, self.policy.symbol_cooldown_minutes)
        if cooldown_minutes <= 0:
            return None

        now = as_of or datetime.now(UTC)
        expires_at = now + timedelta(minutes=cooldown_minutes)
        symbol_key = symbol.upper().strip()
        row = self.session.scalar(select(SymbolCooldown).where(SymbolCooldown.symbol == symbol_key))
        context_payload = {
            "pnl": round(pnl, 6),
            "return_pct": round(return_pct, 6),
            "event_types": sorted(event_types),
            "intraday_volatility_pct": round(intraday_volatility, 6),
        }
        if row is None:
            row = SymbolCooldown(
                symbol=symbol_key,
                cooldown_type=cooldown_type,
                reason=reason,
                triggered_at=now,
                expires_at=expires_at,
                context_json=context_payload,
            )
            self.session.add(row)
        else:
            row.cooldown_type = cooldown_type
            row.reason = reason
            row.triggered_at = now
            row.expires_at = max(row.expires_at, expires_at)
            row.context_json = context_payload
        return row

    def trigger_kill_switch_if_needed(
        self,
        settings_row: BotSettings,
        *,
        runtime: PortfolioRuntimeMetrics,
    ) -> bool:
        if settings_row.kill_switch_enabled:
            return False
        if runtime.severe_anomaly_count < self.policy.severe_anomaly_kill_switch_threshold:
            return False

        settings_row.kill_switch_enabled = True
        settings_row.live_enabled = False
        self.session.add(
            RiskEvent(
                symbol=None,
                severity="critical",
                code="auto_kill_switch",
                message="Kill switch auto-enabled after severe anomaly threshold was breached.",
                payload={
                    "severe_anomalies": runtime.severe_anomaly_count,
                    "threshold": self.policy.severe_anomaly_kill_switch_threshold,
                },
            )
        )
        return True

    def _equity_drawdown_pct(self, *, current_equity: float, now: datetime) -> float:
        lookback_start = now - timedelta(days=1)
        peak_equity = self.session.scalar(
            select(func.max(PortfolioSnapshot.equity)).where(PortfolioSnapshot.created_at >= lookback_start)
        )
        if peak_equity is None:
            return 0.0
        peak = max(float(peak_equity), 1e-6)
        return max((peak - max(current_equity, 0.0)) / peak, 0.0)

    def _loss_streak(self) -> int:
        rows = self.session.scalars(select(TradeReview).order_by(TradeReview.created_at.desc()).limit(20)).all()
        streak = 0
        for row in rows:
            if row.pnl < 0:
                streak += 1
                continue
            break
        return streak

    def _recent_execution_failures(self, *, now: datetime) -> int:
        window_start = now - timedelta(hours=12)
        count = self.session.scalar(
            select(func.count())
            .select_from(RiskEvent)
            .where(RiskEvent.created_at >= window_start)
            .where(RiskEvent.code.in_(tuple(EXECUTION_FAILURE_CODES)))
        )
        return int(count or 0)

    def _recent_severe_anomalies(self, *, now: datetime) -> int:
        window_start = now - timedelta(hours=6)
        count = self.session.scalar(
            select(func.count())
            .select_from(RiskEvent)
            .where(RiskEvent.created_at >= window_start)
            .where(RiskEvent.severity == "critical")
        )
        return int(count or 0)


def _resolve_sector_bucket(symbol: str, structured_events: Sequence[dict[str, Any]]) -> str:
    normalized = symbol.upper().strip()
    for event in structured_events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "sector_etf_context":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        sector_etf = payload.get("sector_etf")
        if isinstance(sector_etf, str) and sector_etf.strip():
            return sector_etf.upper().strip()
    if normalized in CORRELATION_BUCKETS:
        return normalized
    return SECTOR_BUCKETS.get(normalized, "OTHER")


def _resolve_correlation_bucket(sector_bucket: str) -> str:
    return CORRELATION_BUCKETS.get(sector_bucket.upper().strip(), "other")


def _has_event_cluster_risk(structured_events: Iterable[dict[str, Any]]) -> bool:
    for event in structured_events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") not in EVENT_CLUSTER_TYPES:
            continue
        significance = str(event.get("significance", "")).lower()
        if significance in {"high", "critical"}:
            return True
    return False


def _normalize_positions(positions: Sequence[PositionExposure | dict[str, Any] | Any]) -> list[PositionExposure]:
    normalized: list[PositionExposure] = []
    for item in positions:
        if isinstance(item, PositionExposure):
            normalized.append(item)
            continue
        if isinstance(item, dict):
            symbol = str(item.get("symbol") or "").upper().strip()
            market_value = _as_float(item.get("market_value"), fallback=0.0)
            side = str(item.get("side") or "long")
        else:
            symbol = str(getattr(item, "symbol", "") or "").upper().strip()
            market_value = _as_float(getattr(item, "market_value", 0.0), fallback=0.0)
            side = str(getattr(item, "side", "long") or "long")
        if not symbol:
            continue
        normalized.append(PositionExposure(symbol=symbol, market_value=market_value, side=side))
    return normalized


def _as_float(value: Any, *, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
