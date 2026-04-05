from __future__ import annotations

from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import AgentDecision, CommitteeDecision, RiskCheckResult


class CommitteeService:
    def __init__(self, consensus_threshold: float, min_approval_votes: int) -> None:
        self.consensus_threshold = consensus_threshold
        self.min_approval_votes = min_approval_votes

    def propose(self, market_decision: AgentDecision, news_decision: AgentDecision) -> CommitteeDecision:
        directions = [market_decision.direction, news_decision.direction]
        buy_votes = sum(direction == OrderIntent.BUY for direction in directions)
        average_confidence = (market_decision.confidence + news_decision.confidence) / 2
        consensus_met = buy_votes >= self.min_approval_votes and average_confidence >= self.consensus_threshold

        return CommitteeDecision(
            symbol=market_decision.symbol,
            direction=OrderIntent.BUY if consensus_met else OrderIntent.HOLD,
            confidence=round(average_confidence, 3),
            entry=max(market_decision.entry, news_decision.entry),
            stop_loss=min(market_decision.stop_loss, news_decision.stop_loss),
            take_profit=max(market_decision.take_profit, news_decision.take_profit),
            time_horizon="intraday",
            status=RiskDecision.APPROVED if consensus_met else RiskDecision.REJECTED,
            thesis=" | ".join([market_decision.thesis.strip(), news_decision.thesis.strip()]),
            reject_reason=None if consensus_met else "Consensus threshold not met.",
            market_vote=market_decision.vote,
            news_vote=news_decision.vote,
            risk_notes=[],
        )

    def finalize(
        self,
        proposal: CommitteeDecision,
        *,
        risk_result: RiskCheckResult,
    ) -> CommitteeDecision:
        return proposal.model_copy(
            update={
                "status": risk_result.decision,
                "direction": proposal.direction if risk_result.decision == RiskDecision.APPROVED else OrderIntent.HOLD,
                "reject_reason": None if risk_result.decision == RiskDecision.APPROVED else "; ".join(risk_result.notes),
                "risk_notes": risk_result.notes,
            }
        )

