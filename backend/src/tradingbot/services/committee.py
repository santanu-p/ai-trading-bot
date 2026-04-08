from __future__ import annotations

from statistics import mean, median

from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import AgentDecision, ChairSummary, CommitteeDecision, RiskCheckResult


class CommitteeService:
    def __init__(self, consensus_threshold: float, min_approval_votes: int) -> None:
        self.consensus_threshold = consensus_threshold
        self.min_approval_votes = min_approval_votes

    def propose(
        self,
        *agent_decisions: AgentDecision,
        chair_summary: ChairSummary | None = None,
    ) -> CommitteeDecision:
        signals = list(agent_decisions)
        if not signals:
            raise ValueError("At least one agent decision is required.")

        symbol = signals[0].symbol
        approval_signals = [
            signal
            for signal in signals
            if signal.direction == OrderIntent.BUY and signal.vote.lower().strip() in {"approve", "buy", "long"}
        ]
        required_votes = max(self.min_approval_votes, max(2, (len(signals) + 1) // 2))
        average_confidence = mean(signal.confidence for signal in signals)
        chair_supports = (
            chair_summary is None
            or (chair_summary.direction == OrderIntent.BUY and chair_summary.vote.lower().strip() in {"approve", "buy", "long"})
        )
        consensus_met = (
            len(approval_signals) >= required_votes
            and average_confidence >= self.consensus_threshold
            and chair_supports
        )

        price_signals = approval_signals or signals
        committee_notes = [
            f"approvals={len(approval_signals)}/{len(signals)}",
            f"required_votes={required_votes}",
            f"average_confidence={round(average_confidence, 3)}",
        ]
        if chair_summary and chair_summary.dissenting_risks:
            committee_notes.extend(chair_summary.dissenting_risks)

        reject_reasons = [signal.reject_reason for signal in signals if signal.reject_reason]
        if chair_summary and chair_summary.vote.lower().strip() not in {"approve", "buy", "long"}:
            reject_reasons.append(chair_summary.summary)
        if not consensus_met and not reject_reasons:
            reject_reasons.append("Consensus threshold not met.")

        return CommitteeDecision(
            symbol=symbol,
            direction=OrderIntent.BUY if consensus_met else OrderIntent.HOLD,
            confidence=round(average_confidence, 3),
            entry=round(float(median([signal.entry for signal in price_signals])), 4),
            stop_loss=round(float(median([signal.stop_loss for signal in price_signals])), 4),
            take_profit=round(float(median([signal.take_profit for signal in price_signals])), 4),
            time_horizon=chair_summary.time_horizon if chair_summary else signals[0].time_horizon,
            status=RiskDecision.APPROVED if consensus_met else RiskDecision.REJECTED,
            thesis=(chair_summary.summary if chair_summary else " | ".join(signal.thesis.strip() for signal in signals)).strip(),
            reject_reason=None if consensus_met else "; ".join(reject_reasons),
            market_vote=_vote_for_role(signals, "technical_structure"),
            news_vote=_vote_for_role(signals, "catalyst"),
            chair_vote=chair_summary.vote if chair_summary else None,
            risk_notes=[],
            committee_notes=committee_notes,
            agent_signals=signals,
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


def _vote_for_role(agent_decisions: list[AgentDecision], role: str) -> str | None:
    for decision in agent_decisions:
        if decision.role == role:
            return decision.vote
    return None
