"""Monte Carlo simulation and stress testing for backtest equity curves.

Provides:
- Monte Carlo simulation with configurable parameters
- Tail risk estimation (VaR, CVaR at configurable confidence levels)
- Historical stress scenario replay
- Adverse fill model (worst-case slippage scenarios)
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import mean, median, pstdev, quantiles
from typing import Any

from tradingbot.services.metrics import observe_counter, observe_duration_ms

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class EquityCurvePoint:
    """A single point on an equity curve."""

    timestamp: datetime
    equity: float
    pnl: float = 0.0
    drawdown_pct: float = 0.0


@dataclass(slots=True)
class MonteCarloResult:
    """Results of a Monte Carlo simulation."""

    n_simulations: int
    n_trades: int
    median_final_equity: float
    mean_final_equity: float
    p5_final_equity: float
    p10_final_equity: float
    p25_final_equity: float
    p75_final_equity: float
    p90_final_equity: float
    p95_final_equity: float
    var_95: float  # 95% Value at Risk (worst-case equity at 5th percentile)
    cvar_95: float  # Conditional VaR (expected equity below VaR)
    var_99: float
    cvar_99: float
    max_drawdown_median: float
    max_drawdown_p95: float
    probability_of_loss: float
    probability_of_ruin: float  # probability of losing > 50% of capital
    sharpe_ratio_median: float
    raw_simulations: list[list[float]] = field(default_factory=list)  # equity curves
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict[str, Any]:
        return {
            "n_simulations": self.n_simulations,
            "n_trades": self.n_trades,
            "median_final_equity": round(self.median_final_equity, 2),
            "mean_final_equity": round(self.mean_final_equity, 2),
            "percentiles": {
                "p5": round(self.p5_final_equity, 2),
                "p10": round(self.p10_final_equity, 2),
                "p25": round(self.p25_final_equity, 2),
                "p75": round(self.p75_final_equity, 2),
                "p90": round(self.p90_final_equity, 2),
                "p95": round(self.p95_final_equity, 2),
            },
            "risk_metrics": {
                "var_95": round(self.var_95, 2),
                "cvar_95": round(self.cvar_95, 2),
                "var_99": round(self.var_99, 2),
                "cvar_99": round(self.cvar_99, 2),
                "max_drawdown_median": round(self.max_drawdown_median, 4),
                "max_drawdown_p95": round(self.max_drawdown_p95, 4),
                "probability_of_loss": round(self.probability_of_loss, 4),
                "probability_of_ruin": round(self.probability_of_ruin, 4),
                "sharpe_ratio_median": round(self.sharpe_ratio_median, 4),
            },
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(slots=True)
class StressScenario:
    """Definition of a historical stress scenario."""

    name: str
    description: str
    return_shock_pct: float  # e.g., -5.0 for a 5% market drop
    volatility_multiplier: float  # e.g., 3.0 for 3x normal vol
    spread_multiplier: float  # e.g., 5.0 for 5x normal spreads
    duration_bars: int  # How many bars the stress lasts
    gap_pct: float = 0.0  # Opening gap in percentage


@dataclass(slots=True)
class StressTestResult:
    """Result of applying a stress scenario to a portfolio."""

    scenario: str
    equity_before: float
    equity_after: float
    pnl: float
    pnl_pct: float
    max_drawdown_pct: float
    fill_quality_impact: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "equity_before": round(self.equity_before, 2),
            "equity_after": round(self.equity_after, 2),
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "fill_quality_impact": round(self.fill_quality_impact, 4),
        }


# ---------------------------------------------------------------------------
# Built-in stress scenarios
# ---------------------------------------------------------------------------
STRESS_SCENARIOS: list[StressScenario] = [
    StressScenario(
        name="flash_crash",
        description="Sudden market crash similar to the 2010 Flash Crash",
        return_shock_pct=-8.0,
        volatility_multiplier=5.0,
        spread_multiplier=10.0,
        duration_bars=5,
        gap_pct=-3.0,
    ),
    StressScenario(
        name="circuit_breaker",
        description="Market-wide circuit breaker halt (March 2020 style)",
        return_shock_pct=-7.0,
        volatility_multiplier=4.0,
        spread_multiplier=8.0,
        duration_bars=10,
        gap_pct=-5.0,
    ),
    StressScenario(
        name="gap_down_open",
        description="Large gap-down opening from overnight news",
        return_shock_pct=-3.0,
        volatility_multiplier=2.5,
        spread_multiplier=4.0,
        duration_bars=3,
        gap_pct=-4.0,
    ),
    StressScenario(
        name="liquidity_crisis",
        description="Sudden liquidity withdrawal with extreme spread widening",
        return_shock_pct=-2.0,
        volatility_multiplier=3.0,
        spread_multiplier=15.0,
        duration_bars=8,
    ),
    StressScenario(
        name="volatility_spike",
        description="VIX spike event with sustained elevated volatility",
        return_shock_pct=-1.5,
        volatility_multiplier=4.0,
        spread_multiplier=3.0,
        duration_bars=20,
    ),
    StressScenario(
        name="sector_rotation",
        description="Sharp sector rotation causing portfolio correlation breakdown",
        return_shock_pct=-4.0,
        volatility_multiplier=2.0,
        spread_multiplier=2.0,
        duration_bars=15,
    ),
]


# ---------------------------------------------------------------------------
# Monte Carlo engine
# ---------------------------------------------------------------------------
class MonteCarloEngine:
    """Monte Carlo simulation on backtest equity curves."""

    def __init__(
        self,
        *,
        n_simulations: int = 1000,
        seed: int | None = None,
    ) -> None:
        self.n_simulations = max(n_simulations, 100)
        self._rng = random.Random(seed)

    def simulate(
        self,
        trade_returns: list[float],
        *,
        initial_equity: float = 100_000.0,
        position_size_pct: float = 2.0,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation by resampling trade returns.

        Args:
            trade_returns: List of per-trade return percentages (e.g., [2.5, -1.3, ...])
            initial_equity: Starting equity amount
            position_size_pct: Percentage of equity risked per trade
        """
        if not trade_returns:
            return self._empty_result(initial_equity)

        n_trades = len(trade_returns)
        final_equities: list[float] = []
        max_drawdowns: list[float] = []
        sharpe_ratios: list[float] = []
        all_curves: list[list[float]] = []

        for _ in range(self.n_simulations):
            # Resample trades with replacement
            resampled = [self._rng.choice(trade_returns) for _ in range(n_trades)]
            equity_curve, max_dd = self._simulate_curve(resampled, initial_equity, position_size_pct)
            all_curves.append(equity_curve)
            final_equities.append(equity_curve[-1])
            max_drawdowns.append(max_dd)

            # Compute Sharpe ratio for this simulation
            if len(equity_curve) > 1:
                returns = [(equity_curve[i] - equity_curve[i - 1]) / max(equity_curve[i - 1], 1) for i in range(1, len(equity_curve))]
                if returns and pstdev(returns) > 0:
                    sharpe_ratios.append(mean(returns) / pstdev(returns) * (252 ** 0.5))  # Annualized
                else:
                    sharpe_ratios.append(0.0)

        final_equities.sort()
        max_drawdowns.sort()

        # Percentiles
        n = len(final_equities)
        p5 = final_equities[max(int(n * 0.05) - 1, 0)]
        p10 = final_equities[max(int(n * 0.10) - 1, 0)]
        p25 = final_equities[max(int(n * 0.25) - 1, 0)]
        p75 = final_equities[min(int(n * 0.75), n - 1)]
        p90 = final_equities[min(int(n * 0.90), n - 1)]
        p95 = final_equities[min(int(n * 0.95), n - 1)]

        # VaR and CVaR
        var_95 = initial_equity - p5
        var_99 = initial_equity - final_equities[max(int(n * 0.01) - 1, 0)]
        cvar_95_values = [e for e in final_equities if e <= p5]
        cvar_99_values = [e for e in final_equities if e <= final_equities[max(int(n * 0.01) - 1, 0)]]
        cvar_95 = initial_equity - mean(cvar_95_values) if cvar_95_values else var_95
        cvar_99 = initial_equity - mean(cvar_99_values) if cvar_99_values else var_99

        # Probability metrics
        prob_loss = sum(1 for e in final_equities if e < initial_equity) / n
        prob_ruin = sum(1 for e in final_equities if e < initial_equity * 0.5) / n

        observe_counter("monte_carlo.simulations_completed", tags={"n_trades": str(n_trades)})

        return MonteCarloResult(
            n_simulations=self.n_simulations,
            n_trades=n_trades,
            median_final_equity=median(final_equities),
            mean_final_equity=mean(final_equities),
            p5_final_equity=p5,
            p10_final_equity=p10,
            p25_final_equity=p25,
            p75_final_equity=p75,
            p90_final_equity=p90,
            p95_final_equity=p95,
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            max_drawdown_median=median(max_drawdowns),
            max_drawdown_p95=max_drawdowns[min(int(n * 0.95), n - 1)],
            probability_of_loss=prob_loss,
            probability_of_ruin=prob_ruin,
            sharpe_ratio_median=median(sharpe_ratios) if sharpe_ratios else 0.0,
            raw_simulations=all_curves[:10],  # Only keep first 10 for visualization
        )

    def _simulate_curve(
        self,
        returns: list[float],
        initial_equity: float,
        position_size_pct: float,
    ) -> tuple[list[float], float]:
        """Simulate a single equity curve from a sequence of returns."""
        curve = [initial_equity]
        peak = initial_equity
        max_drawdown = 0.0

        for ret_pct in returns:
            current = curve[-1]
            position_value = current * (position_size_pct / 100.0)
            pnl = position_value * (ret_pct / 100.0)
            new_equity = max(current + pnl, 0.0)  # Can't go below zero
            curve.append(new_equity)

            if new_equity > peak:
                peak = new_equity
            if peak > 0:
                drawdown = (peak - new_equity) / peak
                max_drawdown = max(max_drawdown, drawdown)

        return curve, max_drawdown

    def _empty_result(self, initial_equity: float) -> MonteCarloResult:
        return MonteCarloResult(
            n_simulations=0,
            n_trades=0,
            median_final_equity=initial_equity,
            mean_final_equity=initial_equity,
            p5_final_equity=initial_equity,
            p10_final_equity=initial_equity,
            p25_final_equity=initial_equity,
            p75_final_equity=initial_equity,
            p90_final_equity=initial_equity,
            p95_final_equity=initial_equity,
            var_95=0.0,
            cvar_95=0.0,
            var_99=0.0,
            cvar_99=0.0,
            max_drawdown_median=0.0,
            max_drawdown_p95=0.0,
            probability_of_loss=0.0,
            probability_of_ruin=0.0,
            sharpe_ratio_median=0.0,
        )


# ---------------------------------------------------------------------------
# Stress testing
# ---------------------------------------------------------------------------
def run_stress_test(
    equity: float,
    positions: list[dict[str, Any]],
    *,
    scenario: StressScenario | None = None,
    scenarios: list[StressScenario] | None = None,
) -> list[StressTestResult]:
    """Run stress tests against the current portfolio state.

    Args:
        equity: Current portfolio equity
        positions: List of position dicts with 'symbol', 'market_value', 'quantity'
        scenario: A single stress scenario (or use `scenarios` for multiple)
        scenarios: List of scenarios to test (defaults to STRESS_SCENARIOS)
    """
    test_scenarios = [scenario] if scenario else (scenarios or STRESS_SCENARIOS)
    results: list[StressTestResult] = []
    total_exposure = sum(abs(float(p.get("market_value", 0))) for p in positions)

    for sc in test_scenarios:
        # Apply return shock proportional to exposure
        pnl = total_exposure * (sc.return_shock_pct / 100.0)
        # Apply gap impact on positions
        gap_impact = total_exposure * (sc.gap_pct / 100.0)
        total_pnl = pnl + gap_impact

        equity_after = max(equity + total_pnl, 0.0)
        max_dd = abs(total_pnl) / max(equity, 1.0)

        # Estimate fill quality degradation from spread widening
        fill_impact = min(sc.spread_multiplier / 10.0, 1.0)

        results.append(
            StressTestResult(
                scenario=sc.name,
                equity_before=equity,
                equity_after=equity_after,
                pnl=total_pnl,
                pnl_pct=(total_pnl / max(equity, 1.0)) * 100,
                max_drawdown_pct=max_dd * 100,
                fill_quality_impact=fill_impact,
            )
        )
        observe_counter("stress_test.completed", tags={"scenario": sc.name})

    return results


# ---------------------------------------------------------------------------
# Adverse fill models
# ---------------------------------------------------------------------------
def adverse_fill_adjustment(
    expected_price: float,
    quantity: int,
    *,
    avg_daily_volume: float = 1_000_000,
    spread_bps: float = 5.0,
    scenario: str = "normal",
) -> dict[str, float]:
    """Estimate worst-case fill price under different slippage scenarios.

    Returns a dict with best/expected/worst fill prices.
    """
    volume_ratio = quantity / max(avg_daily_volume, 1)
    spread_pct = spread_bps / 10_000.0

    scenario_multipliers = {
        "normal": 1.0,
        "volatile": 2.5,
        "illiquid": 5.0,
        "flash_crash": 10.0,
    }
    multiplier = scenario_multipliers.get(scenario, 1.0)

    # Market impact model (square root of volume ratio)
    market_impact_pct = (volume_ratio ** 0.5) * 0.01 * multiplier
    slippage_pct = spread_pct * multiplier + market_impact_pct

    best_fill = expected_price * (1 - spread_pct * 0.5)
    worst_fill = expected_price * (1 + slippage_pct)
    expected_fill = expected_price * (1 + slippage_pct * 0.3)

    return {
        "best_fill": round(best_fill, 4),
        "expected_fill": round(expected_fill, 4),
        "worst_fill": round(worst_fill, 4),
        "slippage_pct": round(slippage_pct * 100, 4),
        "market_impact_pct": round(market_impact_pct * 100, 4),
        "scenario": scenario,
    }
