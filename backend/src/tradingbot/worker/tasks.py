from __future__ import annotations

from datetime import UTC, datetime, timedelta

from celery.result import AsyncResult
from sqlalchemy import select

from tradingbot.config import get_settings
from tradingbot.db import get_session_factory
from tradingbot.enums import BotStatus, RiskDecision, RunStatus, TradingMode
from tradingbot.models import AgentRun, BotSettings, PortfolioSnapshot, PositionRecord, RiskEvent, TradeCandidate, WatchlistSymbol
from tradingbot.schemas.trading import BacktestRequest, RiskCheckResult
from tradingbot.services.adapters import build_broker_adapter, build_market_data_adapter, build_news_adapter
from tradingbot.services.agents import AgentRunner
from tradingbot.services.backtest import BacktestService
from tradingbot.services.calendar import MarketCalendarService
from tradingbot.services.committee import CommitteeService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.indicators import bar_summary
from tradingbot.services.reconciliation import ReconciliationService
from tradingbot.services.risk import RiskEngine, RiskPolicy
from tradingbot.services.store import (
    ensure_bot_settings,
    live_trading_env_allowed,
    resolve_execution_support,
    serialize_trading_profile,
    strategy_profile_completed,
)
from tradingbot.worker.execution_tasks import enqueue_execution_intent, enqueue_session_flatten
from tradingbot.worker.celery_app import celery_app


def _build_risk_engine(settings_row: BotSettings) -> RiskEngine:
    return RiskEngine(
        RiskPolicy(
            max_open_positions=settings_row.max_open_positions,
            max_daily_loss_pct=settings_row.max_daily_loss_pct,
            max_position_risk_pct=settings_row.max_position_risk_pct,
            max_symbol_notional_pct=settings_row.max_symbol_notional_pct,
            symbol_cooldown_minutes=settings_row.symbol_cooldown_minutes,
        )
    )


def enqueue_backtest(payload: BacktestRequest) -> AsyncResult:
    return run_backtest.delay(payload.model_dump(mode="json"))


@celery_app.task(name="tradingbot.worker.tasks.run_market_scan")
def run_market_scan() -> dict[str, int]:
    settings = get_settings()
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session)
        if settings_row.status != BotStatus.RUNNING or settings_row.kill_switch_enabled:
            return {"queued": 0, "repaired_children": 0, "unresolved_mismatches": 0}
        if not strategy_profile_completed(settings_row):
            session.add(
                RiskEvent(
                    symbol=None,
                    severity="warning",
                    code="strategy_profile_missing",
                    message="Complete the trading-pattern intake before starting the agent workflow.",
                    payload={},
                )
            )
            session.commit()
            return {"queued": 0, "repaired_children": 0, "unresolved_mismatches": 0}

        execution_support = resolve_execution_support(settings_row)
        if settings_row.mode == TradingMode.LIVE and (
            not execution_support.live_start_allowed or not live_trading_env_allowed(settings_row)
        ):
            session.add(
                RiskEvent(
                    symbol=None,
                    severity="critical",
                    code="live_scope_unsupported",
                    message=execution_support.analysis_only_downgrade_reason
                    or "Live mode is blocked for the selected broker/profile combination.",
                    payload={},
                )
            )
            session.commit()
            return {"queued": 0, "repaired_children": 0, "unresolved_mismatches": 0}

        broker = build_broker_adapter(settings_row)
        market_data = build_market_data_adapter(settings_row)
        news_data = build_news_adapter(settings_row)
        agent_runner = AgentRunner(settings_row.openai_model)
        committee = CommitteeService(settings_row.consensus_threshold, settings.min_approval_votes)
        risk_engine = _build_risk_engine(settings_row)
        execution = ExecutionService(session, broker)
        calendar = MarketCalendarService.for_settings(settings_row)
        reconciliation = ReconciliationService(
            session=session,
            settings_row=settings_row,
            execution=execution,
            adapter=broker,
        )

        reconciliation_report = reconciliation.reconcile()
        if settings_row.mode == TradingMode.LIVE and reconciliation_report.live_paused:
            return {
                "queued": 0,
                "repaired_children": 0,
                "unresolved_mismatches": reconciliation_report.unresolved_mismatches,
            }

        session_state = calendar.session_state(
            trading_pattern=settings_row.trading_pattern,
            instrument_class=settings_row.instrument_class,
        )
        if session_state.should_flatten_positions:
            if session.query(PositionRecord).count() > 0:
                enqueue_session_flatten("session_close_flatten")
            return {
                "queued": 0,
                "repaired_children": 0,
                "unresolved_mismatches": reconciliation_report.unresolved_mismatches,
            }
        if not session_state.can_scan:
            session.add(
                RiskEvent(
                    symbol=None,
                    severity="warning",
                    code="market_closed",
                    message=session_state.reason or "Market session is closed for scanning.",
                    payload={"next_session_opens_at": session_state.next_session_opens_at.isoformat() if session_state.next_session_opens_at else None},
                )
            )
            session.commit()
            return {
                "queued": 0,
                "repaired_children": 0,
                "unresolved_mismatches": reconciliation_report.unresolved_mismatches,
            }

        account = broker.get_account_snapshot()
        broker_positions = broker.list_positions()
        execution.sync_positions_snapshot(broker_positions, source="scan_snapshot")
        session.add(
            PortfolioSnapshot(
                equity=account.equity,
                cash=account.cash,
                buying_power=account.buying_power,
                daily_pl=account.daily_pl,
                exposure=sum(position.market_value for position in broker_positions),
            )
        )
        session.commit()

        open_positions = session.query(PositionRecord).count()
        watchlist = session.scalars(select(WatchlistSymbol).where(WatchlistSymbol.enabled.is_(True))).all()
        end = datetime.now(UTC)
        start = end - timedelta(minutes=settings_row.scan_interval_minutes * 40)
        queued = 0
        trading_profile = serialize_trading_profile(settings_row)
        executor_block_reason = execution_support.analysis_only_downgrade_reason

        for item in watchlist:
            run = AgentRun(symbol=item.symbol, status=RunStatus.RUNNING, started_at=end)
            session.add(run)
            session.commit()
            session.refresh(run)
            try:
                bars = market_data.get_intraday_bars(
                    item.symbol,
                    start=start,
                    end=end,
                    interval_minutes=settings_row.scan_interval_minutes,
                )
                if not bars:
                    raise RuntimeError("No market bars returned.")
                indicators = bar_summary(bars)
                news = news_data.get_recent_news(item.symbol, limit=8)
                market_decision = agent_runner.market_agent(item.symbol, indicators, trading_profile)
                news_decision = agent_runner.news_agent(item.symbol, news, trading_profile)
                proposal = committee.propose(market_decision, news_decision)
                if execution_support.supported_for_execution is None:
                    risk_result = RiskCheckResult(
                        decision=RiskDecision.REJECTED,
                        approved_quantity=0,
                        notes=[executor_block_reason] if executor_block_reason else [],
                    )
                else:
                    risk_result = risk_engine.validate(
                        proposal,
                        equity=account.equity,
                        buying_power=account.buying_power,
                        open_positions=open_positions,
                        daily_loss_pct=max((-account.daily_pl / max(account.equity, 1)), 0),
                        active_symbol_exposure=execution.current_symbol_exposure(item.symbol),
                        is_symbol_in_cooldown=False,
                    )
                decision = committee.finalize(proposal, risk_result=risk_result)

                session.add(
                    TradeCandidate(
                        run_id=run.id,
                        symbol=decision.symbol,
                        direction=decision.direction,
                        confidence=decision.confidence,
                        status=decision.status.value,
                        thesis=decision.thesis,
                        entry=decision.entry,
                        stop_loss=decision.stop_loss,
                        take_profit=decision.take_profit,
                        risk_notes=decision.risk_notes,
                        raw_payload=decision.model_dump(mode="json"),
                    )
                )
                run.status = RunStatus.SUCCEEDED
                run.finished_at = datetime.now(UTC)
                run.decision_payload = decision.model_dump(mode="json")
                session.commit()

                if decision.status.value == "approved":
                    intent = execution.queue_trade_intent(
                        settings_row=settings_row,
                        run_id=run.id,
                        decision=decision,
                        risk_result=risk_result,
                        execution_allowed=execution_support.supported_for_execution is not None,
                        block_reason=executor_block_reason,
                    )
                    if intent.status.value == "approved":
                        enqueue_execution_intent(intent.id)
                    open_positions += 1
                    queued += 1
                else:
                    session.add(
                        RiskEvent(
                            symbol=item.symbol,
                            severity="warning",
                            code="trade_rejected",
                            message=decision.reject_reason or "Committee or risk policy rejected the trade.",
                            payload={"notes": decision.risk_notes},
                        )
                    )
                    session.commit()
            except Exception as exc:  # noqa: BLE001
                run.status = RunStatus.FAILED
                run.finished_at = datetime.now(UTC)
                run.error_message = str(exc)
                session.add(
                    RiskEvent(
                        symbol=item.symbol,
                        severity="critical",
                        code="scan_failure",
                        message="Market scan failed for symbol.",
                        payload={"error": str(exc)},
                    )
                )
                session.commit()

        repaired_children = execution.repair_broken_child_orders()
        post_report = reconciliation.reconcile()

        return {
            "queued": queued,
            "repaired_children": repaired_children,
            "unresolved_mismatches": post_report.unresolved_mismatches,
        }
    finally:
        session.close()


@celery_app.task(name="tradingbot.worker.tasks.run_reconciliation")
def run_reconciliation() -> dict[str, int]:
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session)
        broker = build_broker_adapter(settings_row)
        execution = ExecutionService(session, broker)
        service = ReconciliationService(
            session=session,
            settings_row=settings_row,
            execution=execution,
            adapter=broker,
        )
        report = service.reconcile()
        return {
            "transitions_applied": report.transitions_applied,
            "fills_ingested": report.fills_ingested,
            "mismatches_created": report.mismatches_created,
            "unresolved_mismatches": report.unresolved_mismatches,
            "live_paused": int(report.live_paused),
        }
    finally:
        session.close()


@celery_app.task(name="tradingbot.worker.tasks.run_backtest")
def run_backtest(payload: dict) -> dict[str, int]:
    request = BacktestRequest.model_validate(payload)
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session)
        market_data = build_market_data_adapter(settings_row)
        news_data = build_news_adapter(settings_row)
        agent_runner = AgentRunner(settings_row.openai_model)
        committee = CommitteeService(settings_row.consensus_threshold, get_settings().min_approval_votes)
        risk_engine = _build_risk_engine(settings_row)
        service = BacktestService(market_data, news_data, agent_runner, committee, risk_engine)
        trading_profile = serialize_trading_profile(settings_row)

        slices = []
        for symbol in request.symbols:
            slices.extend(service.replay_symbol(symbol, request.start, request.end, request.interval_minutes, trading_profile))

        return {"runs": len(slices)}
    finally:
        session.close()
