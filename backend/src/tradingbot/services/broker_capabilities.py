from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tradingbot.enums import BrokerSlug, InstrumentClass, TradingMode, TradingPattern
from tradingbot.schemas.settings import TradingProfile


@dataclass(frozen=True, slots=True)
class BrokerCapabilityDefinition:
    key: str
    label: str
    description: str
    supported: bool


@dataclass(frozen=True, slots=True)
class BrokerDefinition:
    slug: BrokerSlug
    label: str
    summary: str
    default_account_type: str
    default_venue: str
    default_timezone: str
    default_base_currency: str
    default_permissions: tuple[str, ...]
    supported_modes: frozenset[TradingMode]
    supported_instruments: frozenset[InstrumentClass]
    supported_patterns: frozenset[TradingPattern]
    capabilities: tuple[BrokerCapabilityDefinition, ...]


@dataclass(frozen=True, slots=True)
class ExecutionSupportSummary:
    selected_for_analysis: TradingProfile
    supported_for_execution: TradingProfile | None
    status: str
    analysis_only_downgrade_reason: str | None
    live_start_allowed: bool


ALPACA_BROKER = BrokerDefinition(
    slug=BrokerSlug.ALPACA,
    label="Alpaca US Equities",
    summary="Current repo support is intentionally narrow: US cash-equity research plus same-session bracket-order execution.",
    default_account_type="cash",
    default_venue="US equities",
    default_timezone="America/New_York",
    default_base_currency="USD",
    default_permissions=("paper", "live", "cash_equities"),
    supported_modes=frozenset({TradingMode.PAPER, TradingMode.LIVE}),
    supported_instruments=frozenset({InstrumentClass.CASH_EQUITY}),
    supported_patterns=frozenset({TradingPattern.SCALPING, TradingPattern.INTRADAY}),
    capabilities=(
        BrokerCapabilityDefinition(
            key="cash_equities",
            label="Cash equities",
            description="Places stock and ETF orders in the cash-equity market.",
            supported=True,
        ),
        BrokerCapabilityDefinition(
            key="shorting",
            label="Shorting",
            description="Short-sale workflows through the current execution service.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="futures",
            label="Futures",
            description="Executable futures contracts with venue-aware validation.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="options",
            label="Options",
            description="Executable single-leg or multi-leg options orders.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="bracket_orders",
            label="Bracket orders",
            description="Entry with attached take-profit and stop-loss legs.",
            supported=True,
        ),
        BrokerCapabilityDefinition(
            key="oco_orders",
            label="OCO orders",
            description="Standalone one-cancels-other order workflows.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="stop_market",
            label="Stop-market orders",
            description="Direct stop-market submission outside bracket children.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="stop_limit",
            label="Stop-limit orders",
            description="Direct stop-limit submission and amendment.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="replace_cancel",
            label="Replace / cancel",
            description="Order amendment, cancellation, and repair flows.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="websocket_order_streams",
            label="Order streams",
            description="Realtime broker order/fill streams for reconciliation.",
            supported=False,
        ),
        BrokerCapabilityDefinition(
            key="paper_mode",
            label="Paper mode",
            description="Paper trading mode through the configured broker adapter.",
            supported=True,
        ),
        BrokerCapabilityDefinition(
            key="live_mode",
            label="Live mode",
            description="Live trading mode through the configured broker adapter.",
            supported=True,
        ),
    ),
)


BROKER_DEFINITIONS: dict[BrokerSlug, BrokerDefinition] = {
    BrokerSlug.ALPACA: ALPACA_BROKER,
}


def get_broker_definition(slug: BrokerSlug) -> BrokerDefinition:
    return BROKER_DEFINITIONS[slug]


def normalize_permissions(
    permissions: Iterable[str] | None,
    broker_definition: BrokerDefinition,
) -> list[str]:
    if permissions is None:
        return list(broker_definition.default_permissions)
    cleaned = sorted({item.strip() for item in permissions if item and item.strip()})
    return cleaned or list(broker_definition.default_permissions)


def resolve_execution_support(
    selected_for_analysis: TradingProfile,
    broker_definition: BrokerDefinition,
) -> ExecutionSupportSummary:
    if not _profile_completed(selected_for_analysis):
        return ExecutionSupportSummary(
            selected_for_analysis=selected_for_analysis,
            supported_for_execution=None,
            status="complete_agent_intake_first",
            analysis_only_downgrade_reason=None,
            live_start_allowed=False,
        )

    reasons: list[str] = []

    if selected_for_analysis.instrument_class not in broker_definition.supported_instruments:
        reasons.append(
            f"{broker_definition.label} is configured here for cash-equity execution only, so "
            f"{_display_value(selected_for_analysis.instrument_class)} stays analysis-only."
        )

    if selected_for_analysis.trading_pattern not in broker_definition.supported_patterns:
        reasons.append(
            f"The current {broker_definition.label} execution path only supports same-session cash-equity workflows, so "
            f"{_display_value(selected_for_analysis.trading_pattern)} stays analysis-only."
        )

    if reasons:
        return ExecutionSupportSummary(
            selected_for_analysis=selected_for_analysis,
            supported_for_execution=None,
            status="analysis_only_for_selected_broker",
            analysis_only_downgrade_reason=" ".join(reasons),
            live_start_allowed=False,
        )

    return ExecutionSupportSummary(
        selected_for_analysis=selected_for_analysis,
        supported_for_execution=selected_for_analysis.model_copy(deep=True),
        status="broker_execution_supported",
        analysis_only_downgrade_reason=None,
        live_start_allowed=TradingMode.LIVE in broker_definition.supported_modes,
    )


def _profile_completed(selected_for_analysis: TradingProfile) -> bool:
    return all(
        [
            selected_for_analysis.trading_pattern,
            selected_for_analysis.instrument_class,
            selected_for_analysis.strategy_family,
            selected_for_analysis.risk_profile,
            selected_for_analysis.market_universe,
        ]
    )


def _display_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    if raw_value is None:
        return "Not selected"
    return str(raw_value).replace("_", " ").title()
