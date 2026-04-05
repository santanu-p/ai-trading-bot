from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import CommitteeDecision
from tradingbot.services.risk import RiskEngine, RiskPolicy


def _approved_decision() -> CommitteeDecision:
    return CommitteeDecision(
        symbol="MSFT",
        direction=OrderIntent.BUY,
        confidence=0.81,
        entry=410,
        stop_loss=405,
        take_profit=420,
        time_horizon="intraday",
        status=RiskDecision.APPROVED,
        thesis="Momentum confirmed and news catalyst is clean.",
        risk_notes=[],
    )


def test_risk_engine_rejects_when_daily_loss_breached() -> None:
    engine = RiskEngine(
        RiskPolicy(
            max_open_positions=5,
            max_daily_loss_pct=0.02,
            max_position_risk_pct=0.005,
            max_symbol_notional_pct=0.15,
            symbol_cooldown_minutes=45,
        )
    )
    result = engine.validate(
        _approved_decision(),
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        daily_loss_pct=0.025,
        active_symbol_exposure=0,
        is_symbol_in_cooldown=False,
    )
    assert result.decision == RiskDecision.REJECTED
    assert "Daily loss limit breached." in result.notes


def test_risk_engine_sizes_position_from_stop_distance() -> None:
    engine = RiskEngine(
        RiskPolicy(
            max_open_positions=5,
            max_daily_loss_pct=0.02,
            max_position_risk_pct=0.005,
            max_symbol_notional_pct=0.15,
            symbol_cooldown_minutes=45,
        )
    )
    result = engine.validate(
        _approved_decision(),
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        daily_loss_pct=0.0,
        active_symbol_exposure=0,
        is_symbol_in_cooldown=False,
    )
    assert result.decision == RiskDecision.APPROVED
    assert result.approved_quantity == 100

