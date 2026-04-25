from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.models import ExecutionQualitySample, RiskEvent, TradeCandidate, TradeReview


class MarketEfficiencyService:
    def __init__(self, session: Session, *, profile_id: int | None = None) -> None:
        self.session = session
        self.profile_id = profile_id

    def risk_calibration_report(self, *, window_minutes: int = 24 * 60) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(minutes=max(window_minutes, 1))

        candidate_query = select(TradeCandidate).where(TradeCandidate.created_at >= cutoff)
        risk_query = select(RiskEvent).where(RiskEvent.created_at >= cutoff)
        quality_query = select(ExecutionQualitySample).where(ExecutionQualitySample.created_at >= cutoff)
        review_query = select(TradeReview).where(TradeReview.created_at >= cutoff)
        if self.profile_id is not None:
            candidate_query = candidate_query.where(TradeCandidate.profile_id == self.profile_id)
            risk_query = risk_query.where(RiskEvent.profile_id == self.profile_id)
            quality_query = quality_query.where(ExecutionQualitySample.profile_id == self.profile_id)
            review_query = review_query.where(TradeReview.profile_id == self.profile_id)

        candidates = list(self.session.scalars(candidate_query).all())
        risk_events = list(self.session.scalars(risk_query).all())
        quality_samples = list(self.session.scalars(quality_query).all())
        reviews = list(self.session.scalars(review_query).all())

        approved = sum(1 for item in candidates if item.status == "approved")
        rejected = sum(1 for item in candidates if item.status != "approved")
        rejection_codes: dict[str, int] = {}
        for event in risk_events:
            if event.code.startswith("alert_"):
                continue
            rejection_codes[event.code] = rejection_codes.get(event.code, 0) + 1

        avg_quality_score = _average([sample.quality_score for sample in quality_samples])
        avg_slippage = _average(
            [
                abs(sample.realized_slippage_bps)
                for sample in quality_samples
                if sample.realized_slippage_bps is not None
            ]
        )
        queued_reviews = sum(1 for review in reviews if review.status == "queued")
        avg_review_score = _average([review.review_score for review in reviews])

        recommendations: list[str] = []
        if candidates and rejected / max(len(candidates), 1) > 0.5:
            recommendations.append("Review risk thresholds and input quality because more than half of candidates were rejected.")
        if rejection_codes.get("pretrade_rejected", 0):
            recommendations.append("Inspect pre-trade validation rejects before increasing watchlist size or order frequency.")
        if quality_samples and avg_quality_score < 0.65:
            recommendations.append("Reduce size or tighten execution-quality gates for symbols with weak fill quality.")
        if queued_reviews:
            recommendations.append("Resolve queued post-trade reviews before promoting strategy or prompt changes.")
        if not recommendations:
            recommendations.append("Keep current controls and continue collecting paper-trading evidence.")

        return {
            "window_minutes": window_minutes,
            "trade_candidates": len(candidates),
            "approved_candidates": approved,
            "rejected_candidates": rejected,
            "approval_rate": round(approved / max(len(candidates), 1), 6) if candidates else 0.0,
            "rejection_codes": rejection_codes,
            "execution_quality": {
                "sample_count": len(quality_samples),
                "avg_quality_score": round(avg_quality_score, 6),
                "avg_abs_realized_slippage_bps": round(avg_slippage, 6),
            },
            "post_trade_reviews": {
                "review_count": len(reviews),
                "queued_reviews": queued_reviews,
                "avg_review_score": round(avg_review_score, 6),
            },
            "recommendations": recommendations,
        }


def _average(values: list[float | None]) -> float:
    numbers = [float(item) for item in values if item is not None]
    return sum(numbers) / len(numbers) if numbers else 0.0
