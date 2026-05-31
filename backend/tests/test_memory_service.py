from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import BrokerSlug, OrderIntent, OrderStatus, OrderType, RiskDecision
from tradingbot.models import ExecutionQualitySample, RiskEvent, SymbolCooldown, TradeCandidate, TradeReview
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.memory import TradingMemoryService


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_memory_context_rolls_up_decisions_reviews_and_risk() -> None:
    session = _session_factory()()
    now = datetime.now(UTC)
    session.add_all(
        [
            TradeCandidate(
                profile_id=1,
                run_id="run-a",
                symbol="NVDA",
                direction=OrderIntent.BUY,
                confidence=0.72,
                status="approved",
                thesis="Opening range breakout with strong relative volume.",
                entry=100,
                stop_loss=99,
                take_profit=103,
                risk_notes=[],
                raw_payload={},
            ),
            TradeCandidate(
                profile_id=1,
                run_id="run-b",
                symbol="NVDA",
                direction=OrderIntent.HOLD,
                confidence=0.41,
                status="rejected",
                thesis="Rejected after liquidity faded.",
                entry=100,
                stop_loss=99,
                take_profit=103,
                risk_notes=["liquidity faded"],
                raw_payload={},
            ),
            TradeReview(
                profile_id=1,
                source_run_id="run-a",
                order_id=1,
                symbol="NVDA",
                status="queued",
                review_score=-0.4,
                pnl=-25,
                return_pct=-0.5,
                loss_cause="bad_execution",
                summary="NVDA breakout entries after wide opening spreads failed again.",
                recurring_pattern_key="bad_execution",
                review_payload={"thesis": "breakout"},
            ),
            TradeReview(
                profile_id=1,
                source_run_id="run-c",
                order_id=2,
                symbol="NVDA",
                status="queued",
                review_score=-0.2,
                pnl=-10,
                return_pct=-0.2,
                loss_cause="bad_execution",
                summary="Wide spreads caused poor fill quality.",
                recurring_pattern_key="bad_execution",
                review_payload={"thesis": "breakout"},
            ),
            RiskEvent(
                profile_id=1,
                symbol="NVDA",
                severity="warning",
                code="trade_rejected",
                message="Risk policy rejected the setup after cooldown.",
                payload={"notes": ["cooldown"]},
            ),
            SymbolCooldown(
                profile_id=1,
                symbol="NVDA",
                cooldown_type="stopout",
                reason="Recent stopout; wait for reset.",
                triggered_at=now - timedelta(minutes=5),
                expires_at=now + timedelta(minutes=55),
                context_json={"source": "test"},
            ),
            ExecutionQualitySample(
                profile_id=1,
                order_id=101,
                symbol="NVDA",
                broker_slug=BrokerSlug.ALPACA,
                venue="US equities",
                order_type=OrderType.BRACKET,
                side=OrderIntent.BUY,
                outcome_status=OrderStatus.FILLED,
                quantity=10,
                filled_quantity=10,
                fill_ratio=1,
                realized_slippage_bps=72,
                quality_score=0.33,
                spread_cost=0,
                notional=1000,
                payload={},
            ),
        ]
    )
    session.commit()

    context = TradingMemoryService(session, profile_id=1).build_context("nvda", as_of=now)

    assert context["decision_memory"]
    assert any("approved" in item["summary"] for item in context["decision_memory"])
    assert any("bad_execution" in item["summary"] for item in context["post_trade_lessons"])
    assert any(item["key"] == "execution_quality" for item in context["risk_memory"])
    assert any("cooldown" in note.lower() for note in context["risk_notes"])


def test_remember_decision_persists_compact_summary() -> None:
    session = _session_factory()()
    service = TradingMemoryService(session, profile_id=1)

    memory = service.remember_decision(
        decision=CommitteeDecision(
            symbol="AAPL",
            direction=OrderIntent.BUY,
            confidence=0.81,
            entry=190,
            stop_loss=188,
            take_profit=195,
            time_horizon="intraday",
            status=RiskDecision.APPROVED,
            thesis="Clean pullback continuation.",
            risk_notes=["position size reduced by memory risk note"],
        ),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=5, notes=["memory: prior slippage"]),
        run_id="run-123",
    )
    session.commit()

    assert memory.memory_type == "decision"
    assert memory.memory_key == "approved:buy"
    assert memory.payload["run_id"] == "run-123"
    assert "Clean pullback" in memory.summary
