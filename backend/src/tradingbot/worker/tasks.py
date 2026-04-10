from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from celery.result import AsyncResult
from sqlalchemy import select

from tradingbot.config import get_settings
from tradingbot.db import get_session_factory
from tradingbot.enums import BotStatus, OrderIntent, RiskDecision, RunStatus, TradingMode, TradingPattern
from tradingbot.models import (
    AgentRun,
    BacktestReport,
    BacktestTrade,
    BotSettings,
    PortfolioSnapshot,
    PositionRecord,
    RiskEvent,
    TradeCandidate,
    WatchlistSymbol,
)
from tradingbot.schemas.trading import BacktestRequest, CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import build_broker_adapter, build_market_data_adapter, build_news_adapter
from tradingbot.services.agents import AgentOutputError, AgentRunner
from tradingbot.services.alerts import AlertService
from tradingbot.services.backtest import BacktestService, BacktestSimulationConfig
from tradingbot.services.calendar import MarketCalendarService
from tradingbot.services.committee import CommitteeService
from tradingbot.services.data_quality import DataQualityPolicy, DataQualityValidator
from tradingbot.services.events import extract_structured_events, serialize_structured_events
from tradingbot.services.execution import ExecutionService
from tradingbot.services.features import IndexContext, build_feature_snapshot, infer_market_index_context
from tradingbot.services.metrics import observe_counter, observe_duration_ms
from tradingbot.services.observability import bind_run_id
from tradingbot.services.reconciliation import ReconciliationService
from tradingbot.services.risk import PortfolioRiskService, PositionExposure, RiskEngine, RiskPolicy
from tradingbot.services.store import (
    ensure_bot_settings,
    list_enabled_profiles,
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
            max_gross_exposure_pct=settings_row.max_gross_exposure_pct,
            max_sector_exposure_pct=settings_row.max_sector_exposure_pct,
            max_correlation_exposure_pct=settings_row.max_correlation_exposure_pct,
            max_event_cluster_positions=settings_row.max_event_cluster_positions,
            volatility_target_pct=settings_row.volatility_target_pct,
            atr_sizing_multiplier=settings_row.atr_sizing_multiplier,
            equity_curve_throttle_start_pct=settings_row.equity_curve_throttle_start_pct,
            equity_curve_throttle_min_scale=settings_row.equity_curve_throttle_min_scale,
            intraday_drawdown_pause_pct=settings_row.intraday_drawdown_pause_pct,
            loss_streak_reduction_threshold=settings_row.loss_streak_reduction_threshold,
            loss_streak_size_scale=settings_row.loss_streak_size_scale,
            execution_failure_review_threshold=settings_row.execution_failure_review_threshold,
            severe_anomaly_kill_switch_threshold=settings_row.severe_anomaly_kill_switch_threshold,
            symbol_cooldown_profit_minutes=settings_row.symbol_cooldown_profit_minutes,
            symbol_cooldown_stopout_minutes=settings_row.symbol_cooldown_stopout_minutes,
            symbol_cooldown_event_minutes=settings_row.symbol_cooldown_event_minutes,
            symbol_cooldown_whipsaw_minutes=settings_row.symbol_cooldown_whipsaw_minutes,
        )
    )


def _requires_timely_news(pattern: TradingPattern | None) -> bool:
    if pattern is None:
        return True
    return pattern not in {TradingPattern.DELIVERY, TradingPattern.POSITIONAL}


def _quality_rejection_decision(
    *,
    symbol: str,
    feature_snapshot: dict[str, float],
    notes: list[str],
) -> CommitteeDecision:
    reference = max(feature_snapshot.get("last_close", 0.0), 0.01)
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.HOLD,
        confidence=0.0,
        entry=round(reference, 4),
        stop_loss=round(max(reference * 0.995, 0.01), 4),
        take_profit=round(reference * 1.005, 4),
        time_horizon="intraday",
        status=RiskDecision.REJECTED,
        thesis="Trade rejected before agent inference due to failed data-quality checks.",
        reject_reason="; ".join(notes),
        market_vote="reject",
        news_vote="reject",
        risk_notes=notes,
    )


def _agent_rejection_decision(
    *,
    symbol: str,
    feature_snapshot: dict[str, float],
    notes: list[str],
) -> CommitteeDecision:
    reference = max(feature_snapshot.get("last_close", 0.0), 0.01)
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.HOLD,
        confidence=0.0,
        entry=round(reference, 4),
        stop_loss=round(max(reference * 0.995, 0.01), 4),
        take_profit=round(reference * 1.005, 4),
        time_horizon="intraday",
        status=RiskDecision.REJECTED,
        thesis="Trade rejected because committee agent output could not be repaired into a valid schema.",
        reject_reason="; ".join(notes),
        market_vote="reject",
        news_vote="reject",
        chair_vote="reject",
        risk_notes=notes,
    )


def _execution_quality_rejection_decision(
    *,
    symbol: str,
    feature_snapshot: dict[str, float],
    notes: list[str],
) -> CommitteeDecision:
    reference = max(feature_snapshot.get("last_close", 0.0), 0.01)
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.HOLD,
        confidence=0.0,
        entry=round(reference, 4),
        stop_loss=round(max(reference * 0.995, 0.01), 4),
        take_profit=round(reference * 1.005, 4),
        time_horizon="intraday",
        status=RiskDecision.REJECTED,
        thesis="Trade rejected before committee inference due to persistently poor execution-quality outcomes.",
        reject_reason="; ".join(notes),
        market_vote="reject",
        news_vote="reject",
        risk_notes=notes,
    )


def _decision_payload(
    *,
    decision: CommitteeDecision,
    feature_snapshot: dict[str, float],
    data_quality_payload: dict[str, object],
    data_timestamps: dict[str, str | None],
    structured_events: list[dict[str, object]],
    index_context: IndexContext,
    committee_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = decision.model_dump(mode="json")
    payload["feature_snapshot"] = feature_snapshot
    payload["data_quality"] = data_quality_payload
    payload["data_timestamps"] = data_timestamps
    payload["structured_events"] = structured_events
    payload["market_index_context"] = index_context.to_payload()
    if committee_metadata is not None:
        payload["committee_metadata"] = committee_metadata
    return payload


def enqueue_backtest(payload: BacktestRequest, report_id: str) -> AsyncResult:
    serialized = payload.model_dump(mode="json")
    serialized["report_id"] = report_id
    return run_backtest.delay(serialized)


@celery_app.task(name="tradingbot.worker.tasks.run_market_scan")
def run_market_scan(profile_id: int | None = None) -> dict[str, int]:
    started = perf_counter()
    observe_counter("worker.market_scan.invocations")
    settings = get_settings()
    session = get_session_factory()()
    try:
        if profile_id is None:
            aggregate = {"queued": 0, "repaired_children": 0, "unresolved_mismatches": 0}
            for profile in list_enabled_profiles(session):
                result = run_market_scan(profile.id)
                aggregate["queued"] += int(result.get("queued", 0))
                aggregate["repaired_children"] += int(result.get("repaired_children", 0))
                aggregate["unresolved_mismatches"] += int(result.get("unresolved_mismatches", 0))
            return aggregate

        settings_row = ensure_bot_settings(session, profile_id=profile_id)
        if settings_row.status != BotStatus.RUNNING or settings_row.kill_switch_enabled:
            return {"queued": 0, "repaired_children": 0, "unresolved_mismatches": 0}
        if not strategy_profile_completed(settings_row):
            session.add(
                RiskEvent(
                    profile_id=settings_row.id,
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
                    profile_id=settings_row.id,
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

        broker = build_broker_adapter(session, settings_row)
        market_data = build_market_data_adapter(settings_row)
        news_data = build_news_adapter(settings_row)
        agent_runner = AgentRunner(settings_row.openai_model)
        committee = CommitteeService(settings_row.consensus_threshold, settings.min_approval_votes)
        risk_engine = _build_risk_engine(settings_row)
        execution = ExecutionService(session, broker, settings_row)
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
            if session.query(PositionRecord).filter(PositionRecord.profile_id == settings_row.id).count() > 0:
                enqueue_session_flatten("session_close_flatten")
            return {
                "queued": 0,
                "repaired_children": 0,
                "unresolved_mismatches": reconciliation_report.unresolved_mismatches,
            }
        if not session_state.can_scan:
            session.add(
                RiskEvent(
                    profile_id=settings_row.id,
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
                profile_id=settings_row.id,
                equity=account.equity,
                cash=account.cash,
                buying_power=account.buying_power,
                daily_pl=account.daily_pl,
                exposure=sum(position.market_value for position in broker_positions),
            )
        )
        session.commit()

        open_positions = session.query(PositionRecord).filter(PositionRecord.profile_id == settings_row.id).count()
        watchlist = session.scalars(
            select(WatchlistSymbol)
            .where(WatchlistSymbol.profile_id == settings_row.id)
            .where(WatchlistSymbol.enabled.is_(True))
        ).all()
        end = datetime.now(UTC)
        start = end - timedelta(minutes=settings_row.scan_interval_minutes * 40)
        queued = 0
        portfolio_risk = PortfolioRiskService(session, risk_engine.policy, profile_id=settings_row.id)
        runtime_metrics = portfolio_risk.compute_runtime_metrics(
            equity=account.equity,
            positions=broker_positions,
            now=end,
        )
        if portfolio_risk.trigger_kill_switch_if_needed(settings_row, runtime=runtime_metrics):
            session.commit()
            return {
                "queued": 0,
                "repaired_children": 0,
                "unresolved_mismatches": reconciliation_report.unresolved_mismatches,
            }
        trading_profile = serialize_trading_profile(settings_row)
        executor_block_reason = execution_support.analysis_only_downgrade_reason
        data_quality = DataQualityValidator(
            DataQualityPolicy(
                max_bar_staleness_minutes=max(15, settings_row.scan_interval_minutes * 3),
                max_news_staleness_minutes=max(45, settings_row.scan_interval_minutes * 12),
                max_missing_candle_ratio=0.12,
                abnormal_gap_multiplier=4.0,
            )
        )
        index_bars: dict[str, list] = {}
        benchmark_symbols = settings_row.benchmark_symbols or (["SPY", "QQQ"] if settings_row.market_region.value == "us" else [])
        for index_symbol in benchmark_symbols:
            try:
                index_bars[index_symbol] = market_data.get_intraday_bars(
                    index_symbol,
                    start=start,
                    end=end,
                    interval_minutes=settings_row.scan_interval_minutes,
                )
            except Exception as exc:  # noqa: BLE001
                index_bars[index_symbol] = []
                session.add(
                    RiskEvent(
                        profile_id=settings_row.id,
                        symbol=index_symbol,
                        severity="warning",
                        code="index_context_unavailable",
                        message="Failed to fetch bars for market-index context.",
                        payload={"error": str(exc)},
                    )
                )
        index_context = infer_market_index_context(index_bars)
        session.commit()

        for item in watchlist:
            run = AgentRun(profile_id=settings_row.id, symbol=item.symbol, status=RunStatus.RUNNING, started_at=end)
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
                feature_snapshot = build_feature_snapshot(
                    bars,
                    interval_minutes=settings_row.scan_interval_minutes,
                    index_context=index_context,
                )
                news = news_data.get_recent_news(item.symbol, limit=8)
                structured_events = extract_structured_events(
                    item.symbol,
                    news,
                    as_of=end,
                    index_context=index_context,
                )
                structured_event_payload = serialize_structured_events(structured_events)
                quality_report = data_quality.evaluate(
                    symbol=item.symbol,
                    bars=bars,
                    news_items=news,
                    interval_minutes=settings_row.scan_interval_minutes,
                    now=end,
                    requires_timely_news=_requires_timely_news(settings_row.trading_pattern),
                )
                if not quality_report.passed:
                    rejection_notes = quality_report.rejection_notes() or ["Data quality checks failed."]
                    quality_reject = _quality_rejection_decision(
                        symbol=item.symbol,
                        feature_snapshot=feature_snapshot,
                        notes=rejection_notes,
                    )
                    quality_payload = _decision_payload(
                        decision=quality_reject,
                        feature_snapshot=feature_snapshot,
                        data_quality_payload=quality_report.to_payload(),
                        data_timestamps=quality_report.data_timestamps,
                        structured_events=structured_event_payload,
                        index_context=index_context,
                    )
                    session.add(
                        TradeCandidate(
                            profile_id=settings_row.id,
                            run_id=run.id,
                            symbol=quality_reject.symbol,
                            direction=quality_reject.direction,
                            confidence=quality_reject.confidence,
                            status=quality_reject.status.value,
                            thesis=quality_reject.thesis,
                            entry=quality_reject.entry,
                            stop_loss=quality_reject.stop_loss,
                            take_profit=quality_reject.take_profit,
                            risk_notes=quality_reject.risk_notes,
                            raw_payload=quality_payload,
                        )
                    )
                    run.status = RunStatus.SUCCEEDED
                    run.finished_at = datetime.now(UTC)
                    run.decision_payload = quality_payload
                    session.add(
                        RiskEvent(
                            profile_id=settings_row.id,
                            symbol=item.symbol,
                            severity="critical",
                            code="data_quality_rejected",
                            message="Scan data-quality checks rejected the symbol before agent inference.",
                            payload={
                                "notes": rejection_notes,
                                "issues": quality_report.to_payload()["issues"],
                                "data_timestamps": quality_report.data_timestamps,
                            },
                        )
                    )
                    session.commit()
                    observe_counter("decision.rejected", tags={"reason": "data_quality"})
                    continue

                execution_feedback = execution.execution_feedback_for_symbol(item.symbol)
                if bool(execution_feedback.get("block_new_entries")):
                    notes_payload = execution_feedback.get("notes")
                    note_items = notes_payload if isinstance(notes_payload, list) else []
                    rejection_notes = [
                        str(note)
                        for note in note_items
                        if isinstance(note, str) and note.strip()
                    ]
                    if not rejection_notes:
                        rejection_notes = [
                            "Execution-quality feedback blocked new entries for this symbol.",
                        ]
                    execution_reject = _execution_quality_rejection_decision(
                        symbol=item.symbol,
                        feature_snapshot=feature_snapshot,
                        notes=rejection_notes,
                    )
                    execution_payload = _decision_payload(
                        decision=execution_reject,
                        feature_snapshot=feature_snapshot,
                        data_quality_payload=quality_report.to_payload(),
                        data_timestamps=quality_report.data_timestamps,
                        structured_events=structured_event_payload,
                        index_context=index_context,
                        committee_metadata={"execution_feedback": execution_feedback},
                    )
                    session.add(
                        TradeCandidate(
                            profile_id=settings_row.id,
                            run_id=run.id,
                            symbol=execution_reject.symbol,
                            direction=execution_reject.direction,
                            confidence=execution_reject.confidence,
                            status=execution_reject.status.value,
                            thesis=execution_reject.thesis,
                            entry=execution_reject.entry,
                            stop_loss=execution_reject.stop_loss,
                            take_profit=execution_reject.take_profit,
                            risk_notes=execution_reject.risk_notes,
                            raw_payload=execution_payload,
                        )
                    )
                    run.status = RunStatus.SUCCEEDED
                    run.finished_at = datetime.now(UTC)
                    run.decision_payload = execution_payload
                    session.add(
                        RiskEvent(
                            profile_id=settings_row.id,
                            symbol=item.symbol,
                            severity="warning",
                            code="execution_feedback_rejected",
                            message="Symbol rejected before committee inference due to poor recent execution outcomes.",
                            payload={"feedback": execution_feedback, "notes": rejection_notes},
                        )
                    )
                    session.commit()
                    observe_counter("decision.rejected", tags={"reason": "execution_feedback"})
                    continue

                portfolio_context = {
                    "equity": round(account.equity, 4),
                    "buying_power": round(account.buying_power, 4),
                    "daily_pl": round(account.daily_pl, 4),
                    "open_positions": open_positions,
                    "current_symbol_exposure": round(execution.current_symbol_exposure(item.symbol), 4),
                    "portfolio_exposure": round(runtime_metrics.portfolio_exposure, 4),
                    "positions": [
                        {
                            "symbol": position.symbol,
                            "market_value": round(position.market_value, 4),
                            "unrealized_pl": round(position.unrealized_pl, 4),
                            "side": position.side,
                        }
                        for position in broker_positions[:10]
                    ],
                    "execution_quality": execution_feedback,
                }
                with bind_run_id(run.id):
                    committee_result = agent_runner.run_structured_committee(
                        symbol=item.symbol,
                        trading_profile=trading_profile,
                        feature_snapshot=feature_snapshot,
                        news_items=news,
                        structured_events=structured_event_payload,
                        data_quality=quality_report.to_payload(),
                        portfolio_context=portfolio_context,
                    )
                run.model_name = committee_result.model_name
                run.prompt_versions_json = committee_result.prompt_versions
                run.input_snapshot_json = committee_result.shared_input_snapshot
                proposal = committee.propose(
                    *committee_result.specialist_signals,
                    chair_summary=committee_result.chair_summary,
                ).model_copy(
                    update={
                        "model_name": committee_result.model_name,
                        "prompt_versions": committee_result.prompt_versions,
                    }
                )
                if execution_support.supported_for_execution is None:
                    risk_result = RiskCheckResult(
                        decision=RiskDecision.REJECTED,
                        approved_quantity=0,
                        notes=[executor_block_reason] if executor_block_reason else [],
                    )
                else:
                    cooldown_active, cooldown_notes = portfolio_risk.active_cooldown(item.symbol, as_of=end)
                    risk_result = risk_engine.validate(
                        proposal,
                        equity=account.equity,
                        buying_power=account.buying_power,
                        open_positions=open_positions,
                        daily_loss_pct=max((-account.daily_pl / max(account.equity, 1)), 0),
                        active_symbol_exposure=execution.current_symbol_exposure(item.symbol),
                        is_symbol_in_cooldown=cooldown_active,
                        portfolio_exposure=runtime_metrics.portfolio_exposure,
                        positions=runtime_metrics.positions,
                        feature_snapshot=feature_snapshot,
                        structured_events=structured_event_payload,
                        equity_drawdown_pct=runtime_metrics.equity_drawdown_pct,
                        loss_streak=runtime_metrics.loss_streak,
                        recent_execution_failures=runtime_metrics.recent_execution_failures,
                        pretrade_notes=cooldown_notes,
                        execution_quality_feedback=execution_feedback,
                    )
                decision = committee.finalize(proposal, risk_result=risk_result)
                decision_payload = _decision_payload(
                    decision=decision,
                    feature_snapshot=feature_snapshot,
                    data_quality_payload=quality_report.to_payload(),
                    data_timestamps=quality_report.data_timestamps,
                    structured_events=structured_event_payload,
                    index_context=index_context,
                    committee_metadata=committee_result.to_payload(),
                )

                session.add(
                    TradeCandidate(
                        profile_id=settings_row.id,
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
                        raw_payload=decision_payload,
                    )
                )
                run.status = RunStatus.SUCCEEDED
                run.finished_at = datetime.now(UTC)
                run.decision_payload = decision_payload
                session.commit()

                if decision.status.value == "approved":
                    intent = execution.queue_trade_intent(
                        settings_row=settings_row,
                        run_id=run.id,
                        decision=decision,
                        decision_context=decision_payload,
                        risk_result=risk_result,
                        execution_allowed=execution_support.supported_for_execution is not None,
                        block_reason=executor_block_reason,
                    )
                    if intent.status.value == "approved":
                        enqueue_execution_intent(intent.id)
                    open_positions += 1
                    runtime_metrics.portfolio_exposure += risk_result.approved_quantity * decision.entry
                    runtime_metrics.positions.append(
                        PositionExposure(
                            symbol=decision.symbol,
                            market_value=risk_result.approved_quantity * decision.entry,
                            side="long",
                        )
                    )
                    queued += 1
                    observe_counter("decision.approved")
                else:
                    session.add(
                        RiskEvent(
                            profile_id=settings_row.id,
                            symbol=item.symbol,
                            severity="warning",
                            code="trade_rejected",
                            message=decision.reject_reason or "Committee or risk policy rejected the trade.",
                            payload={"notes": decision.risk_notes},
                        )
                    )
                    observe_counter("decision.rejected", tags={"reason": "risk_or_committee"})
                    session.commit()
            except AgentOutputError as exc:
                rejection_notes = [
                    f"Malformed committee output from role {exc.role}.",
                    exc.invocation.error_message or "Agent output validation failed after repair.",
                ]
                agent_reject = _agent_rejection_decision(
                    symbol=item.symbol,
                    feature_snapshot=feature_snapshot,
                    notes=rejection_notes,
                ).model_copy(
                    update={
                        "model_name": agent_runner.model_name,
                        "prompt_versions": {exc.invocation.prompt_key: exc.invocation.prompt_version},
                    }
                )
                agent_payload = _decision_payload(
                    decision=agent_reject,
                    feature_snapshot=feature_snapshot,
                    data_quality_payload=quality_report.to_payload(),
                    data_timestamps=quality_report.data_timestamps,
                    structured_events=structured_event_payload,
                    index_context=index_context,
                    committee_metadata={
                        "model_name": agent_runner.model_name,
                        "prompt_versions": {exc.invocation.prompt_key: exc.invocation.prompt_version},
                        "failed_invocation": exc.invocation.to_payload(),
                    },
                )
                run.status = RunStatus.SUCCEEDED
                run.finished_at = datetime.now(UTC)
                run.model_name = agent_runner.model_name
                run.prompt_versions_json = {exc.invocation.prompt_key: exc.invocation.prompt_version}
                run.input_snapshot_json = exc.invocation.input_snapshot
                run.decision_payload = agent_payload
                session.add(
                    TradeCandidate(
                        profile_id=settings_row.id,
                        run_id=run.id,
                        symbol=agent_reject.symbol,
                        direction=agent_reject.direction,
                        confidence=agent_reject.confidence,
                        status=agent_reject.status.value,
                        thesis=agent_reject.thesis,
                        entry=agent_reject.entry,
                        stop_loss=agent_reject.stop_loss,
                        take_profit=agent_reject.take_profit,
                        risk_notes=agent_reject.risk_notes,
                        raw_payload=agent_payload,
                    )
                )
                session.add(
                    RiskEvent(
                        profile_id=settings_row.id,
                        symbol=item.symbol,
                        severity="warning",
                        code="agent_output_malformed",
                        message="Committee processing rejected the trade because a specialist payload stayed malformed after repair.",
                        payload={"role": exc.role, "invocation": exc.invocation.to_payload()},
                    )
                )
                observe_counter("agent.output_malformed")
                session.commit()
            except Exception as exc:  # noqa: BLE001
                run.status = RunStatus.FAILED
                run.finished_at = datetime.now(UTC)
                run.error_message = str(exc)
                session.add(
                    RiskEvent(
                        profile_id=settings_row.id,
                        symbol=item.symbol,
                        severity="critical",
                        code="scan_failure",
                        message="Market scan failed for symbol.",
                        payload={"error": str(exc)},
                    )
                )
                observe_counter("worker.market_scan.symbol_failures")
                session.commit()

        repaired_children = execution.repair_broken_child_orders()
        post_report = reconciliation.reconcile()
        AlertService(session, profile_id=settings_row.id).evaluate_runtime_alerts()
        session.commit()

        observe_counter("worker.market_scan.completed")
        return {
            "queued": queued,
            "repaired_children": repaired_children,
            "unresolved_mismatches": post_report.unresolved_mismatches,
        }
    except Exception:
        observe_counter("worker.market_scan.failures")
        raise
    finally:
        observe_duration_ms("worker.market_scan.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()


@celery_app.task(name="tradingbot.worker.tasks.run_reconciliation")
def run_reconciliation(profile_id: int | None = None) -> dict[str, int]:
    started = perf_counter()
    observe_counter("worker.reconciliation.invocations")
    session = get_session_factory()()
    try:
        settings_row = ensure_bot_settings(session, profile_id=profile_id)
        broker = build_broker_adapter(session, settings_row)
        execution = ExecutionService(session, broker, settings_row)
        service = ReconciliationService(
            session=session,
            settings_row=settings_row,
            execution=execution,
            adapter=broker,
        )
        report = service.reconcile()
        AlertService(session, profile_id=settings_row.id).evaluate_runtime_alerts()
        session.commit()
        observe_counter("worker.reconciliation.completed")
        return {
            "transitions_applied": report.transitions_applied,
            "fills_ingested": report.fills_ingested,
            "mismatches_created": report.mismatches_created,
            "unresolved_mismatches": report.unresolved_mismatches,
            "live_paused": int(report.live_paused),
        }
    except Exception:
        observe_counter("worker.reconciliation.failures")
        raise
    finally:
        observe_duration_ms("worker.reconciliation.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()


@celery_app.task(name="tradingbot.worker.tasks.run_backtest")
def run_backtest(payload: dict) -> dict[str, int]:
    started = perf_counter()
    observe_counter("worker.backtest.invocations")
    request = BacktestRequest.model_validate(payload)
    report_id = str(payload.get("report_id", "")).strip() or None
    session = get_session_factory()()
    try:
        now = datetime.now(UTC)
        report = session.get(BacktestReport, report_id) if report_id else None
        if report is not None:
            report.status = "running"
            report.started_at = now
            report.error_message = None
            session.commit()

        settings_row = ensure_bot_settings(session, profile_id=request.profile_id)
        market_data = build_market_data_adapter(settings_row)
        news_data = build_news_adapter(settings_row)
        service = BacktestService(market_data, news_data)
        trading_profile = serialize_trading_profile(settings_row)
        simulation_config = BacktestSimulationConfig(
            initial_equity=request.initial_equity,
            slippage_bps=request.slippage_bps,
            commission_per_share=request.commission_per_share,
            fill_delay_bars=request.fill_delay_bars,
            reject_probability=request.reject_probability,
            max_holding_bars=request.max_holding_bars,
            random_seed=request.random_seed,
        )
        result = service.run_research(
            symbols=request.symbols,
            start=request.start,
            end=request.end,
            interval_minutes=request.interval_minutes,
            trading_profile=trading_profile,
            config=simulation_config,
        )

        if report is None:
            report = BacktestReport(
                profile_id=settings_row.id,
                symbols=request.symbols,
                start_at=request.start,
                end_at=request.end,
                interval_minutes=request.interval_minutes,
                initial_equity=request.initial_equity,
                slippage_bps=request.slippage_bps,
                commission_per_share=request.commission_per_share,
                fill_delay_bars=request.fill_delay_bars,
                reject_probability=request.reject_probability,
                max_holding_bars=request.max_holding_bars,
                random_seed=request.random_seed,
            )
            session.add(report)
            session.flush()

        summary = result.metrics
        report.status = "succeeded"
        report.finished_at = datetime.now(UTC)
        report.total_trades = int(summary["total_trades"])
        report.rejected_orders = int(summary["rejected_orders"])
        report.final_equity = float(summary["final_equity"])
        report.total_return_pct = float(summary["total_return_pct"])
        report.win_rate = float(summary["win_rate"])
        report.expectancy = float(summary["expectancy"])
        report.sharpe_ratio = float(summary["sharpe_ratio"])
        report.max_drawdown_pct = float(summary["max_drawdown_pct"])
        report.turnover = float(summary["turnover"])
        report.avg_exposure_pct = float(summary["avg_exposure_pct"])
        report.max_exposure_pct = float(summary["max_exposure_pct"])
        report.metrics_json = result.metrics
        report.walk_forward_json = result.walk_forward
        report.regime_breakdown_json = result.regime_breakdown
        report.equity_curve_json = result.equity_curve_payload()
        report.symbol_breakdown_json = result.symbol_breakdown
        report.error_message = None

        session.query(BacktestTrade).filter(BacktestTrade.report_id == report.id).delete(synchronize_session=False)
        for item in result.trades:
            session.add(
                BacktestTrade(
                    profile_id=settings_row.id,
                    report_id=report.id,
                    symbol=item.symbol,
                    status=item.status,
                    regime=item.regime,
                    signal_at=item.signal_at,
                    entry_at=item.entry_at,
                    exit_at=item.exit_at,
                    quantity=item.quantity,
                    holding_bars=item.holding_bars,
                    entry_price=item.entry_price,
                    exit_price=item.exit_price,
                    gross_pnl=item.gross_pnl,
                    net_pnl=item.net_pnl,
                    return_pct=item.return_pct,
                    commission_paid=item.commission_paid,
                    slippage_paid=item.slippage_paid,
                    notes=item.notes,
                )
            )
        session.commit()
        observe_counter("worker.backtest.completed")
        return {"runs": report.total_trades, "rejected_orders": report.rejected_orders}
    except Exception as exc:  # noqa: BLE001
        observe_counter("worker.backtest.failures")
        if report_id:
            report = session.get(BacktestReport, report_id)
            if report is not None:
                report.status = "failed"
                report.finished_at = datetime.now(UTC)
                report.error_message = str(exc)
                session.commit()
        raise
    finally:
        observe_duration_ms("worker.backtest.latency_ms", duration_ms=(perf_counter() - started) * 1000)
        session.close()
