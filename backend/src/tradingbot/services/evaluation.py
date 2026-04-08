from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import OrderIntent, OrderStatus
from tradingbot.models import AgentRun, ExecutionIntent, OrderRecord, RiskEvent, TradeReview


class TradeReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def queue_review_for_exit_order(self, order: OrderRecord) -> TradeReview | None:
        if order.direction != OrderIntent.SELL or order.status != OrderStatus.FILLED:
            return None

        existing = self.session.scalar(select(TradeReview).where(TradeReview.order_id == order.id))
        if existing is not None:
            return existing

        parent = self.session.get(OrderRecord, order.parent_order_id) if order.parent_order_id else None
        if parent is None:
            return None

        quantity = max(min(parent.filled_quantity or parent.quantity, order.filled_quantity or order.quantity), 0)
        entry_price = parent.average_fill_price or parent.limit_price or _decision_entry(parent.metadata_json)
        exit_price = order.average_fill_price or order.limit_price or order.stop_price
        if quantity <= 0 or entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0:
            return None

        pnl = (exit_price - entry_price) * quantity
        return_pct = pnl / max(entry_price * quantity, 1e-6)
        decision_payload = _decision_payload(parent)
        source_run_id, model_name, prompt_versions = self._run_metadata(parent)
        loss_cause = self._classify_loss_cause(
            order=order,
            decision_payload=decision_payload,
            pnl=pnl,
            entry_price=entry_price,
            exit_price=exit_price,
        )
        review_score = round(max(min(return_pct * 10, 1.0), -1.0), 4)
        status = "queued" if pnl < 0 else "completed"
        summary = self._review_summary(
            symbol=order.symbol,
            pnl=pnl,
            return_pct=return_pct,
            loss_cause=loss_cause,
            thesis=str(decision_payload.get("thesis") or "No thesis recorded."),
        )

        review = TradeReview(
            source_run_id=source_run_id,
            order_id=order.id,
            symbol=order.symbol,
            status=status,
            model_name=model_name,
            prompt_versions_json=prompt_versions,
            review_score=review_score,
            pnl=round(pnl, 6),
            return_pct=round(return_pct * 100, 6),
            loss_cause=loss_cause,
            summary=summary,
            recurring_pattern_key=loss_cause if loss_cause else "validated_thesis",
            review_payload={
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "quantity": quantity,
                "thesis": decision_payload.get("thesis"),
                "risk_notes": decision_payload.get("risk_notes", []),
                "feature_snapshot": decision_payload.get("feature_snapshot", {}),
                "structured_events": decision_payload.get("structured_events", []),
                "committee_notes": decision_payload.get("committee_notes", []),
            },
            reviewed_at=None if status == "queued" else datetime.now(UTC),
        )
        self.session.add(review)
        self.session.flush()

        if status == "queued":
            self._flag_recurring_pattern(review)

        return review

    def summarize_model_performance(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.session.scalars(
            select(TradeReview).order_by(TradeReview.created_at.desc()).limit(limit)
        ).all()
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            model_name = row.model_name or "unknown"
            prompt_signature = _prompt_signature(row.prompt_versions_json or {})
            bucket = grouped.setdefault(
                (model_name, prompt_signature),
                {
                    "model_name": model_name,
                    "prompt_signature": prompt_signature,
                    "reviewed_trades": 0,
                    "queued_reviews": 0,
                    "score_total": 0.0,
                    "return_total": 0.0,
                    "loss_causes": {},
                },
            )
            bucket["reviewed_trades"] += 1
            bucket["queued_reviews"] += int(row.status == "queued")
            bucket["score_total"] += row.review_score
            bucket["return_total"] += row.return_pct
            if row.loss_cause:
                bucket["loss_causes"][row.loss_cause] = bucket["loss_causes"].get(row.loss_cause, 0) + 1

        summaries: list[dict[str, Any]] = []
        for bucket in grouped.values():
            reviewed = max(bucket["reviewed_trades"], 1)
            summaries.append(
                {
                    "model_name": bucket["model_name"],
                    "prompt_signature": bucket["prompt_signature"],
                    "reviewed_trades": bucket["reviewed_trades"],
                    "queued_reviews": bucket["queued_reviews"],
                    "avg_score": round(bucket["score_total"] / reviewed, 4),
                    "avg_return_pct": round(bucket["return_total"] / reviewed, 6),
                    "loss_causes": bucket["loss_causes"],
                }
            )
        return sorted(summaries, key=lambda item: (item["avg_score"], item["reviewed_trades"]), reverse=True)

    def _run_metadata(self, parent: OrderRecord) -> tuple[str | None, str | None, dict[str, str]]:
        execution_intent_id = parent.execution_intent_id
        if not execution_intent_id:
            return None, None, {}
        intent = self.session.get(ExecutionIntent, execution_intent_id)
        if intent is None or not intent.source_run_id:
            return None, None, {}
        run = self.session.get(AgentRun, intent.source_run_id)
        if run is None:
            return intent.source_run_id, None, {}
        return run.id, run.model_name, dict(run.prompt_versions_json or {})

    def _classify_loss_cause(
        self,
        *,
        order: OrderRecord,
        decision_payload: dict[str, Any],
        pnl: float,
        entry_price: float,
        exit_price: float,
    ) -> str | None:
        if pnl >= 0:
            return None

        intended_exit = order.limit_price or order.stop_price
        if intended_exit is not None:
            slippage_pct = abs(exit_price - intended_exit) / max(intended_exit, 1e-6)
            if slippage_pct >= 0.003:
                return "bad_execution"

        structured_events = decision_payload.get("structured_events", [])
        if any(item.get("significance") == "high" for item in structured_events if isinstance(item, dict)):
            return "bad_context"

        risk_notes = [str(item).lower() for item in decision_payload.get("risk_notes", [])]
        committee_notes = [str(item).lower() for item in decision_payload.get("committee_notes", [])]
        if any("gap" in note or "risk" in note or "cooldown" in note for note in risk_notes + committee_notes):
            return "avoidable_risk"

        move_pct = (exit_price - entry_price) / max(entry_price, 1e-6)
        if move_pct <= -0.004:
            return "bad_signal"
        return "bad_context"

    def _review_summary(
        self,
        *,
        symbol: str,
        pnl: float,
        return_pct: float,
        loss_cause: str | None,
        thesis: str,
    ) -> str:
        if pnl >= 0:
            return (
                f"Trade thesis for {symbol} was validated with realized PnL {round(pnl, 2)} "
                f"and return {round(return_pct * 100, 3)}%."
            )
        return (
            f"Trade thesis for {symbol} underperformed with realized PnL {round(pnl, 2)} "
            f"and return {round(return_pct * 100, 3)}%. "
            f"Classified cause: {loss_cause or 'unclassified'}. Thesis: {thesis}"
        )

    def _flag_recurring_pattern(self, review: TradeReview) -> None:
        if not review.recurring_pattern_key:
            return
        prior_count = self.session.scalar(
            select(func.count())
            .select_from(TradeReview)
            .where(TradeReview.recurring_pattern_key == review.recurring_pattern_key)
            .where(TradeReview.status == "queued")
        )
        if (prior_count or 0) < 3:
            return
        self.session.add(
            RiskEvent(
                symbol=review.symbol,
                severity="warning",
                code="trade_review_pattern",
                message="Recurring post-trade review pattern detected.",
                payload={
                    "symbol": review.symbol,
                    "pattern": review.recurring_pattern_key,
                    "queued_reviews": int(prior_count or 0),
                    "model_name": review.model_name,
                },
            )
        )


def _decision_payload(parent: OrderRecord) -> dict[str, Any]:
    payload = parent.metadata_json or {}
    decision = payload.get("decision")
    return decision if isinstance(decision, dict) else payload


def _decision_entry(payload: dict[str, Any]) -> float | None:
    decision = payload.get("decision")
    if isinstance(decision, dict):
        entry = decision.get("entry")
        if entry is None:
            return None
        try:
            return float(entry)
        except (TypeError, ValueError):
            return None
    entry = payload.get("entry")
    if entry is None:
        return None
    try:
        return float(entry)
    except (TypeError, ValueError):
        return None


def _prompt_signature(prompt_versions: dict[str, str]) -> str:
    if not prompt_versions:
        return "none"
    return json.dumps(prompt_versions, sort_keys=True)
