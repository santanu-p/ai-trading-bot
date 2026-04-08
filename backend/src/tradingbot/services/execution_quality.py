from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.enums import BrokerSlug, OrderIntent, OrderStatus, OrderType, TimeInForce
from tradingbot.models import ExecutionQualitySample, OrderFill, OrderRecord
from tradingbot.services.adapters import LiquiditySnapshot

_TERMINAL_OUTCOMES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.EXPIRED,
    OrderStatus.REJECTED,
    OrderStatus.REPLACED,
}


@dataclass(slots=True)
class ExecutionQualityPolicy:
    max_expected_slippage_bps: float = 80.0
    max_expected_spread_bps: float = 45.0
    min_liquidity_score: float = 0.28
    feedback_lookback_hours: int = 72
    feedback_min_samples: int = 6
    feedback_size_floor: float = 0.45
    feedback_block_score: float = 0.25
    feedback_block_reject_rate: float = 0.5


@dataclass(slots=True)
class ExecutionPreview:
    accepted: bool
    reasons: list[str]
    intended_price: float
    reference_price: float
    expected_slippage_bps: float
    expected_spread_bps: float
    expected_slippage_value: float
    liquidity_score: float
    aggressiveness: str
    order_type: OrderType
    time_in_force: TimeInForce
    entry_limit_price: float | None
    venue: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "intended_price": round(self.intended_price, 6),
            "reference_price": round(self.reference_price, 6),
            "expected_slippage_bps": round(self.expected_slippage_bps, 4),
            "expected_spread_bps": round(self.expected_spread_bps, 4),
            "expected_slippage_value": round(self.expected_slippage_value, 6),
            "liquidity_score": round(self.liquidity_score, 6),
            "aggressiveness": self.aggressiveness,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "entry_limit_price": round(self.entry_limit_price, 6) if self.entry_limit_price is not None else None,
            "venue": self.venue,
        }


@dataclass(slots=True)
class ExecutionFeedback:
    symbol: str
    sample_count: int
    avg_slippage_bps: float
    avg_time_to_fill_seconds: float
    reject_rate: float
    cancel_rate: float
    quality_score: float
    size_scale: float
    block_new_entries: bool
    notes: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sample_count": self.sample_count,
            "avg_slippage_bps": round(self.avg_slippage_bps, 6),
            "avg_time_to_fill_seconds": round(self.avg_time_to_fill_seconds, 3),
            "reject_rate": round(self.reject_rate, 6),
            "cancel_rate": round(self.cancel_rate, 6),
            "quality_score": round(self.quality_score, 6),
            "size_scale": round(self.size_scale, 6),
            "block_new_entries": self.block_new_entries,
            "notes": list(self.notes),
        }


class ExecutionQualityService:
    def __init__(
        self,
        session: Session,
        *,
        broker_slug: BrokerSlug,
        default_venue: str | None,
        policy: ExecutionQualityPolicy | None = None,
    ) -> None:
        self.session = session
        self.broker_slug = broker_slug
        self.default_venue = (default_venue or "unknown").strip() or "unknown"
        self.policy = policy or ExecutionQualityPolicy()

    def preview_order(
        self,
        *,
        symbol: str,
        side: OrderIntent,
        quantity: int,
        intended_price: float,
        feature_snapshot: dict[str, float] | None,
        liquidity_snapshot: LiquiditySnapshot | None,
        preferred_venue: str | None,
    ) -> ExecutionPreview:
        del symbol
        normalized_quantity = max(int(quantity), 1)
        reference_price = self._reference_price(intended_price, liquidity_snapshot)
        if reference_price <= 0:
            return ExecutionPreview(
                accepted=False,
                reasons=["Unable to resolve a valid reference price for execution-quality checks."],
                intended_price=max(float(intended_price), 0.0),
                reference_price=0.0,
                expected_slippage_bps=0.0,
                expected_spread_bps=0.0,
                expected_slippage_value=0.0,
                liquidity_score=0.0,
                aggressiveness="blocked",
                order_type=OrderType.BRACKET,
                time_in_force=TimeInForce.DAY,
                entry_limit_price=None,
                venue=preferred_venue or self.default_venue,
            )

        features = feature_snapshot or {}
        expected_spread_bps = self._estimate_spread_bps(liquidity_snapshot, features)
        expected_slippage_bps = self._estimate_slippage_bps(
            spread_bps=expected_spread_bps,
            quantity=normalized_quantity,
            liquidity_snapshot=liquidity_snapshot,
            feature_snapshot=features,
        )
        liquidity_score = self._liquidity_score(
            spread_bps=expected_spread_bps,
            quantity=normalized_quantity,
            liquidity_snapshot=liquidity_snapshot,
            feature_snapshot=features,
        )

        reasons: list[str] = []
        if expected_spread_bps > self.policy.max_expected_spread_bps:
            reasons.append(
                (
                    "Execution-quality gate rejected the setup because estimated spread is too wide "
                    f"({round(expected_spread_bps, 2)} bps)."
                )
            )
        if expected_slippage_bps > self.policy.max_expected_slippage_bps:
            reasons.append(
                (
                    "Execution-quality gate rejected the setup because expected slippage is too high "
                    f"({round(expected_slippage_bps, 2)} bps)."
                )
            )
        if liquidity_score < self.policy.min_liquidity_score:
            reasons.append(
                (
                    "Execution-quality gate rejected the setup because liquidity score is below threshold "
                    f"({round(liquidity_score, 3)})."
                )
            )

        aggressiveness, order_type, time_in_force, limit_price = self._execution_plan(
            side=side,
            reference_price=reference_price,
            expected_spread_bps=expected_spread_bps,
            liquidity_score=liquidity_score,
        )

        venue = (preferred_venue or liquidity_snapshot.venue if liquidity_snapshot else None) or self.default_venue
        expected_slippage_value = normalized_quantity * reference_price * (expected_slippage_bps / 10_000)

        return ExecutionPreview(
            accepted=not reasons,
            reasons=reasons,
            intended_price=float(intended_price),
            reference_price=reference_price,
            expected_slippage_bps=expected_slippage_bps,
            expected_spread_bps=expected_spread_bps,
            expected_slippage_value=expected_slippage_value,
            liquidity_score=liquidity_score,
            aggressiveness=aggressiveness,
            order_type=order_type,
            time_in_force=time_in_force,
            entry_limit_price=limit_price,
            venue=venue,
        )

    def upsert_order_sample(self, order: OrderRecord, *, fills: list[OrderFill] | None = None) -> ExecutionQualitySample:
        metadata = order.metadata_json or {}
        execution_payload = _execution_payload(metadata)
        order_fills = fills if fills is not None else self.session.scalars(
            select(OrderFill).where(OrderFill.order_id == order.id).order_by(OrderFill.filled_at.asc())
        ).all()

        intended_price = _optional_float(execution_payload.get("intended_price"))
        if intended_price is None:
            intended_price = _decision_entry(metadata)
        if intended_price is None:
            intended_price = _optional_float(order.limit_price)
        if intended_price is None:
            intended_price = _optional_float(order.stop_price)

        realized_price = _optional_float(order.average_fill_price)
        expected_slippage_bps = _optional_float(execution_payload.get("expected_slippage_bps"))
        expected_spread_bps = _optional_float(execution_payload.get("expected_spread_bps"))
        liquidity_score = _optional_float(execution_payload.get("liquidity_score"), fallback=0.5) or 0.5
        aggressiveness = _optional_str(execution_payload.get("aggressiveness"))

        fill_ratio = min(max(order.filled_quantity / max(order.quantity, 1), 0.0), 1.0)
        notional_price = realized_price or intended_price or _optional_float(order.limit_price, fallback=0.0) or 0.0
        notional = max(notional_price, 0.0) * max(order.filled_quantity, 0)
        realized_slippage_bps = _realized_slippage_bps(order.direction, intended_price, realized_price)
        spread_cost = _spread_cost(expected_spread_bps, notional_price, order.filled_quantity)
        time_to_fill_seconds = _time_to_fill_seconds(order, order_fills)
        quality_score = _outcome_quality_score(
            base_score=liquidity_score,
            status=order.status,
            realized_slippage_bps=realized_slippage_bps,
            expected_slippage_bps=expected_slippage_bps,
            fill_ratio=fill_ratio,
            time_to_fill_seconds=time_to_fill_seconds,
        )

        broker_slug = _broker_slug_from_payload(execution_payload.get("broker_slug"), self.broker_slug)
        venue = _optional_str(execution_payload.get("venue")) or self.default_venue

        row = self.session.scalar(select(ExecutionQualitySample).where(ExecutionQualitySample.order_id == order.id))
        if row is None:
            row = ExecutionQualitySample(
                order_id=order.id,
                symbol=order.symbol,
                broker_slug=broker_slug,
                venue=venue,
                order_type=order.order_type,
                side=order.direction,
                outcome_status=order.status,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                fill_ratio=fill_ratio,
                intended_price=intended_price,
                realized_price=realized_price,
                expected_slippage_bps=expected_slippage_bps,
                realized_slippage_bps=realized_slippage_bps,
                expected_spread_bps=expected_spread_bps,
                spread_cost=spread_cost,
                notional=notional,
                time_to_fill_seconds=time_to_fill_seconds,
                aggressiveness=aggressiveness,
                quality_score=quality_score,
                payload={
                    "execution_preview": execution_payload,
                    "fill_count": len(order_fills),
                },
            )
            self.session.add(row)
        else:
            row.symbol = order.symbol
            row.broker_slug = broker_slug
            row.venue = venue
            row.order_type = order.order_type
            row.side = order.direction
            row.outcome_status = order.status
            row.quantity = order.quantity
            row.filled_quantity = order.filled_quantity
            row.fill_ratio = fill_ratio
            row.intended_price = intended_price
            row.realized_price = realized_price
            row.expected_slippage_bps = expected_slippage_bps
            row.realized_slippage_bps = realized_slippage_bps
            row.expected_spread_bps = expected_spread_bps
            row.spread_cost = spread_cost
            row.notional = notional
            row.time_to_fill_seconds = time_to_fill_seconds
            row.aggressiveness = aggressiveness
            row.quality_score = quality_score
            row.payload = {
                **(row.payload or {}),
                "execution_preview": execution_payload,
                "fill_count": len(order_fills),
            }

        return row

    def feedback_for_symbol(self, symbol: str) -> ExecutionFeedback:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return ExecutionFeedback(
                symbol=symbol,
                sample_count=0,
                avg_slippage_bps=0.0,
                avg_time_to_fill_seconds=0.0,
                reject_rate=0.0,
                cancel_rate=0.0,
                quality_score=1.0,
                size_scale=1.0,
                block_new_entries=False,
                notes=[],
            )

        rows = self._load_recent_rows(symbol=normalized_symbol)
        if not rows:
            return ExecutionFeedback(
                symbol=normalized_symbol,
                sample_count=0,
                avg_slippage_bps=0.0,
                avg_time_to_fill_seconds=0.0,
                reject_rate=0.0,
                cancel_rate=0.0,
                quality_score=1.0,
                size_scale=1.0,
                block_new_entries=False,
                notes=[],
            )

        filled_rows = [row for row in rows if row.outcome_status == OrderStatus.FILLED]
        avg_slippage_bps = _average([
            abs(row.realized_slippage_bps)
            for row in filled_rows
            if row.realized_slippage_bps is not None
        ])
        avg_time_to_fill_seconds = _average([
            row.time_to_fill_seconds
            for row in filled_rows
            if row.time_to_fill_seconds is not None
        ])
        reject_rate = _ratio(sum(1 for row in rows if row.outcome_status == OrderStatus.REJECTED), len(rows))
        cancel_rate = _ratio(sum(1 for row in rows if row.outcome_status == OrderStatus.CANCELED), len(rows))
        avg_quality_score = _average([row.quality_score for row in rows])

        quality_score = avg_quality_score
        quality_score -= min(max(avg_slippage_bps - 20.0, 0.0) / 120.0, 0.25)
        quality_score -= min(reject_rate * 0.35, 0.35)
        quality_score -= min(cancel_rate * 0.22, 0.22)
        quality_score = max(min(quality_score, 1.0), 0.0)

        sample_count = len(rows)
        size_scale = 1.0
        if sample_count >= self.policy.feedback_min_samples:
            if quality_score >= 0.72 and reject_rate < 0.2:
                size_scale = 1.0
            elif quality_score >= 0.55:
                size_scale = 0.85
            elif quality_score >= 0.4:
                size_scale = 0.65
            else:
                size_scale = self.policy.feedback_size_floor

        block_new_entries = False
        if sample_count >= self.policy.feedback_min_samples and (
            quality_score < self.policy.feedback_block_score or reject_rate >= self.policy.feedback_block_reject_rate
        ):
            block_new_entries = True
            size_scale = 0.0

        notes: list[str] = []
        if sample_count >= self.policy.feedback_min_samples and size_scale < 1.0 and not block_new_entries:
            notes.append(
                (
                    "Execution-quality feedback reduced risk size because recent fills show degraded quality "
                    f"(score={round(quality_score, 3)})."
                )
            )
        if block_new_entries:
            notes.append(
                (
                    "Execution-quality feedback blocked new entries for this symbol due to persistently poor "
                    f"outcomes (score={round(quality_score, 3)}, reject_rate={round(reject_rate * 100, 2)}%)."
                )
            )

        return ExecutionFeedback(
            symbol=normalized_symbol,
            sample_count=sample_count,
            avg_slippage_bps=avg_slippage_bps,
            avg_time_to_fill_seconds=avg_time_to_fill_seconds,
            reject_rate=reject_rate,
            cancel_rate=cancel_rate,
            quality_score=quality_score,
            size_scale=size_scale,
            block_new_entries=block_new_entries,
            notes=notes,
        )

    def summarize(self, *, dimension: str, limit: int = 20) -> list[dict[str, Any]]:
        key_extractors = {
            "symbol": lambda row: row.symbol,
            "venue": lambda row: row.venue,
            "broker": lambda row: row.broker_slug.value,
            "order_type": lambda row: row.order_type.value,
        }
        extractor = key_extractors.get(dimension)
        if extractor is None:
            raise ValueError("Unsupported summary dimension.")

        rows = self._load_recent_rows(symbol=None)
        grouped: dict[str, list[ExecutionQualitySample]] = {}
        for row in rows:
            key = str(extractor(row) or "unknown")
            grouped.setdefault(key, []).append(row)

        summaries: list[dict[str, Any]] = []
        for key, bucket in grouped.items():
            filled = [row for row in bucket if row.outcome_status == OrderStatus.FILLED]
            sample_count = len(bucket)
            filled_count = len(filled)
            reject_rate = _ratio(sum(1 for row in bucket if row.outcome_status == OrderStatus.REJECTED), sample_count)
            cancel_rate = _ratio(sum(1 for row in bucket if row.outcome_status == OrderStatus.CANCELED), sample_count)
            summaries.append(
                {
                    "dimension": dimension,
                    "key": key,
                    "sample_count": sample_count,
                    "filled_count": filled_count,
                    "cancel_rate": cancel_rate,
                    "reject_rate": reject_rate,
                    "avg_expected_slippage_bps": _average(
                        [row.expected_slippage_bps for row in filled if row.expected_slippage_bps is not None]
                    ),
                    "avg_realized_slippage_bps": _average(
                        [abs(row.realized_slippage_bps) for row in filled if row.realized_slippage_bps is not None]
                    ),
                    "avg_spread_cost": _average([row.spread_cost for row in filled]),
                    "avg_time_to_fill_seconds": _average(
                        [row.time_to_fill_seconds for row in filled if row.time_to_fill_seconds is not None]
                    ),
                    "avg_fill_ratio": _average([row.fill_ratio for row in bucket]),
                    "avg_quality_score": _average([row.quality_score for row in bucket]),
                }
            )

        summaries.sort(key=lambda item: (item["sample_count"], item["avg_quality_score"]), reverse=True)
        return summaries[: max(limit, 1)]

    def _load_recent_rows(self, *, symbol: str | None) -> list[ExecutionQualitySample]:
        window_start = datetime.now(UTC) - timedelta(hours=max(self.policy.feedback_lookback_hours, 1))
        query = select(ExecutionQualitySample).where(ExecutionQualitySample.created_at >= window_start)
        if symbol:
            query = query.where(ExecutionQualitySample.symbol == symbol)
        return self.session.scalars(query.order_by(ExecutionQualitySample.created_at.desc()).limit(2000)).all()

    def _reference_price(self, intended_price: float, liquidity_snapshot: LiquiditySnapshot | None) -> float:
        if intended_price > 0:
            return float(intended_price)
        if liquidity_snapshot is None:
            return 0.0
        if liquidity_snapshot.mid_price is not None and liquidity_snapshot.mid_price > 0:
            return float(liquidity_snapshot.mid_price)
        if liquidity_snapshot.last_price is not None and liquidity_snapshot.last_price > 0:
            return float(liquidity_snapshot.last_price)
        return 0.0

    def _estimate_spread_bps(
        self,
        liquidity_snapshot: LiquiditySnapshot | None,
        feature_snapshot: dict[str, float],
    ) -> float:
        if liquidity_snapshot is not None and liquidity_snapshot.spread_bps is not None:
            return max(liquidity_snapshot.spread_bps, 0.0)

        volatility_pct = _optional_float(feature_snapshot.get("intraday_volatility_pct"), fallback=1.0) or 1.0
        relative_volume = _optional_float(feature_snapshot.get("relative_volume_10"), fallback=1.0) or 1.0
        inferred = 8.0
        inferred += max(volatility_pct - 1.0, 0.0) * 5.0
        inferred += max(1.0 - relative_volume, 0.0) * 11.0
        return max(min(inferred, 140.0), 4.0)

    def _estimate_slippage_bps(
        self,
        *,
        spread_bps: float,
        quantity: int,
        liquidity_snapshot: LiquiditySnapshot | None,
        feature_snapshot: dict[str, float],
    ) -> float:
        volatility_pct = _optional_float(feature_snapshot.get("intraday_volatility_pct"), fallback=1.0) or 1.0
        relative_volume = _optional_float(feature_snapshot.get("relative_volume_10"), fallback=1.0) or 1.0
        gap_latest = abs(_optional_float(feature_snapshot.get("gap_latest_pct"), fallback=0.0) or 0.0)

        depth_penalty = 8.0
        if liquidity_snapshot is not None and liquidity_snapshot.quoted_depth > 0:
            depth_ratio = quantity / max(liquidity_snapshot.quoted_depth, 1.0)
            depth_penalty = 0.0
            if depth_ratio > 0.25:
                depth_penalty += min((depth_ratio - 0.25) * 35.0, 45.0)

        expected = 2.5
        expected += spread_bps * 0.55
        expected += max(volatility_pct - 1.0, 0.0) * 3.2
        expected += max(gap_latest - 0.3, 0.0) * 1.5
        expected += max(1.0 - relative_volume, 0.0) * 14.0
        expected += depth_penalty
        return max(min(expected, 250.0), 1.0)

    def _liquidity_score(
        self,
        *,
        spread_bps: float,
        quantity: int,
        liquidity_snapshot: LiquiditySnapshot | None,
        feature_snapshot: dict[str, float],
    ) -> float:
        volatility_pct = _optional_float(feature_snapshot.get("intraday_volatility_pct"), fallback=1.0) or 1.0
        relative_volume = _optional_float(feature_snapshot.get("relative_volume_10"), fallback=1.0) or 1.0

        score = 1.0
        score -= min(spread_bps / 120.0, 0.55)
        score -= min(volatility_pct / 15.0, 0.2)
        score -= min(max(1.0 - relative_volume, 0.0) * 0.35, 0.25)

        if liquidity_snapshot is None or liquidity_snapshot.quoted_depth <= 0:
            score -= 0.15
        else:
            score -= min((quantity / max(liquidity_snapshot.quoted_depth, 1.0)) * 0.6, 0.35)

        if relative_volume > 1.25:
            score += 0.05
        return max(min(score, 1.0), 0.0)

    def _execution_plan(
        self,
        *,
        side: OrderIntent,
        reference_price: float,
        expected_spread_bps: float,
        liquidity_score: float,
    ) -> tuple[str, OrderType, TimeInForce, float | None]:
        if liquidity_score >= 0.78 and expected_spread_bps <= 12:
            return "aggressive", OrderType.BRACKET, TimeInForce.DAY, None
        if liquidity_score >= 0.5 and expected_spread_bps <= 28:
            return "balanced", OrderType.BRACKET, TimeInForce.DAY, round(reference_price, 4)

        passive_bps = min(max(expected_spread_bps * 0.2, 2.0), 10.0)
        adjustment = reference_price * (passive_bps / 10_000)
        if side == OrderIntent.BUY:
            limit_price = max(reference_price - adjustment, 0.01)
        else:
            limit_price = reference_price + adjustment
        return "passive", OrderType.BRACKET, TimeInForce.GTC, round(limit_price, 4)


def _execution_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    payload = metadata.get("execution_quality") if isinstance(metadata, dict) else None
    if isinstance(payload, dict):
        return payload
    return {}


def _decision_entry(metadata: dict[str, Any]) -> float | None:
    if not isinstance(metadata, dict):
        return None
    decision = metadata.get("decision")
    if isinstance(decision, dict):
        return _optional_float(decision.get("entry"))
    return _optional_float(metadata.get("entry"))


def _broker_slug_from_payload(raw: Any, fallback: BrokerSlug) -> BrokerSlug:
    if isinstance(raw, str):
        try:
            return BrokerSlug(raw)
        except ValueError:
            return fallback
    return fallback


def _realized_slippage_bps(
    side: OrderIntent,
    intended_price: float | None,
    realized_price: float | None,
) -> float | None:
    if intended_price is None or realized_price is None or intended_price <= 0:
        return None
    if side == OrderIntent.BUY:
        return ((realized_price - intended_price) / intended_price) * 10_000
    if side == OrderIntent.SELL:
        return ((intended_price - realized_price) / intended_price) * 10_000
    return None


def _spread_cost(expected_spread_bps: float | None, price: float, quantity: int) -> float:
    if expected_spread_bps is None or price <= 0 or quantity <= 0:
        return 0.0
    return price * quantity * (expected_spread_bps / 10_000)


def _time_to_fill_seconds(order: OrderRecord, fills: list[OrderFill]) -> float | None:
    if not fills or order.submitted_at is None:
        return None
    latest_fill = max(fills, key=lambda row: row.filled_at)
    delta = latest_fill.filled_at - order.submitted_at
    return max(delta.total_seconds(), 0.0)


def _outcome_quality_score(
    *,
    base_score: float,
    status: OrderStatus,
    realized_slippage_bps: float | None,
    expected_slippage_bps: float | None,
    fill_ratio: float,
    time_to_fill_seconds: float | None,
) -> float:
    score = max(min(base_score, 1.0), 0.0)
    if status == OrderStatus.REJECTED:
        score *= 0.1
    elif status == OrderStatus.CANCELED:
        score *= 0.3
    elif status == OrderStatus.EXPIRED:
        score *= 0.35

    if realized_slippage_bps is not None and expected_slippage_bps is not None and expected_slippage_bps > 0:
        slippage_ratio = realized_slippage_bps / expected_slippage_bps
        if slippage_ratio > 1.0:
            score -= min((slippage_ratio - 1.0) * 0.25, 0.3)
    elif realized_slippage_bps is not None:
        score -= min(max(realized_slippage_bps, 0.0) / 200.0, 0.25)

    score *= max(min(fill_ratio, 1.0), 0.1)

    if time_to_fill_seconds is not None and time_to_fill_seconds > 0:
        score -= min(time_to_fill_seconds / 3600.0, 0.2)

    return max(min(score, 1.0), 0.0)


def _optional_float(value: Any, fallback: float | None = None) -> float | None:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _average(values: list[float | None]) -> float:
    numbers = [float(item) for item in values if item is not None]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator
