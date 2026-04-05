from __future__ import annotations

from dataclasses import dataclass

from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult


@dataclass(slots=True)
class RiskPolicy:
    max_open_positions: int
    max_daily_loss_pct: float
    max_position_risk_pct: float
    max_symbol_notional_pct: float
    symbol_cooldown_minutes: int


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
    ) -> RiskCheckResult:
        notes: list[str] = []

        if decision.direction != OrderIntent.BUY:
            return RiskCheckResult(decision=RiskDecision.REJECTED, notes=["Only long entries are enabled in v1."])

        if decision.status != RiskDecision.APPROVED:
            return RiskCheckResult(
                decision=RiskDecision.REJECTED,
                notes=[decision.reject_reason or "Committee rejected the trade."],
            )

        if is_symbol_in_cooldown:
            notes.append("Symbol is in cooldown after a recent order.")
        if open_positions >= self.policy.max_open_positions:
            notes.append("Maximum open positions reached.")
        if daily_loss_pct >= self.policy.max_daily_loss_pct:
            notes.append("Daily loss limit breached.")

        stop_distance = max(decision.entry - decision.stop_loss, 0)
        if stop_distance <= 0:
            notes.append("Stop loss must be below entry for long trades.")

        per_trade_risk_budget = equity * self.policy.max_position_risk_pct
        approved_quantity = int(per_trade_risk_budget // max(stop_distance, 0.01))
        notional = approved_quantity * decision.entry

        if approved_quantity <= 0:
            notes.append("Risk budget does not allow any shares.")
        if notional > buying_power:
            notes.append("Insufficient buying power.")
        if notional > equity * self.policy.max_symbol_notional_pct:
            notes.append("Trade exceeds single-symbol notional cap.")
        if active_symbol_exposure + notional > equity * self.policy.max_symbol_notional_pct:
            notes.append("Existing exposure to this symbol is already at the cap.")

        if notes:
            return RiskCheckResult(decision=RiskDecision.REJECTED, notes=notes)

        return RiskCheckResult(
            decision=RiskDecision.APPROVED,
            approved_quantity=approved_quantity,
            notes=["Risk checks passed."],
        )

