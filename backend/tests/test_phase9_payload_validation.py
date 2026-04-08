from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tradingbot.enums import OrderIntent, RiskDecision
from tradingbot.schemas.trading import CommitteeDecision

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "committee-decision.schema.json"


def test_phase9_committee_decision_accepts_valid_payload() -> None:
    payload = {
        "symbol": "AAPL",
        "direction": "buy",
        "confidence": 0.77,
        "entry": 101.5,
        "stop_loss": 99.4,
        "take_profit": 105.2,
        "time_horizon": "intraday",
        "status": "approved",
        "thesis": "Breakout with supportive volume and catalyst alignment.",
        "risk_notes": ["risk note"],
    }

    decision = CommitteeDecision.model_validate(payload)

    assert decision.symbol == "AAPL"
    assert decision.direction == OrderIntent.BUY
    assert decision.status == RiskDecision.APPROVED


def test_phase9_committee_decision_rejects_invalid_confidence() -> None:
    payload = {
        "symbol": "AAPL",
        "direction": "buy",
        "confidence": 1.2,
        "entry": 101.5,
        "stop_loss": 99.4,
        "take_profit": 105.2,
        "time_horizon": "intraday",
        "status": "approved",
        "thesis": "Invalid confidence should fail.",
    }

    with pytest.raises(ValidationError):
        CommitteeDecision.model_validate(payload)


def test_phase9_runtime_schema_stays_aligned_with_contract_enums() -> None:
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    model_fields = set(CommitteeDecision.model_fields.keys())

    required_contract_fields = set(schema["required"])
    direction_enum = set(schema["properties"]["direction"]["enum"])
    status_enum = set(schema["properties"]["status"]["enum"])

    assert required_contract_fields.issubset(model_fields)
    assert direction_enum == {item.value for item in OrderIntent}
    assert status_enum == {item.value for item in RiskDecision}
