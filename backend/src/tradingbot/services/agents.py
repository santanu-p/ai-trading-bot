from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from tradingbot.enums import AgentRole
from tradingbot.schemas.settings import TradingProfile
from tradingbot.schemas.trading import AgentDecision, ChairSummary
from tradingbot.services.adapters import NewsItem
from tradingbot.services.llm_clients import LLMClient, build_llm_client
from tradingbot.services.prompt_registry import PromptRegistry

SPECIALIST_ROLE_MAP: dict[str, AgentRole] = {
    "technical_structure": AgentRole.TECHNICAL_STRUCTURE,
    "catalyst": AgentRole.CATALYST,
    "market_regime": AgentRole.MARKET_REGIME,
    "portfolio_exposure": AgentRole.PORTFOLIO_EXPOSURE,
    "execution_quality": AgentRole.EXECUTION_QUALITY,
}

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(slots=True)
class AgentInvocationRecord:
    role: str
    prompt_key: str
    prompt_version: str
    model_name: str
    input_snapshot: dict[str, Any]
    raw_output: str | None = None
    repaired_output: str | None = None
    repair_attempts: int = 0
    repaired: bool = False
    error_message: str | None = None
    response_payload: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "prompt_key": self.prompt_key,
            "prompt_version": self.prompt_version,
            "model_name": self.model_name,
            "input_snapshot": self.input_snapshot,
            "repair_attempts": self.repair_attempts,
            "repaired": self.repaired,
            "error_message": self.error_message,
            "response_payload": self.response_payload,
        }


@dataclass(slots=True)
class StructuredCommitteeResult:
    specialist_signals: list[AgentDecision]
    chair_summary: ChairSummary
    invocations: list[AgentInvocationRecord]
    shared_input_snapshot: dict[str, Any]
    model_name: str

    @property
    def prompt_versions(self) -> dict[str, str]:
        return {record.prompt_key: record.prompt_version for record in self.invocations}

    def to_payload(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "prompt_versions": self.prompt_versions,
            "shared_input_snapshot": self.shared_input_snapshot,
            "specialist_signals": [item.model_dump(mode="json") for item in self.specialist_signals],
            "chair_summary": self.chair_summary.model_dump(mode="json"),
            "invocations": [record.to_payload() for record in self.invocations],
        }


class AgentOutputError(RuntimeError):
    def __init__(self, role: str, invocation: AgentInvocationRecord, message: str) -> None:
        super().__init__(message)
        self.role = role
        self.invocation = invocation


class AgentRunner:
    def __init__(
        self,
        model: str | None = None,
        *,
        client: LLMClient | None = None,
        prompt_registry: PromptRegistry | None = None,
        max_repair_attempts: int = 1,
    ) -> None:
        self.client = client or build_llm_client(model)
        self.model_name = getattr(self.client, "model", model or "unknown")
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.max_repair_attempts = max(0, max_repair_attempts)

    def market_agent(self, symbol: str, indicators: dict[str, float], trading_profile: TradingProfile) -> AgentDecision:
        payload = {
            "symbol": symbol,
            "trading_profile": trading_profile.model_dump(mode="json"),
            "feature_snapshot": indicators,
        }
        decision, _ = self._run_prompt(
            prompt_key="technical_structure",
            role=AgentRole.MARKET.value,
            prompt_payload=payload,
            response_model=AgentDecision,
        )
        return decision

    def news_agent(
        self,
        symbol: str,
        news_items: list[NewsItem],
        trading_profile: TradingProfile,
        *,
        structured_events: list[dict[str, Any]] | None = None,
    ) -> AgentDecision:
        payload = {
            "symbol": symbol,
            "trading_profile": trading_profile.model_dump(mode="json"),
            "news": _serialize_news(news_items),
            "structured_events": structured_events or [],
        }
        decision, _ = self._run_prompt(
            prompt_key="catalyst",
            role=AgentRole.NEWS.value,
            prompt_payload=payload,
            response_model=AgentDecision,
        )
        return decision

    def run_structured_committee(
        self,
        *,
        symbol: str,
        trading_profile: TradingProfile,
        feature_snapshot: dict[str, float],
        news_items: list[NewsItem],
        structured_events: list[dict[str, Any]],
        data_quality: dict[str, Any],
        portfolio_context: dict[str, Any],
    ) -> StructuredCommitteeResult:
        shared_input_snapshot = {
            "symbol": symbol,
            "trading_profile": trading_profile.model_dump(mode="json"),
            "feature_snapshot": feature_snapshot,
            "news": _serialize_news(news_items),
            "structured_events": structured_events,
            "data_quality": data_quality,
            "portfolio_context": portfolio_context,
        }

        specialist_signals: list[AgentDecision] = []
        invocations: list[AgentInvocationRecord] = []
        for prompt_key, role in SPECIALIST_ROLE_MAP.items():
            payload = {**shared_input_snapshot, "role_focus": prompt_key}
            decision, invocation = self._run_prompt(
                prompt_key=prompt_key,
                role=role.value,
                prompt_payload=payload,
                response_model=AgentDecision,
            )
            specialist_signals.append(decision)
            invocations.append(invocation)

        chair_payload = {
            **shared_input_snapshot,
            "specialist_signals": [item.model_dump(mode="json") for item in specialist_signals],
        }
        chair_summary, chair_invocation = self._run_prompt(
            prompt_key="chair",
            role=AgentRole.CHAIR.value,
            prompt_payload=chair_payload,
            response_model=ChairSummary,
        )
        invocations.append(chair_invocation)
        return StructuredCommitteeResult(
            specialist_signals=specialist_signals,
            chair_summary=chair_summary,
            invocations=invocations,
            shared_input_snapshot=shared_input_snapshot,
            model_name=self.model_name,
        )

    def _run_prompt(
        self,
        *,
        prompt_key: str,
        role: str,
        prompt_payload: dict[str, Any],
        response_model: type[ResponseModel],
    ) -> tuple[ResponseModel, AgentInvocationRecord]:
        template = self.prompt_registry.get(prompt_key)
        invocation = AgentInvocationRecord(
            role=role,
            prompt_key=prompt_key,
            prompt_version=template.version,
            model_name=self.model_name,
            input_snapshot=prompt_payload,
        )
        raw_output = self.client.complete_json(system_prompt=template.system_prompt, prompt_payload=prompt_payload)
        invocation.raw_output = raw_output
        try:
            parsed = self._parse_response(response_model, raw_output, role=role, symbol=str(prompt_payload["symbol"]))
            invocation.response_payload = parsed.model_dump(mode="json")
            return parsed, invocation
        except Exception as exc:  # noqa: BLE001
            invocation.error_message = str(exc)

        repair_output = invocation.raw_output
        for attempt in range(self.max_repair_attempts):
            repair_output = self.client.complete_json(
                system_prompt=(
                    "Repair the previous assistant output. "
                    "Return only valid JSON that matches the requested schema. "
                    "Do not add commentary, markdown fences, or prose."
                ),
                prompt_payload={
                    "role": role,
                    "original_prompt_payload": prompt_payload,
                    "invalid_output": repair_output,
                    "validation_error": invocation.error_message,
                    "required_schema": response_model.model_json_schema(),
                },
            )
            invocation.repair_attempts = attempt + 1
            invocation.repaired_output = repair_output
            try:
                parsed = self._parse_response(
                    response_model,
                    repair_output,
                    role=role,
                    symbol=str(prompt_payload["symbol"]),
                )
                invocation.repaired = True
                invocation.error_message = None
                invocation.response_payload = parsed.model_dump(mode="json")
                return parsed, invocation
            except Exception as exc:  # noqa: BLE001
                invocation.error_message = str(exc)

        raise AgentOutputError(role, invocation, invocation.error_message or "Agent output validation failed.")

    def _parse_response(
        self,
        response_model: type[ResponseModel],
        raw_output: str,
        *,
        role: str,
        symbol: str,
    ) -> ResponseModel:
        parsed = response_model.model_validate_json(raw_output)
        if isinstance(parsed, AgentDecision):
            return parsed.model_copy(update={"role": role, "symbol": symbol.upper().strip()})  # type: ignore[return-value]
        if isinstance(parsed, ChairSummary):
            return parsed.model_copy(update={"symbol": symbol.upper().strip()})  # type: ignore[return-value]
        return parsed


def _serialize_news(news_items: list[NewsItem]) -> list[dict[str, Any]]:
    return [
        {
            "headline": item.headline,
            "summary": item.summary,
            "source": item.source,
            "created_at": item.created_at.isoformat(),
        }
        for item in news_items
    ]
