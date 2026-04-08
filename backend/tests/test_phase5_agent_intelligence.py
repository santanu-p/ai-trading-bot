from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import BrokerSlug, ExecutionIntentStatus, ExecutionIntentType, OrderIntent, OrderStatus, OrderType, RiskDecision, RunStatus, TradingMode
from tradingbot.models import AgentRun, ExecutionIntent, OrderRecord, TradeReview
from tradingbot.schemas.settings import TradingProfile
from tradingbot.schemas.trading import AgentDecision, ChairSummary, RiskCheckResult
from tradingbot.services.adapters import AccountSnapshot, BrokerFill, BrokerPosition
from tradingbot.services.agents import AgentRunner
from tradingbot.services.committee import CommitteeService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.prompt_registry import PromptRegistry


class FakeLLMClient:
    def __init__(self, responses: list[str], model: str = "fake-phase5-model") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls: list[dict] = []

    def complete_json(self, *, system_prompt: str, prompt_payload: dict) -> str:
        self.calls.append({"system_prompt": system_prompt, "prompt_payload": prompt_payload})
        return self._responses.pop(0)


class StubExecutionAdapter:
    broker_slug = BrokerSlug.ALPACA

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000, daily_pl=0.0)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list:
        return []

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def replace_order(self, broker_order_id: str, patch):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> bool:
        raise NotImplementedError

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def fetch_fills(self, *, since=None, limit: int = 200, symbol: str | None = None):  # type: ignore[no-untyped-def]
        return []


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _agent_payload(role: str, *, confidence: float = 0.78, direction: str = "buy") -> str:
    return json.dumps(
        {
            "role": role,
            "symbol": "AAPL",
            "direction": direction,
            "confidence": confidence,
            "thesis": f"{role} approves the setup.",
            "entry": 101.2,
            "stop_loss": 99.8,
            "take_profit": 104.6,
            "time_horizon": "intraday",
            "vote": "approve" if direction == "buy" else "hold",
            "supporting_facts": ["Aligned with plan."],
            "risk_flags": [],
        }
    )


def _chair_payload(direction: str = "buy", vote: str = "approve") -> str:
    return json.dumps(
        {
            "symbol": "AAPL",
            "direction": direction,
            "confidence": 0.81,
            "time_horizon": "intraday",
            "vote": vote,
            "summary": "Committee alignment is adequate.",
            "dissenting_risks": [],
        }
    )


def test_phase5_structured_committee_repairs_malformed_specialist_output() -> None:
    client = FakeLLMClient(
        responses=[
            '{"role":"technical_structure","symbol":"AAPL"}',
            _agent_payload("technical_structure"),
            _agent_payload("catalyst"),
            _agent_payload("market_regime"),
            _agent_payload("portfolio_exposure"),
            _agent_payload("execution_quality"),
            _chair_payload(),
        ]
    )
    runner = AgentRunner(client=client, prompt_registry=PromptRegistry())

    result = runner.run_structured_committee(
        symbol="AAPL",
        trading_profile=TradingProfile(),
        feature_snapshot={"last_close": 101.5, "relative_volume_10": 1.4},
        news_items=[],
        structured_events=[],
        data_quality={"passed": True},
        portfolio_context={"open_positions": 1, "current_symbol_exposure": 0},
    )

    assert len(result.specialist_signals) == 5
    assert result.model_name == "fake-phase5-model"
    assert any(record.repaired for record in result.invocations)
    assert result.prompt_versions["technical_structure"] == "phase5.technical_structure.v1"


def test_phase5_committee_requires_chair_alignment() -> None:
    committee = CommitteeService(consensus_threshold=0.65, min_approval_votes=2)
    signals = [
        AgentDecision.model_validate_json(_agent_payload("technical_structure", confidence=0.8)),
        AgentDecision.model_validate_json(_agent_payload("catalyst", confidence=0.76)),
        AgentDecision.model_validate_json(_agent_payload("market_regime", confidence=0.74)),
        AgentDecision.model_validate_json(_agent_payload("portfolio_exposure", confidence=0.7)),
        AgentDecision.model_validate_json(_agent_payload("execution_quality", confidence=0.72)),
    ]
    chair = ChairSummary.model_validate_json(_chair_payload(direction="hold", vote="hold"))

    proposal = committee.propose(*signals, chair_summary=chair)

    assert proposal.status == RiskDecision.REJECTED
    assert proposal.direction == OrderIntent.HOLD
    assert proposal.chair_vote == "hold"


def test_phase5_exit_fill_creates_trade_review_with_model_lineage() -> None:
    session = _session()
    run = AgentRun(
        symbol="AAPL",
        status=RunStatus.SUCCEEDED,
        model_name="gpt-5-mini",
        prompt_versions_json={"chair": "phase5.chair.v1", "technical_structure": "phase5.technical_structure.v1"},
        input_snapshot_json={"symbol": "AAPL"},
    )
    session.add(run)
    session.flush()

    intent = ExecutionIntent(
        source_run_id=run.id,
        intent_type=ExecutionIntentType.TRADE,
        mode=TradingMode.PAPER,
        status=ExecutionIntentStatus.EXECUTED,
        symbol="AAPL",
        direction=OrderIntent.BUY,
        quantity=10,
        limit_price=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        requires_human_approval=False,
        idempotency_key="phase5-test-intent",
        decision_payload={"symbol": "AAPL"},
        risk_payload=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]).model_dump(mode="json"),
        metadata_json={},
    )
    session.add(intent)
    session.flush()

    parent = OrderRecord(
        execution_intent_id=intent.id,
        symbol="AAPL",
        mode=TradingMode.PAPER,
        direction=OrderIntent.BUY,
        order_type=OrderType.BRACKET,
        quantity=10,
        filled_quantity=10,
        average_fill_price=100.0,
        limit_price=100.0,
        stop_loss=98.0,
        stop_price=98.0,
        take_profit=104.0,
        status=OrderStatus.FILLED,
        client_order_id="phase5-parent-order",
        broker_order_id="phase5-parent-broker",
        metadata_json={"decision": {"symbol": "AAPL", "thesis": "Breakout continuation", "structured_events": []}},
    )
    session.add(parent)
    session.flush()

    child = OrderRecord(
        execution_intent_id=intent.id,
        symbol="AAPL",
        mode=TradingMode.PAPER,
        direction=OrderIntent.SELL,
        order_type=OrderType.LIMIT,
        quantity=10,
        filled_quantity=0,
        average_fill_price=None,
        limit_price=96.0,
        status=OrderStatus.ACCEPTED,
        client_order_id="phase5-child-order",
        broker_order_id="phase5-child-broker",
        parent_order_id=parent.id,
        metadata_json={},
    )
    session.add(child)
    session.commit()

    execution = ExecutionService(session, StubExecutionAdapter())
    created = execution.ingest_broker_fill(
        BrokerFill(
            broker_fill_id="phase5-fill-1",
            broker_order_id="phase5-child-broker",
            symbol="AAPL",
            side="sell",
            quantity=10,
            price=95.0,
            fee=0.0,
            filled_at=datetime.now(UTC),
            raw={},
        ),
        source="unit",
    )
    session.commit()

    review = session.scalar(select(TradeReview).where(TradeReview.order_id == child.id))
    summary = execution.trade_reviews.summarize_model_performance(limit=10)

    assert created is True
    assert review is not None
    assert review.status == "queued"
    assert review.model_name == "gpt-5-mini"
    assert review.loss_cause == "bad_execution"
    assert summary[0]["model_name"] == "gpt-5-mini"
