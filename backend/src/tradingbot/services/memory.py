from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.models import (
    AgentMemory,
    ExecutionQualitySample,
    RiskEvent,
    SymbolCooldown,
    TradeCandidate,
    TradeReview,
)
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult

_MEMORY_LIMIT = 6
_RECENT_LIMIT = 20
_HIGH_SLIPPAGE_BPS = 35.0
_LOW_QUALITY_SCORE = 0.45


class TradingMemoryService:
    """Persist and retrieve compact trading memories for future committee scans.

    This intentionally stays framework-light: the committee orchestration is still direct, while
    this service provides durable profile/symbol memory for decisions, post-trade lessons, and risk
    or execution-quality patterns.
    """

    def __init__(self, session: Session, *, profile_id: int) -> None:
        self.session = session
        self.profile_id = profile_id

    def build_context(self, symbol: str, *, as_of: datetime | None = None, limit: int = _MEMORY_LIMIT) -> dict[str, Any]:
        normalized_symbol = _normalize_symbol(symbol)
        self.refresh_symbol_memory(normalized_symbol, as_of=as_of or datetime.now(UTC))
        rows = self.session.scalars(
            select(AgentMemory)
            .where(AgentMemory.profile_id == self.profile_id)
            .where(AgentMemory.symbol == normalized_symbol)
            .where((AgentMemory.expires_at.is_(None)) | (AgentMemory.expires_at > (as_of or datetime.now(UTC))))
            .order_by(AgentMemory.memory_type.asc(), AgentMemory.score.desc(), AgentMemory.last_seen_at.desc())
            .limit(max(limit * 3, 1))
        ).all()
        grouped: dict[str, list[dict[str, Any]]] = {
            "decision_memory": [],
            "post_trade_lessons": [],
            "risk_memory": [],
        }
        risk_notes: list[str] = []
        execution_quality: list[dict[str, Any]] = []
        for row in rows:
            item = _memory_payload(row)
            if row.memory_type == "decision":
                grouped["decision_memory"].append(item)
            elif row.memory_type == "post_trade":
                grouped["post_trade_lessons"].append(item)
            elif row.memory_type == "risk":
                grouped["risk_memory"].append(item)
                risk_notes.append(row.summary)
                if row.memory_key == "execution_quality":
                    execution_quality.append(item)
        return {
            "symbol": normalized_symbol,
            "profile_id": self.profile_id,
            "decision_memory": grouped["decision_memory"][:limit],
            "post_trade_lessons": grouped["post_trade_lessons"][:limit],
            "risk_memory": grouped["risk_memory"][:limit],
            "risk_notes": risk_notes[:limit],
            "execution_quality": execution_quality[:limit],
            "as_of": (as_of or datetime.now(UTC)).isoformat(),
        }

    def remember_decision(
        self,
        *,
        decision: CommitteeDecision,
        risk_result: RiskCheckResult | None = None,
        run_id: str | None = None,
        as_of: datetime | None = None,
    ) -> AgentMemory:
        symbol = _normalize_symbol(decision.symbol)
        notes = list(decision.risk_notes or [])
        if risk_result is not None:
            notes.extend(risk_result.notes)
        risk_text = _compact_list(notes, max_items=3)
        key = f"{decision.status.value}:{decision.direction.value}"
        summary = (
            f"Last {symbol} decision was {decision.status.value}/{decision.direction.value} "
            f"with confidence {round(decision.confidence, 3)}. Thesis: {_truncate(decision.thesis, 180)}"
        )
        if risk_text:
            summary = f"{summary} Risk notes: {risk_text}"
        return self._upsert(
            symbol=symbol,
            memory_type="decision",
            memory_key=key,
            summary=summary,
            score=max(min(decision.confidence, 1.0), 0.0),
            source="committee_decision",
            payload={
                "run_id": run_id,
                "status": decision.status.value,
                "direction": decision.direction.value,
                "confidence": decision.confidence,
                "entry": decision.entry,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "reject_reason": decision.reject_reason,
                "risk_notes": notes,
            },
            as_of=as_of,
        )

    def remember_trade_review(self, review: TradeReview, *, as_of: datetime | None = None) -> AgentMemory:
        symbol = _normalize_symbol(review.symbol)
        key = review.recurring_pattern_key or review.loss_cause or "trade_review"
        score = _severity_score(review.review_score, invert=True)
        lesson = review.summary
        if review.loss_cause:
            lesson = f"{review.loss_cause}: {lesson}"
        return self._upsert(
            symbol=symbol,
            memory_type="post_trade",
            memory_key=key,
            summary=_truncate(lesson, 320),
            score=score,
            source="trade_review",
            payload={
                "review_id": review.id,
                "status": review.status,
                "pnl": review.pnl,
                "return_pct": review.return_pct,
                "loss_cause": review.loss_cause,
                "review_score": review.review_score,
                "review_payload": review.review_payload,
            },
            as_of=as_of,
        )

    def refresh_symbol_memory(self, symbol: str, *, as_of: datetime | None = None) -> None:
        normalized_symbol = _normalize_symbol(symbol)
        now = as_of or datetime.now(UTC)
        self._refresh_decision_rollup(normalized_symbol, as_of=now)
        self._refresh_post_trade_rollups(normalized_symbol, as_of=now)
        self._refresh_risk_rollups(normalized_symbol, as_of=now)

    def _refresh_decision_rollup(self, symbol: str, *, as_of: datetime) -> None:
        rows = self.session.scalars(
            select(TradeCandidate)
            .where(TradeCandidate.profile_id == self.profile_id)
            .where(TradeCandidate.symbol == symbol)
            .order_by(TradeCandidate.created_at.desc())
            .limit(12)
        ).all()
        if not rows:
            return
        status_counts = Counter(row.status for row in rows)
        avg_confidence = mean(row.confidence for row in rows)
        latest = rows[0]
        summary = (
            f"Recent {symbol} decisions: {status_counts.get('approved', 0)} approved, "
            f"{status_counts.get('rejected', 0)} rejected across {len(rows)} scans; "
            f"avg confidence {round(avg_confidence, 3)}. Latest {latest.status}/{latest.direction.value}: "
            f"{_truncate(latest.thesis, 160)}"
        )
        self._upsert(
            symbol=symbol,
            memory_type="decision",
            memory_key="recent_decision_rollup",
            summary=summary,
            score=min(max(avg_confidence, 0.1), 1.0),
            source="trade_candidates",
            payload={
                "status_counts": dict(status_counts),
                "sample_count": len(rows),
                "avg_confidence": avg_confidence,
                "latest_candidate_id": latest.id,
            },
            as_of=as_of,
            occurrences=len(rows),
        )

    def _refresh_post_trade_rollups(self, symbol: str, *, as_of: datetime) -> None:
        rows = self.session.scalars(
            select(TradeReview)
            .where(TradeReview.profile_id == self.profile_id)
            .where(TradeReview.symbol == symbol)
            .order_by(TradeReview.created_at.desc())
            .limit(_RECENT_LIMIT)
        ).all()
        if not rows:
            return
        wins = [row for row in rows if row.pnl >= 0]
        losses = [row for row in rows if row.pnl < 0]
        avg_return = mean(row.return_pct for row in rows)
        latest = rows[0]
        self._upsert(
            symbol=symbol,
            memory_type="post_trade",
            memory_key="wins_losses",
            summary=(
                f"Recent {symbol} outcomes: {len(wins)} wins and {len(losses)} losses over {len(rows)} reviews; "
                f"avg return {round(avg_return, 4)}%. Latest lesson: {_truncate(latest.summary, 180)}"
            ),
            score=_severity_score(avg_return / 100.0, invert=True),
            source="trade_reviews",
            payload={"wins": len(wins), "losses": len(losses), "avg_return_pct": avg_return, "latest_review_id": latest.id},
            as_of=as_of,
            occurrences=len(rows),
        )
        for pattern, count in Counter(row.recurring_pattern_key or row.loss_cause or "unclassified" for row in rows).items():
            if count < 2:
                continue
            matching = [row for row in rows if (row.recurring_pattern_key or row.loss_cause or "unclassified") == pattern]
            example = matching[0]
            self._upsert(
                symbol=symbol,
                memory_type="post_trade",
                memory_key=f"pattern:{pattern}",
                summary=(
                    f"Repeated {symbol} post-trade pattern '{pattern}' occurred {count} times recently. "
                    f"Example lesson: {_truncate(example.summary, 220)}"
                ),
                score=min(1.0, 0.45 + count * 0.12),
                source="trade_reviews",
                payload={"pattern": pattern, "count": count, "example_review_id": example.id},
                as_of=as_of,
                occurrences=count,
            )

    def _refresh_risk_rollups(self, symbol: str, *, as_of: datetime) -> None:
        risk_events = self.session.scalars(
            select(RiskEvent)
            .where(RiskEvent.profile_id == self.profile_id)
            .where(RiskEvent.symbol == symbol)
            .order_by(RiskEvent.created_at.desc())
            .limit(_RECENT_LIMIT)
        ).all()
        if risk_events:
            counts = Counter(event.code for event in risk_events)
            latest = risk_events[0]
            top_codes = ", ".join(f"{code} x{count}" for code, count in counts.most_common(4))
            self._upsert(
                symbol=symbol,
                memory_type="risk",
                memory_key="risk_events",
                summary=f"Recent {symbol} risk events: {top_codes}. Latest: {latest.code} - {_truncate(latest.message, 180)}",
                score=min(1.0, 0.3 + len(risk_events) * 0.04),
                source="risk_events",
                payload={"code_counts": dict(counts), "latest_event_id": latest.id, "latest_payload": latest.payload},
                as_of=as_of,
                occurrences=len(risk_events),
            )

        cooldowns = self.session.scalars(
            select(SymbolCooldown)
            .where(SymbolCooldown.profile_id == self.profile_id)
            .where(SymbolCooldown.symbol == symbol)
            .order_by(SymbolCooldown.triggered_at.desc())
            .limit(5)
        ).all()
        active_cooldowns = [row for row in cooldowns if _as_aware(row.expires_at) > _as_aware(as_of)]
        if cooldowns:
            source_rows = active_cooldowns or cooldowns
            latest = source_rows[0]
            self._upsert(
                symbol=symbol,
                memory_type="risk",
                memory_key="cooldowns",
                summary=(
                    f"{symbol} has {len(active_cooldowns)} active and {len(cooldowns)} recent cooldown records. "
                    f"Latest {latest.cooldown_type}: {_truncate(latest.reason, 180)}"
                ),
                score=0.9 if active_cooldowns else 0.55,
                source="symbol_cooldowns",
                payload={
                    "active_count": len(active_cooldowns),
                    "recent_count": len(cooldowns),
                    "latest_cooldown_type": latest.cooldown_type,
                    "latest_expires_at": latest.expires_at.isoformat(),
                    "latest_context": latest.context_json,
                },
                as_of=as_of,
                occurrences=len(cooldowns),
            )

        quality_samples = self.session.scalars(
            select(ExecutionQualitySample)
            .where(ExecutionQualitySample.profile_id == self.profile_id)
            .where(ExecutionQualitySample.symbol == symbol)
            .order_by(ExecutionQualitySample.created_at.desc())
            .limit(_RECENT_LIMIT)
        ).all()
        if quality_samples:
            slippages = [abs(row.realized_slippage_bps) for row in quality_samples if row.realized_slippage_bps is not None]
            avg_slippage = mean(slippages) if slippages else 0.0
            avg_quality = mean(row.quality_score for row in quality_samples)
            rejected = sum(1 for row in quality_samples if row.outcome_status.value == "rejected")
            if avg_slippage >= _HIGH_SLIPPAGE_BPS or avg_quality <= _LOW_QUALITY_SCORE or rejected:
                self._upsert(
                    symbol=symbol,
                    memory_type="risk",
                    memory_key="execution_quality",
                    summary=(
                        f"Recent {symbol} execution quality: avg slippage {round(avg_slippage, 2)} bps, "
                        f"avg quality {round(avg_quality, 3)}, rejected samples {rejected}/{len(quality_samples)}."
                    ),
                    score=max(min((avg_slippage / 100.0) + (1.0 - avg_quality), 1.0), 0.2),
                    source="execution_quality_samples",
                    payload={
                        "sample_count": len(quality_samples),
                        "avg_abs_slippage_bps": avg_slippage,
                        "avg_quality_score": avg_quality,
                        "rejected_samples": rejected,
                    },
                    as_of=as_of,
                    occurrences=len(quality_samples),
                )

    def _upsert(
        self,
        *,
        symbol: str,
        memory_type: str,
        memory_key: str,
        summary: str,
        score: float,
        source: str,
        payload: dict[str, Any],
        as_of: datetime | None = None,
        occurrences: int | None = None,
    ) -> AgentMemory:
        normalized_symbol = _normalize_symbol(symbol)
        row = self.session.scalar(
            select(AgentMemory)
            .where(AgentMemory.profile_id == self.profile_id)
            .where(AgentMemory.symbol == normalized_symbol)
            .where(AgentMemory.memory_type == memory_type)
            .where(AgentMemory.memory_key == memory_key)
        )
        now = as_of or datetime.now(UTC)
        if row is None:
            row = AgentMemory(
                profile_id=self.profile_id,
                symbol=normalized_symbol,
                memory_type=memory_type,
                memory_key=memory_key,
                summary=summary,
                score=round(max(min(score, 1.0), 0.0), 6),
                occurrences=max(int(occurrences or 1), 1),
                last_seen_at=now,
                source=source,
                payload=payload,
            )
            self.session.add(row)
        else:
            row.summary = summary
            row.score = round(max(min(score, 1.0), 0.0), 6)
            row.occurrences = max(int(occurrences), 1) if occurrences is not None else row.occurrences + 1
            row.last_seen_at = now
            row.source = source
            row.payload = payload
        self.session.flush()
        return row


def _memory_payload(row: AgentMemory) -> dict[str, Any]:
    return {
        "type": row.memory_type,
        "key": row.memory_key,
        "summary": row.summary,
        "score": row.score,
        "occurrences": row.occurrences,
        "last_seen_at": row.last_seen_at.isoformat(),
        "source": row.source,
        "payload": row.payload,
    }


def _normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip()


def _truncate(value: str, max_length: int) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}…"


def _compact_list(values: list[str], *, max_items: int) -> str:
    compacted = [_truncate(value, 100) for value in values if str(value).strip()]
    return "; ".join(compacted[:max_items])


def _severity_score(value: float, *, invert: bool) -> float:
    bounded = max(min(value, 1.0), -1.0)
    if invert:
        return max(min(0.5 - bounded / 2, 1.0), 0.0)
    return max(min(0.5 + bounded / 2, 1.0), 0.0)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
