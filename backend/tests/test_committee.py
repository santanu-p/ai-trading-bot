from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import AgentDecision, RiskCheckResult
from tradingbot.services.committee import CommitteeService


def _agent(role: str, confidence: float) -> AgentDecision:
    return AgentDecision(
        role=role,
        symbol="AAPL",
        direction=OrderIntent.BUY,
        confidence=confidence,
        thesis=f"{role} supports momentum continuation.",
        entry=200,
        stop_loss=197,
        take_profit=206,
        time_horizon="intraday",
        vote="approve",
    )


def test_committee_proposal_requires_consensus_threshold() -> None:
    committee = CommitteeService(consensus_threshold=0.7, min_approval_votes=2)
    proposal = committee.propose(_agent("market", 0.62), _agent("news", 0.6))
    assert proposal.status == RiskDecision.REJECTED
    assert proposal.direction == OrderIntent.HOLD


def test_committee_finalize_carries_risk_rejection_notes() -> None:
    committee = CommitteeService(consensus_threshold=0.6, min_approval_votes=2)
    proposal = committee.propose(_agent("market", 0.76), _agent("news", 0.72))
    result = committee.finalize(
        proposal,
        risk_result=RiskCheckResult(decision=RiskDecision.REJECTED, notes=["Buying power exhausted."]),
    )
    assert result.status == RiskDecision.REJECTED
    assert result.reject_reason == "Buying power exhausted."

