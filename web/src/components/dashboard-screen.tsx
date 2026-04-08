"use client";

import Link from "next/link";
import { type FormEvent, startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  approveExecutionIntent,
  brokerKill,
  cancelAllOrders,
  cancelOrder,
  disableLiveExecution,
  enableLiveExecution,
  flattenAllPositions,
  getBacktestReport,
  getCurrentSession,
  getPerformanceSummary,
  listExecutionQualitySamples,
  listExecutionQualitySummary,
  getSettings,
  listAlerts,
  launchBacktest,
  listAuditLogs,
  listBacktests,
  listDecisions,
  listExecutionIntents,
  listOrderFills,
  listOrderTransitions,
  listOrders,
  listPositions,
  listReconciliationMismatches,
  listRiskEvents,
  listRuns,
  listSessions,
  login,
  logout,
  prepareLiveEnablement,
  rejectExecutionIntent,
  revokeSession,
  runReconciliation,
  startBot,
  stopBot,
  switchMode,
  toggleKillSwitch,
  updateSettings
} from "@/lib/api";
import type {
  AuditLogResponse,
  BacktestDetailResponse,
  BacktestRequestPayload,
  BacktestSummaryResponse,
  BotSettingsResponse,
  BotSettingsUpdatePayload,
  BrokerSettings,
  CommitteeDecision,
  ExecutionQualitySampleResponse,
  ExecutionQualitySummaryResponse,
  ExecutionIntentResponse,
  LiveEnablePrepareResponse,
  LoginResponse,
  OrderStatus,
  OrderFillResponse,
  OrderResponse,
  OrderTransitionResponse,
  PerformanceSummaryResponse,
  PositionResponse,
  ReconciliationMismatchResponse,
  RiskEventResponse,
  SessionResponse,
  RunResponse,
  TradingProfile
} from "@/lib/contracts";
import { AgentIntake } from "@/components/agent-intake";
import { currency, percent, timestamp } from "@/lib/format";
import {
  brokerOptions,
  executionSupportCopy,
  instrumentOptions,
  marketUniverseOptions,
  optionLabel,
  riskProfileOptions,
  strategyFamilyOptions,
  tradingPatternOptions
} from "@/lib/trading-profile";

type SectionName = "overview" | "orders" | "decisions" | "risk" | "backtests" | "settings";
type ExecutionSummaryDimension = "symbol" | "venue" | "broker" | "order_type";
type ExecutionSampleStatusFilter = "all" | OrderStatus;

const executionSummaryDimensionOptions: Array<{ value: ExecutionSummaryDimension; label: string }> = [
  { value: "symbol", label: "Symbol" },
  { value: "venue", label: "Venue" },
  { value: "broker", label: "Broker" },
  { value: "order_type", label: "Order type" }
];

const executionSummaryDimensionLabels: Record<ExecutionSummaryDimension, string> = {
  symbol: "Symbol",
  venue: "Venue",
  broker: "Broker",
  order_type: "Order type"
};

const executionSampleStatusOptions: OrderStatus[] = [
  "new",
  "accepted",
  "pending_trigger",
  "partially_filled",
  "filled",
  "canceled",
  "expired",
  "replaced",
  "rejected",
  "suspended"
];

interface ExecutionQualityFilters {
  summaryDimension: ExecutionSummaryDimension;
  summaryLimit: number;
  sampleSymbol: string;
  sampleStatus: ExecutionSampleStatusFilter;
  sampleLimit: number;
}

function defaultExecutionQualityFilters(): ExecutionQualityFilters {
  return {
    summaryDimension: "symbol",
    summaryLimit: 8,
    sampleSymbol: "",
    sampleStatus: "all",
    sampleLimit: 12
  };
}

const sections: Array<{ href: string; label: string; key: SectionName }> = [
  { href: "/", label: "Overview", key: "overview" },
  { href: "/orders", label: "Orders", key: "orders" },
  { href: "/decisions", label: "Decisions", key: "decisions" },
  { href: "/risk", label: "Risk", key: "risk" },
  { href: "/backtests", label: "Backtests", key: "backtests" },
  { href: "/settings", label: "Settings", key: "settings" }
];

interface Props {
  section: SectionName;
}

interface BacktestDraft {
  symbols: string;
  start: string;
  end: string;
  interval_minutes: number;
  initial_equity: number;
  slippage_bps: number;
  commission_per_share: number;
  fill_delay_bars: number;
  reject_probability: number;
  max_holding_bars: number;
  random_seed: number;
}

function toLocalDateTimeInput(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  const hours = String(value.getHours()).padStart(2, "0");
  const minutes = String(value.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function buildBacktestPayload(draft: BacktestDraft): BacktestRequestPayload {
  return {
    symbols: draft.symbols
      .split(",")
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean),
    start: new Date(draft.start).toISOString(),
    end: new Date(draft.end).toISOString(),
    interval_minutes: draft.interval_minutes,
    initial_equity: draft.initial_equity,
    slippage_bps: draft.slippage_bps,
    commission_per_share: draft.commission_per_share,
    fill_delay_bars: draft.fill_delay_bars,
    reject_probability: draft.reject_probability,
    max_holding_bars: draft.max_holding_bars,
    random_seed: draft.random_seed
  };
}

function buildSettingsPayload(draft: BotSettingsResponse): BotSettingsUpdatePayload {
  return {
    scan_interval_minutes: draft.scan_interval_minutes,
    consensus_threshold: draft.consensus_threshold,
    max_open_positions: draft.max_open_positions,
    max_daily_loss_pct: draft.max_daily_loss_pct,
    max_position_risk_pct: draft.max_position_risk_pct,
    max_symbol_notional_pct: draft.max_symbol_notional_pct,
    max_gross_exposure_pct: draft.max_gross_exposure_pct,
    max_sector_exposure_pct: draft.max_sector_exposure_pct,
    max_correlation_exposure_pct: draft.max_correlation_exposure_pct,
    max_event_cluster_positions: draft.max_event_cluster_positions,
    volatility_target_pct: draft.volatility_target_pct,
    atr_sizing_multiplier: draft.atr_sizing_multiplier,
    equity_curve_throttle_start_pct: draft.equity_curve_throttle_start_pct,
    equity_curve_throttle_min_scale: draft.equity_curve_throttle_min_scale,
    intraday_drawdown_pause_pct: draft.intraday_drawdown_pause_pct,
    loss_streak_reduction_threshold: draft.loss_streak_reduction_threshold,
    loss_streak_size_scale: draft.loss_streak_size_scale,
    execution_failure_review_threshold: draft.execution_failure_review_threshold,
    severe_anomaly_kill_switch_threshold: draft.severe_anomaly_kill_switch_threshold,
    symbol_cooldown_minutes: draft.symbol_cooldown_minutes,
    symbol_cooldown_profit_minutes: draft.symbol_cooldown_profit_minutes,
    symbol_cooldown_stopout_minutes: draft.symbol_cooldown_stopout_minutes,
    symbol_cooldown_event_minutes: draft.symbol_cooldown_event_minutes,
    symbol_cooldown_whipsaw_minutes: draft.symbol_cooldown_whipsaw_minutes,
    openai_model: draft.openai_model,
    watchlist: draft.watchlist,
    broker_settings: draft.broker_settings,
    selected_for_analysis: draft.selected_for_analysis
  };
}

function renderProfileScope(profile: TradingProfile | null | undefined) {
  if (!profile) {
    return <p className="muted">No execution profile is currently supported for the selected broker scope.</p>;
  }

  return (
    <div className="profile-summary-grid">
      <div className="summary-pill">
        <span>Pattern</span>
        <strong>{optionLabel(tradingPatternOptions, profile.trading_pattern)}</strong>
      </div>
      <div className="summary-pill">
        <span>Instrument</span>
        <strong>{optionLabel(instrumentOptions, profile.instrument_class)}</strong>
      </div>
      <div className="summary-pill">
        <span>Strategy</span>
        <strong>{optionLabel(strategyFamilyOptions, profile.strategy_family)}</strong>
      </div>
      <div className="summary-pill">
        <span>Risk</span>
        <strong>{optionLabel(riskProfileOptions, profile.risk_profile)}</strong>
      </div>
      <div className="summary-pill">
        <span>Universe</span>
        <strong>{optionLabel(marketUniverseOptions, profile.market_universe)}</strong>
      </div>
    </div>
  );
}

export function DashboardScreen({ section }: Props) {
  const [operator, setOperator] = useState<LoginResponse | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [flash, setFlash] = useState<{ tone: "error" | "info"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filterInput, setFilterInput] = useState("");
  const [settingsDraft, setSettingsDraft] = useState<BotSettingsResponse | null>(null);
  const [settingsData, setSettingsData] = useState<BotSettingsResponse | null>(null);
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [decisions, setDecisions] = useState<CommitteeDecision[]>([]);
  const [executionIntents, setExecutionIntents] = useState<ExecutionIntentResponse[]>([]);
  const [orders, setOrders] = useState<OrderResponse[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [orderTransitions, setOrderTransitions] = useState<OrderTransitionResponse[]>([]);
  const [orderFills, setOrderFills] = useState<OrderFillResponse[]>([]);
  const [positions, setPositions] = useState<PositionResponse[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEventResponse[]>([]);
  const [alerts, setAlerts] = useState<RiskEventResponse[]>([]);
  const [performanceSummary, setPerformanceSummary] = useState<PerformanceSummaryResponse | null>(null);
  const [executionQualitySamples, setExecutionQualitySamples] = useState<ExecutionQualitySampleResponse[]>([]);
  const [executionQualitySummary, setExecutionQualitySummary] = useState<ExecutionQualitySummaryResponse[]>([]);
  const [executionFilters, setExecutionFilters] = useState<ExecutionQualityFilters>(() => defaultExecutionQualityFilters());
  const [executionFilterDraft, setExecutionFilterDraft] = useState<ExecutionQualityFilters>(() =>
    defaultExecutionQualityFilters()
  );
  const [mismatches, setMismatches] = useState<ReconciliationMismatchResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [backtests, setBacktests] = useState<BacktestSummaryResponse[]>([]);
  const [selectedBacktestId, setSelectedBacktestId] = useState<string | null>(null);
  const [selectedBacktest, setSelectedBacktest] = useState<BacktestDetailResponse | null>(null);
  const [backtestDraft, setBacktestDraft] = useState<BacktestDraft>(() => {
    const end = new Date();
    const start = new Date(end.getTime() - 5 * 24 * 60 * 60 * 1000);
    return {
      symbols: "AAPL, MSFT, NVDA",
      start: toLocalDateTimeInput(start),
      end: toLocalDateTimeInput(end),
      interval_minutes: 5,
      initial_equity: 100000,
      slippage_bps: 5,
      commission_per_share: 0.005,
      fill_delay_bars: 1,
      reject_probability: 0.03,
      max_holding_bars: 24,
      random_seed: 42
    };
  });
  const [liveApproval, setLiveApproval] = useState<LiveEnablePrepareResponse | null>(null);
  const [liveApprovalCode, setLiveApprovalCode] = useState("");
  const deferredFilter = useDeferredValue(filterInput.trim().toLowerCase());

  const canOperate = operator?.role === "operator" || operator?.role === "admin";
  const isAdmin = operator?.role === "admin";

  function clearDashboardState() {
    setSettingsDraft(null);
    setSettingsData(null);
    setRuns([]);
    setDecisions([]);
    setExecutionIntents([]);
    setOrders([]);
    setSelectedOrderId(null);
    setOrderTransitions([]);
    setOrderFills([]);
    setPositions([]);
    setRiskEvents([]);
    setAlerts([]);
    setPerformanceSummary(null);
    setExecutionQualitySamples([]);
    setExecutionQualitySummary([]);
    const defaults = defaultExecutionQualityFilters();
    setExecutionFilters(defaults);
    setExecutionFilterDraft(defaults);
    setMismatches([]);
    setAuditLogs([]);
    setSessions([]);
    setBacktests([]);
    setSelectedBacktestId(null);
    setSelectedBacktest(null);
    setLiveApproval(null);
    setLiveApprovalCode("");
  }

  function describeError(error: unknown) {
    return error instanceof Error ? error.message : "Request failed.";
  }

  async function handleApiError(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      setOperator(null);
      clearDashboardState();
      setFlash({ tone: "error", text: "Session expired. Sign in again." });
      return;
    }
    setFlash({ tone: "error", text: describeError(error) });
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const session = await getCurrentSession();
        if (!cancelled) {
          setOperator(session);
        }
      } catch (error) {
        if (!cancelled && !(error instanceof ApiError && error.status === 401)) {
          setFlash({ tone: "error", text: describeError(error) });
        }
      } finally {
        if (!cancelled) {
          setAuthChecked(true);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  async function loadOrderLifecycle(orderId: number | null) {
    if (!orderId) {
      setOrderTransitions([]);
      setOrderFills([]);
      return;
    }
    const [transitions, fills] = await Promise.all([listOrderTransitions(orderId), listOrderFills(orderId)]);
    setOrderTransitions(transitions);
    setOrderFills(fills);
  }

  async function loadBacktestDetail(reportId: string | null) {
    if (!reportId) {
      setSelectedBacktest(null);
      return;
    }
    const detail = await getBacktestReport(reportId);
    setSelectedBacktest(detail);
  }

  async function loadDashboardData(resetDraft = false) {
    const [
      settingsResponse,
      runsResponse,
      decisionsResponse,
      executionIntentResponse,
      ordersResponse,
      positionsResponse,
      riskResponse,
      alertsResponse,
      performanceResponse,
      executionQualitySamplesResponse,
      executionQualitySummaryResponse,
      mismatchesResponse,
      auditResponse,
      sessionResponse,
      backtestsResponse
    ] = await Promise.all([
      getSettings(),
      listRuns(),
      listDecisions(),
      listExecutionIntents(undefined, 24),
      listOrders(),
      listPositions(),
      listRiskEvents(),
      listAlerts(16),
      getPerformanceSummary(60),
      listExecutionQualitySamples(
        executionFilters.sampleSymbol || undefined,
        executionFilters.sampleStatus === "all" ? undefined : executionFilters.sampleStatus,
        executionFilters.sampleLimit
      ),
      listExecutionQualitySummary(executionFilters.summaryDimension, executionFilters.summaryLimit),
      listReconciliationMismatches(),
      listAuditLogs(24),
      listSessions(),
      listBacktests(undefined, 24)
    ]);

    setSettingsData(settingsResponse);
    setSettingsDraft((current) => (resetDraft || current === null ? settingsResponse : current));
    setRuns(runsResponse);
    setDecisions(decisionsResponse);
    setExecutionIntents(executionIntentResponse);
    setOrders(ordersResponse);
    setPositions(positionsResponse);
    setRiskEvents(riskResponse);
    setAlerts(alertsResponse);
    setPerformanceSummary(performanceResponse);
    setExecutionQualitySamples(executionQualitySamplesResponse);
    setExecutionQualitySummary(executionQualitySummaryResponse);
    setMismatches(mismatchesResponse);
    setAuditLogs(auditResponse);
    setSessions(sessionResponse);
    setBacktests(backtestsResponse);

    const nextSelectedOrderId = ordersResponse.some((order) => order.id === selectedOrderId)
      ? selectedOrderId
      : ordersResponse[0]?.id ?? null;
    setSelectedOrderId(nextSelectedOrderId);
    await loadOrderLifecycle(nextSelectedOrderId);

    const nextBacktestId = backtestsResponse.some((report) => report.id === selectedBacktestId)
      ? selectedBacktestId
      : backtestsResponse[0]?.id ?? null;
    setSelectedBacktestId(nextBacktestId);
    await loadBacktestDetail(nextBacktestId);
  }

  useEffect(() => {
    if (!operator) {
      return;
    }

    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        await loadDashboardData();
        if (cancelled) {
          return;
        }
      } catch (error) {
        if (!cancelled) {
          await handleApiError(error);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    const interval = window.setInterval(load, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [operator, selectedOrderId, selectedBacktestId, executionFilters]);

  const filteredOrders = useMemo(() => {
    if (!deferredFilter) {
      return orders;
    }
    return orders.filter(
      (order) =>
        order.symbol.toLowerCase().includes(deferredFilter) ||
        order.status.toLowerCase().includes(deferredFilter)
    );
  }, [deferredFilter, orders]);

  const filteredDecisions = useMemo(() => {
    if (!deferredFilter) {
      return decisions;
    }
    return decisions.filter(
      (decision) =>
        decision.symbol.toLowerCase().includes(deferredFilter) ||
        decision.thesis.toLowerCase().includes(deferredFilter)
    );
  }, [decisions, deferredFilter]);

  const selectedOrder = useMemo(
    () => orders.find((order) => order.id === selectedOrderId) ?? null,
    [orders, selectedOrderId]
  );

  const executionSummaryKeyLabel = executionSummaryDimensionLabels[executionFilters.summaryDimension];

  function canCancel(status: string) {
    return ["new", "accepted", "pending_trigger", "partially_filled", "suspended"].includes(status);
  }

  function selectOrder(orderId: number) {
    setSelectedOrderId(orderId);
    void loadOrderLifecycle(orderId);
  }

  function selectBacktest(reportId: string) {
    setSelectedBacktestId(reportId);
    void loadBacktestDetail(reportId);
  }

  async function refreshNow(resetDraft = false) {
    if (!operator) {
      return;
    }
    setLoading(true);
    try {
      await loadDashboardData(resetDraft);
    } catch (error) {
      await handleApiError(error);
    } finally {
      setLoading(false);
    }
  }

  function applyExecutionQualityFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setExecutionFilters({
      summaryDimension: executionFilterDraft.summaryDimension,
      summaryLimit: Math.min(Math.max(Math.round(executionFilterDraft.summaryLimit), 1), 200),
      sampleSymbol: executionFilterDraft.sampleSymbol.trim().toUpperCase(),
      sampleStatus: executionFilterDraft.sampleStatus,
      sampleLimit: Math.min(Math.max(Math.round(executionFilterDraft.sampleLimit), 1), 500)
    });
  }

  function resetExecutionQualityFilters() {
    const defaults = defaultExecutionQualityFilters();
    setExecutionFilters(defaults);
    setExecutionFilterDraft(defaults);
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFlash(null);
    try {
      const response = await login(email, password);
      setOperator(response);
      setAuthChecked(true);
      setPassword("");
      await loadDashboardData(true);
    } catch (error) {
      await handleApiError(error);
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    try {
      await logout();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        await handleApiError(error);
      }
    } finally {
      setBusy(false);
      setOperator(null);
      clearDashboardState();
    }
  }

  function handleCommand(
    command: () => Promise<unknown>,
    options?: { refresh?: boolean; resetDraft?: boolean; success?: string }
  ) {
    setBusy(true);
    setFlash(null);
    startTransition(() => {
      command()
        .then(async () => {
          if (options?.success) {
            setFlash({ tone: "info", text: options.success });
          }
          if (options?.refresh === false) {
            return;
          }
          await refreshNow(Boolean(options?.resetDraft));
        })
        .catch(async (error) => handleApiError(error))
        .finally(() => setBusy(false));
    });
  }

  function updateTradingProfile<K extends keyof TradingProfile>(key: K, value: TradingProfile[K]) {
    setSettingsDraft((current) =>
      current
        ? {
            ...current,
            selected_for_analysis: {
              ...current.selected_for_analysis,
              [key]: value
            }
          }
        : current
    );
  }

  function updateBrokerSettings<K extends keyof BrokerSettings>(key: K, value: BrokerSettings[K]) {
    setSettingsDraft((current) =>
      current
        ? {
            ...current,
            broker_settings: {
              ...current.broker_settings,
              [key]: value
            }
          }
        : current
    );
  }

  function saveSettingsDraft() {
    if (!settingsDraft) {
      return Promise.resolve();
    }
    return updateSettings(buildSettingsPayload(settingsDraft));
  }

  async function handlePrepareLive() {
    setBusy(true);
    setFlash(null);
    try {
      const response = await prepareLiveEnablement();
      setLiveApproval(response);
      setLiveApprovalCode(response.approval_code);
      setFlash({ tone: "info", text: "Live enablement code generated. Confirm it below before live approval." });
      await refreshNow();
    } catch (error) {
      await handleApiError(error);
    } finally {
      setBusy(false);
    }
  }

  function handleEnableLive() {
    if (!liveApprovalCode.trim()) {
      setFlash({ tone: "error", text: "Enter the approval code before enabling live execution." });
      return;
    }
    handleCommand(() => enableLiveExecution(liveApprovalCode.trim()), {
      resetDraft: true,
      success: "Live execution enabled."
    });
    setLiveApproval(null);
  }

  function handleRejectIntent(intentId: string) {
    const detail = window.prompt("Reason for rejection", "Rejected by operator.");
    if (!detail) {
      return;
    }
    handleCommand(() => rejectExecutionIntent(intentId, detail), { success: "Execution intent rejected." });
  }

  function statusTone(status: string) {
    if (["approved", "executed", "running", "supported", "open"].includes(status)) {
      return "tag-positive";
    }
    if (["blocked", "failed", "rejected", "critical", "off"].includes(status)) {
      return "tag-negative";
    }
    return "tag-neutral";
  }

  async function handleLaunchBacktest() {
    setBusy(true);
    setFlash(null);
    try {
      const payload = buildBacktestPayload(backtestDraft);
      if (payload.symbols.length === 0) {
        setFlash({ tone: "error", text: "Enter at least one symbol for backtesting." });
        return;
      }
      if (new Date(payload.end).getTime() <= new Date(payload.start).getTime()) {
        setFlash({ tone: "error", text: "Backtest end must be after start." });
        return;
      }
      const response = await launchBacktest(payload);
      setFlash({ tone: "info", text: `Backtest queued. Report ${response.report_id}.` });
      await refreshNow();
    } catch (error) {
      await handleApiError(error);
    } finally {
      setBusy(false);
    }
  }

  if (!authChecked) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="eyebrow">AI Trading Bot</p>
          <h1>Loading operator console</h1>
          <p className="muted">Checking for an active secure session.</p>
        </section>
      </main>
    );
  }

  if (!operator) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="eyebrow">AI Trading Bot</p>
          <h1>Operator Console</h1>
          <p className="muted">
            Authenticate with a backend operator account. Sessions are stored in secure HTTP-only cookies.
          </p>
          <form className="login-form" onSubmit={handleLogin}>
            <label>
              Email
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
            </label>
            <label>
              Password
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
              />
            </label>
            <button className="primary-button" disabled={busy} type="submit">
              {busy ? "Signing in..." : "Enter console"}
            </button>
          </form>
          {flash ? <p className={flash.tone === "error" ? "error-text" : "info-text"}>{flash.text}</p> : null}
        </section>
      </main>
    );
  }

  const totalMarketValue = positions.reduce((total, position) => total + position.market_value, 0);
  const totalUnrealized = positions.reduce((total, position) => total + position.unrealized_pl, 0);
  const approvedDecisions = decisions.filter((decision) => decision.status === "approved").length;
  const unresolvedMismatchCount = mismatches.filter((item) => !item.resolved).length;
  const pendingIntentCount = executionIntents.filter((intent) => intent.status === "pending_approval").length;
  const intakeRequired = Boolean(settingsData && !settingsData.strategy_profile_completed);
  const supportState = settingsData ? executionSupportCopy[settingsData.execution_support_status] : null;
  const liveStartBlocked = Boolean(settingsData?.mode === "live" && !settingsData.live_start_allowed);
  const switchingToLive = settingsData?.mode === "paper";
  const selectedPattern = settingsData
    ? optionLabel(tradingPatternOptions, settingsData.selected_for_analysis.trading_pattern)
    : "Not selected";
  const selectedInstrument = settingsData
    ? optionLabel(instrumentOptions, settingsData.selected_for_analysis.instrument_class)
    : "Not selected";
  const selectedBroker = settingsData
    ? optionLabel(brokerOptions, settingsData.broker_settings.broker)
    : "Not selected";
  const marketSession = settingsData?.market_session;
  const startButtonLabel = !canOperate
    ? "Reviewer access"
    : intakeRequired
      ? "Complete intake first"
      : settingsData?.mode === "live" && !settingsData.live_enabled
        ? "Start review loop"
        : settingsData?.execution_support_status === "analysis_only_for_selected_broker"
          ? "Start analysis mode"
          : "Start bot";

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <div>
          <p className="eyebrow">AI Trading Bot</p>
          <h1>Pattern-aware agent ops</h1>
          <p className="sidebar-copy">
            The system begins with an agent intake so the workflow aligns to the user's selected trading style.
          </p>
        </div>

        <div className="status-stack">
          <div className="status-pill">
            <span>Bot</span>
            <strong>{settingsData?.status ?? "loading"}</strong>
          </div>
          <div className="status-pill">
            <span>Broker</span>
            <strong>{selectedBroker}</strong>
          </div>
          <div className="status-pill">
            <span>Pattern</span>
            <strong>{selectedPattern}</strong>
          </div>
          <div className="status-pill">
            <span>Instrument</span>
            <strong>{selectedInstrument}</strong>
          </div>
          <div className="status-pill">
            <span>Session</span>
            <strong>{marketSession?.status ?? "loading"}</strong>
          </div>
          <div className="status-pill">
            <span>Live gate</span>
            <strong>{settingsData?.live_enabled ? "armed" : "manual"}</strong>
          </div>
          <div className="status-pill">
            <span>Kill switch</span>
            <strong>{settingsData?.kill_switch_enabled ? "armed" : "off"}</strong>
          </div>
          <div className="status-pill">
            <span>Role</span>
            <strong>{operator.role}</strong>
          </div>
        </div>

        <div className="command-stack">
          <button
            className="primary-button"
            disabled={busy || !canOperate || intakeRequired || liveStartBlocked}
            onClick={() => handleCommand(() => startBot(), { success: "Bot started." })}
          >
            {startButtonLabel}
          </button>
          <button
            className="secondary-button"
            disabled={busy || !canOperate}
            onClick={() => handleCommand(() => stopBot(), { success: "Bot stopped." })}
          >
            Stop bot
          </button>
          <button
            className="ghost-button"
            disabled={
              busy ||
              !settingsData ||
              !canOperate ||
              intakeRequired ||
              Boolean(switchingToLive && !settingsData.live_start_allowed)
            }
            onClick={() =>
              handleCommand(() => switchMode(settingsData?.mode === "paper" ? "live" : "paper"), {
                success: "Bot mode updated."
              })
            }
          >
            {switchingToLive && !settingsData?.live_start_allowed ? "Live mode blocked" : "Flip mode"}
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData || !canOperate}
            onClick={() =>
              handleCommand(() => toggleKillSwitch(!settingsData.kill_switch_enabled), {
                success: "Kill switch updated."
              })
            }
          >
            Toggle kill switch
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData || !canOperate}
            onClick={() => handleCommand(() => runReconciliation(), { success: "Reconciliation finished." })}
          >
            Reconcile now
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData || !canOperate}
            onClick={() => handleCommand(() => cancelAllOrders(), { success: "Cancel-all request submitted." })}
          >
            Cancel all open orders
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData || !canOperate}
            onClick={() => handleCommand(() => flattenAllPositions(), { success: "Flatten-all request submitted." })}
          >
            Flatten all
          </button>
          <button className="secondary-button" disabled={busy} onClick={() => void handleLogout()}>
            Sign out
          </button>
        </div>

        <nav className="section-nav">
          {sections.map((item) => (
            <Link
              key={item.key}
              className={item.key === section ? "nav-link active" : "nav-link"}
              href={item.href}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Operator surface</p>
            <h2>{intakeRequired ? "Agent intake" : sections.find((item) => item.key === section)?.label}</h2>
          </div>
          <div className="header-actions">
            <div className="account-chip">
              <strong>{operator.email}</strong>
              <span>
                {operator.role} | expires {timestamp(operator.expires_at)}
              </span>
            </div>
            <input
              className="filter-input"
              placeholder="Filter by symbol, thesis, or status"
              value={filterInput}
              onChange={(event) => setFilterInput(event.target.value)}
            />
            <button className="secondary-button" disabled={loading} onClick={() => void refreshNow()}>
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </header>

        {supportState ? (
          <section
            className={
              settingsData?.execution_support_status === "broker_execution_supported"
                ? "support-banner positive"
                : "support-banner"
            }
          >
            <strong>{supportState.title}</strong>
            <p>{supportState.description}</p>
            {settingsData?.analysis_only_downgrade_reason ? <p>{settingsData.analysis_only_downgrade_reason}</p> : null}
          </section>
        ) : null}

        {settingsData?.mode === "live" && !settingsData.live_enabled ? (
          <section className="support-banner">
            <strong>Live mode still requires manual approval</strong>
            <p>
              The system can analyze and queue intents in live mode, but an admin must generate and confirm a live-enable code before approvals can route orders.
            </p>
          </section>
        ) : null}

        {!intakeRequired ? (
        <section className="metric-row">
          <article className="metric-block">
            <span>Gross market value</span>
            <strong>{currency(totalMarketValue)}</strong>
          </article>
          <article className="metric-block">
            <span>Unrealized P/L</span>
            <strong>{currency(totalUnrealized)}</strong>
          </article>
          <article className="metric-block">
            <span>Approved setups</span>
            <strong>{approvedDecisions}</strong>
          </article>
          <article className="metric-block">
            <span>Pending intents</span>
            <strong>{pendingIntentCount}</strong>
          </article>
          <article className="metric-block">
            <span>Recon mismatches</span>
            <strong>{unresolvedMismatchCount}</strong>
          </article>
        </section>
        ) : null}

        {intakeRequired && settingsDraft ? (
          <AgentIntake
            profile={settingsDraft.selected_for_analysis}
            brokerSettings={settingsDraft.broker_settings}
            brokerCapabilityMatrix={settingsDraft.broker_capability_matrix}
            onChange={updateTradingProfile}
            onBrokerChange={updateBrokerSettings}
            title="First question set for the AI agents"
            description="Choose the broker scope and trading profile first. After this is saved, the agents will use those instructions before generating setups or performing tasks."
          />
        ) : null}

        {intakeRequired && settingsDraft ? (
          <button
            className="primary-button"
            disabled={busy || !isAdmin}
            onClick={() => handleCommand(() => saveSettingsDraft(), { resetDraft: true, success: "Settings saved." })}
          >
            Save intake and unlock bot
          </button>
        ) : null}

        {!intakeRequired && section === "overview" ? (
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h3>Analysis vs execution scope</h3>
                <p>The selected research brief is stored separately from what the current broker can actually execute.</p>
              </div>
              <div className="scope-grid">
                <article className="scope-card">
                  <h4>Selected for analysis</h4>
                  {renderProfileScope(settingsData?.selected_for_analysis)}
                </article>
                <article className="scope-card">
                  <h4>Supported for execution</h4>
                  {renderProfileScope(settingsData?.supported_for_execution)}
                </article>
              </div>
              {settingsData?.selected_for_analysis.profile_notes ? (
                <p className="note-row">{settingsData.selected_for_analysis.profile_notes}</p>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Market session and live gate</h3>
                <p>Session-aware guardrails, timezone-aware trading windows, and live safety friction.</p>
              </div>
              <div className="profile-summary-grid">
                <div className="summary-pill">
                  <span>Session status</span>
                  <strong>{marketSession?.status ?? "unknown"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Scans</span>
                  <strong>{marketSession?.can_scan ? "enabled" : "blocked"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Order entry</span>
                  <strong>{marketSession?.can_submit_orders ? "enabled" : "blocked"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Half day</span>
                  <strong>{marketSession?.is_half_day ? "yes" : "no"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Environment allowlist</span>
                  <strong>{settingsData?.live_trading_env_allowed ? "allowed" : "blocked"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Live execution</span>
                  <strong>{settingsData?.live_enabled ? "enabled" : "manual"}</strong>
                </div>
              </div>
              <p className="muted broker-permissions">
                {marketSession?.reason ?? "The market calendar service is gating scans and submissions for the configured venue."}
              </p>
              <table className="data-table capability-table">
                <thead>
                  <tr>
                    <th>Checkpoint</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Session opens</td>
                    <td>{timestamp(marketSession?.session_opens_at ?? null)}</td>
                  </tr>
                  <tr>
                    <td>Session closes</td>
                    <td>{timestamp(marketSession?.session_closes_at ?? null)}</td>
                  </tr>
                  <tr>
                    <td>Next open</td>
                    <td>{timestamp(marketSession?.next_session_opens_at ?? null)}</td>
                  </tr>
                  <tr>
                    <td>Flatten on close</td>
                    <td>{marketSession?.should_flatten_positions ? "yes" : "no"}</td>
                  </tr>
                </tbody>
              </table>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Intent review queue</h3>
                <p>Decisioning is split from execution. Operators approve or reject intents before broker submission.</p>
              </div>
              <div className="decision-list">
                {executionIntents.slice(0, 6).map((intent) => {
                  const approvalBlocked = intent.mode === "live" && !settingsData?.live_enabled;
                  return (
                    <article className="decision-item" key={intent.id}>
                      <div className="decision-meta">
                        <strong>{intent.symbol ?? intent.intent_type}</strong>
                        <span className={statusTone(intent.status)}>{intent.status}</span>
                      </div>
                      <div className="decision-values">
                        <span>{intent.mode}</span>
                        <span>{intent.direction ?? intent.intent_type}</span>
                        <span>Qty {intent.quantity ?? 0}</span>
                        <span>{timestamp(intent.created_at)}</span>
                      </div>
                      {intent.block_reason ? <div className="note-row">{intent.block_reason}</div> : null}
                      {intent.last_error ? <div className="note-row">{intent.last_error}</div> : null}
                      {canOperate && intent.status === "pending_approval" ? (
                        <div className="inline-action-row">
                          <button
                            className="secondary-button inline-button"
                            disabled={busy || approvalBlocked}
                            onClick={() =>
                              handleCommand(() => approveExecutionIntent(intent.id), {
                                success: "Execution intent approved."
                              })
                            }
                          >
                            {approvalBlocked ? "Enable live first" : "Approve"}
                          </button>
                          <button
                            className="ghost-button inline-button"
                            disabled={busy}
                            onClick={() => handleRejectIntent(intent.id)}
                          >
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
                {executionIntents.length === 0 ? <p className="muted">No execution intents recorded yet.</p> : null}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Broker coverage</h3>
                <p>Configured broker metadata and the capability registry that gates live execution.</p>
              </div>
              <div className="profile-summary-grid">
                <div className="summary-pill">
                  <span>Broker</span>
                  <strong>{selectedBroker}</strong>
                </div>
                <div className="summary-pill">
                  <span>Account type</span>
                  <strong>{settingsData?.broker_settings.account_type}</strong>
                </div>
                <div className="summary-pill">
                  <span>Venue</span>
                  <strong>{settingsData?.broker_settings.venue}</strong>
                </div>
                <div className="summary-pill">
                  <span>Timezone</span>
                  <strong>{settingsData?.broker_settings.timezone}</strong>
                </div>
                <div className="summary-pill">
                  <span>Base currency</span>
                  <strong>{settingsData?.broker_settings.base_currency}</strong>
                </div>
              </div>
              <p className="muted broker-permissions">
                Permissions: {settingsData?.broker_settings.permissions.join(", ") || "None configured"}
              </p>
              <table className="data-table capability-table">
                <thead>
                  <tr>
                    <th>Capability</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {settingsData?.broker_capability_matrix.map((capability) => (
                    <tr key={capability.key}>
                      <td className="capability-cell">
                        <strong>{capability.label}</strong>
                        <span>{capability.description}</span>
                      </td>
                      <td>
                        <span className={capability.supported ? "tag-positive" : "tag-negative"}>
                          {capability.supported ? "Supported" : "Not supported"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Live positions</h3>
                <p>Current exposure and marked value.</p>
              </div>
              <table className="data-table selectable">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Avg</th>
                    <th>Value</th>
                    <th>Unrealized</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.id}>
                      <td>{position.symbol}</td>
                      <td>{position.quantity}</td>
                      <td>{currency(position.average_entry_price)}</td>
                      <td>{currency(position.market_value)}</td>
                      <td>{currency(position.unrealized_pl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Committee feed</h3>
                <p>Latest approved and rejected decisions.</p>
              </div>
              <div className="decision-list">
                {decisions.slice(0, 6).map((decision) => (
                  <article className="decision-item" key={`${decision.symbol}-${decision.entry}-${decision.confidence}`}>
                    <div className="decision-meta">
                      <strong>{decision.symbol}</strong>
                      <span className={decision.status === "approved" ? "tag-positive" : "tag-negative"}>
                        {decision.status}
                      </span>
                    </div>
                    <p>{decision.thesis}</p>
                    <div className="decision-values">
                      <span>Entry {currency(decision.entry)}</span>
                      <span>Conf {percent(decision.confidence)}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Audit log</h3>
                <p>Latest operator and system actions across auth, safety, and execution.</p>
              </div>
              <div className="stack-list">
                {auditLogs.slice(0, 8).map((entry) => (
                  <div className="stack-row" key={entry.id}>
                    <span>{entry.action}</span>
                    <span>{entry.actor}</span>
                    <span>{timestamp(entry.created_at)}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Run history</h3>
                <p>Each scheduled scan and its outcome.</p>
              </div>
              <div className="stack-list">
                {runs.slice(0, 8).map((run) => (
                  <div className="stack-row" key={run.id}>
                    <span>{run.symbol}</span>
                    <span>{run.status}</span>
                    <span>{timestamp(run.finished_at ?? run.started_at)}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : null}

        {!intakeRequired && section === "orders" ? (
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h3>Orders</h3>
                <p>Select an order to inspect full lifecycle transitions and fills.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Type</th>
                    <th>Qty</th>
                    <th>Filled</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((order) => (
                    <tr
                      key={order.id}
                      className={selectedOrderId === order.id ? "table-row-active" : undefined}
                      onClick={() => selectOrder(order.id)}
                    >
                      <td>{order.symbol}</td>
                      <td>{order.order_type}</td>
                      <td>{order.quantity}</td>
                      <td>{order.filled_quantity}</td>
                      <td>{order.status}</td>
                      <td>
                        <button
                          className="secondary-button inline-button"
                          disabled={busy || !canOperate || !canCancel(order.status)}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleCommand(() => cancelOrder(order.id), { success: "Order canceled." });
                          }}
                        >
                          Cancel
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Lifecycle history</h3>
                <p>
                  {selectedOrder
                    ? `Order ${selectedOrder.client_order_id} (${selectedOrder.symbol})`
                    : "Select an order to see transitions."}
                </p>
              </div>
              <div className="stack-list">
                {orderTransitions.map((transition) => (
                  <div className="stack-row" key={transition.id}>
                    <span>
                      {transition.from_status ?? "none"} -&gt; {transition.to_status}
                    </span>
                    <span>{transition.source}</span>
                    <span>{timestamp(transition.transition_at)}</span>
                  </div>
                ))}
                {orderTransitions.length === 0 ? <p className="muted">No lifecycle transitions for this order yet.</p> : null}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Fill history</h3>
                <p>Broker-reported fills mapped to local order state.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Fee</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {orderFills.map((fill) => (
                    <tr key={fill.id}>
                      <td>{fill.quantity}</td>
                      <td>{currency(fill.price)}</td>
                      <td>{currency(fill.fee)}</td>
                      <td>{timestamp(fill.filled_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {orderFills.length === 0 ? <p className="muted">No fills recorded for the selected order.</p> : null}
            </section>
          </div>
        ) : null}

        {!intakeRequired && section === "decisions" ? (
          <section className="panel">
            <div className="panel-heading">
              <h3>Committee decisions</h3>
              <p>Combined market/news conviction after risk review.</p>
            </div>
            <div className="decision-list long">
              {filteredDecisions.map((decision) => (
                <article className="decision-item" key={`${decision.symbol}-${decision.entry}-${decision.confidence}`}>
                  <div className="decision-meta">
                    <strong>{decision.symbol}</strong>
                    <span>{decision.direction}</span>
                    <span className={decision.status === "approved" ? "tag-positive" : "tag-negative"}>
                      {decision.status}
                    </span>
                  </div>
                  <p>{decision.thesis}</p>
                  <div className="decision-values">
                    <span>Entry {currency(decision.entry)}</span>
                    <span>Stop {currency(decision.stop_loss)}</span>
                    <span>Target {currency(decision.take_profit)}</span>
                    <span>Conf {percent(decision.confidence)}</span>
                  </div>
                  {decision.risk_notes.length ? (
                    <div className="note-row">{decision.risk_notes.join(" | ")}</div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {!intakeRequired && section === "risk" ? (
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h3>Performance snapshot</h3>
                <p>Recent operator metrics, rejection pressure, and latency envelopes.</p>
              </div>
              {performanceSummary ? (
                <>
                  <div className="metric-row">
                    <article className="metric-block">
                      <span>Window</span>
                      <strong>{performanceSummary.window_minutes}m</strong>
                    </article>
                    <article className="metric-block">
                      <span>Rejection rate</span>
                      <strong>{percent(performanceSummary.rejection_rate)}</strong>
                    </article>
                    <article className="metric-block">
                      <span>Malformed outputs</span>
                      <strong>{performanceSummary.malformed_events}</strong>
                    </article>
                    <article className="metric-block">
                      <span>Scan failures</span>
                      <strong>{performanceSummary.scan_failures}</strong>
                    </article>
                    <article className="metric-block">
                      <span>Positions</span>
                      <strong>{performanceSummary.portfolio_position_count}</strong>
                    </article>
                    <article className="metric-block">
                      <span>Gross exposure</span>
                      <strong>{currency(performanceSummary.portfolio_gross_exposure)}</strong>
                    </article>
                    <article className="metric-block">
                      <span>Latest equity</span>
                      <strong>{currency(performanceSummary.latest_equity)}</strong>
                    </article>
                  </div>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Counter metric</th>
                        <th>Value</th>
                        <th>Tags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {performanceSummary.counters.slice(0, 8).map((item) => (
                        <tr key={`${item.name}-${JSON.stringify(item.tags)}`}>
                          <td>{item.name}</td>
                          <td>{item.value.toFixed(2)}</td>
                          <td>{Object.entries(item.tags).map(([key, value]) => `${key}:${value}`).join(" | ") || "n/a"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {performanceSummary.counters.length === 0 ? (
                    <p className="muted">No counter samples in the selected window.</p>
                  ) : null}

                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Latency metric</th>
                        <th>P95</th>
                        <th>Avg</th>
                        <th>Samples</th>
                        <th>Tags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {performanceSummary.latencies.slice(0, 8).map((item) => (
                        <tr key={`${item.name}-${JSON.stringify(item.tags)}`}>
                          <td>{item.name}</td>
                          <td>{item.p95_ms.toFixed(2)} ms</td>
                          <td>{item.avg_ms.toFixed(2)} ms</td>
                          <td>{item.samples}</td>
                          <td>{Object.entries(item.tags).map(([key, value]) => `${key}:${value}`).join(" | ") || "n/a"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {performanceSummary.latencies.length === 0 ? (
                    <p className="muted">No latency samples in the selected window.</p>
                  ) : null}
                </>
              ) : (
                <p className="muted">Performance summary is unavailable.</p>
              )}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Operational alerts</h3>
                <p>Auto-alerts for kill switch, worker instability, and reconciliation stress.</p>
              </div>
              <div className="stack-list">
                {alerts.map((event) => (
                  <div className="risk-item" key={event.id}>
                    <div>
                      <strong>{event.code}</strong>
                      <p>{event.message}</p>
                    </div>
                    <div className="risk-meta">
                      <span>{event.severity}</span>
                      <span>{timestamp(event.created_at)}</span>
                    </div>
                  </div>
                ))}
                {alerts.length === 0 ? <p className="muted">No active operational alerts.</p> : null}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Risk events</h3>
                <p>Guardrail trips, scan failures, and rejected trades.</p>
              </div>
              <div className="stack-list">
                {riskEvents.map((event) => (
                  <div className="risk-item" key={event.id}>
                    <div>
                      <strong>{event.code}</strong>
                      <p>{event.message}</p>
                    </div>
                    <div className="risk-meta">
                      <span>{event.symbol ?? "portfolio"}</span>
                      <span>{timestamp(event.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Reconciliation mismatches</h3>
                <p>Unresolved broker/local state drift that can pause live trading.</p>
              </div>
              <div className="stack-list">
                {mismatches.map((mismatch) => (
                  <div className="risk-item" key={mismatch.id}>
                    <div>
                      <strong>{mismatch.mismatch_type}</strong>
                      <p>
                        Local {mismatch.local_reference ?? "n/a"} vs broker {mismatch.broker_reference ?? "n/a"}
                      </p>
                    </div>
                    <div className="risk-meta">
                      <span>{mismatch.symbol ?? "portfolio"}</span>
                      <span>{timestamp(mismatch.created_at)}</span>
                    </div>
                  </div>
                ))}
                {mismatches.length === 0 ? <p className="muted">No unresolved reconciliation mismatches.</p> : null}
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading compact">
                <h3>Execution quality filters</h3>
                <p>Change grouping and sample filters, then apply.</p>
              </div>
              <form id="execution-quality-filter-form" className="settings-grid" onSubmit={applyExecutionQualityFilters}>
                <label>
                  Summary dimension
                  <select
                    value={executionFilterDraft.summaryDimension}
                    onChange={(event) =>
                      setExecutionFilterDraft((current) => ({
                        ...current,
                        summaryDimension: event.target.value as ExecutionSummaryDimension
                      }))
                    }
                  >
                    {executionSummaryDimensionOptions.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Summary rows
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={executionFilterDraft.summaryLimit}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setExecutionFilterDraft((current) => ({
                        ...current,
                        summaryLimit: Number.isFinite(next) ? next : current.summaryLimit
                      }));
                    }}
                  />
                </label>

                <label>
                  Sample symbol
                  <input
                    type="text"
                    placeholder="AAPL (optional)"
                    value={executionFilterDraft.sampleSymbol}
                    onChange={(event) =>
                      setExecutionFilterDraft((current) => ({ ...current, sampleSymbol: event.target.value }))
                    }
                  />
                </label>

                <label>
                  Sample status
                  <select
                    value={executionFilterDraft.sampleStatus}
                    onChange={(event) =>
                      setExecutionFilterDraft((current) => ({
                        ...current,
                        sampleStatus: event.target.value as ExecutionSampleStatusFilter
                      }))
                    }
                  >
                    <option value="all">All</option>
                    {executionSampleStatusOptions.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Sample rows
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={executionFilterDraft.sampleLimit}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setExecutionFilterDraft((current) => ({
                        ...current,
                        sampleLimit: Number.isFinite(next) ? next : current.sampleLimit
                      }));
                    }}
                  />
                </label>
              </form>
              <div className="inline-action-row">
                <button
                  className="secondary-button"
                  type="submit"
                  form="execution-quality-filter-form"
                  disabled={busy || loading}
                >
                  Apply filters
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  onClick={resetExecutionQualityFilters}
                  disabled={busy || loading}
                >
                  Reset
                </button>
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Execution quality summary</h3>
                <p>Grouped TCA by {executionSummaryKeyLabel.toLowerCase()} from recent orders.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{executionSummaryKeyLabel}</th>
                    <th>Samples</th>
                    <th>Reject</th>
                    <th>Avg slippage</th>
                    <th>Avg quality</th>
                  </tr>
                </thead>
                <tbody>
                  {executionQualitySummary.map((item) => (
                    <tr key={`${item.dimension}-${item.key}`}>
                      <td>{item.key}</td>
                      <td>{item.sample_count}</td>
                      <td>{percent(item.reject_rate)}</td>
                      <td>{item.avg_realized_slippage_bps.toFixed(2)} bps</td>
                      <td>{item.avg_quality_score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {executionQualitySummary.length === 0 ? (
                <p className="muted">No execution-quality summary rows yet.</p>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Recent execution samples</h3>
                <p>Intended vs realized execution outcomes and fill diagnostics.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Status</th>
                    <th>Agg</th>
                    <th>Expected</th>
                    <th>Realized</th>
                    <th>Fill ratio</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {executionQualitySamples.map((item) => (
                    <tr key={item.id}>
                      <td>{item.symbol}</td>
                      <td>{item.outcome_status}</td>
                      <td>{item.aggressiveness ?? "n/a"}</td>
                      <td>
                        {item.expected_slippage_bps !== null && item.expected_slippage_bps !== undefined
                          ? `${item.expected_slippage_bps.toFixed(2)} bps`
                          : "n/a"}
                      </td>
                      <td>
                        {item.realized_slippage_bps !== null && item.realized_slippage_bps !== undefined
                          ? `${item.realized_slippage_bps.toFixed(2)} bps`
                          : "n/a"}
                      </td>
                      <td>{percent(item.fill_ratio)}</td>
                      <td>
                        {item.time_to_fill_seconds !== null && item.time_to_fill_seconds !== undefined
                          ? `${item.time_to_fill_seconds.toFixed(1)}s`
                          : "n/a"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {executionQualitySamples.length === 0 ? <p className="muted">No execution samples yet.</p> : null}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Audit trail</h3>
                <p>Recent auth, safety, and execution actions.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Role</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((entry) => (
                    <tr key={entry.id}>
                      <td>{entry.action}</td>
                      <td>{entry.actor}</td>
                      <td>{entry.actor_role}</td>
                      <td>{timestamp(entry.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        ) : null}

        {!intakeRequired && section === "backtests" ? (
          <div className="dashboard-grid">
            <section className="panel settings-panel">
              <div className="panel-heading">
                <h3>Launch research backtest</h3>
                <p>Simulates slippage, commissions, delayed fills, rejects, walk-forward windows, and regime scoring.</p>
              </div>
              <div className="settings-grid">
                <label>
                  Symbols
                  <input
                    type="text"
                    value={backtestDraft.symbols}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, symbols: event.target.value })}
                  />
                </label>
                <label>
                  Interval (minutes)
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={backtestDraft.interval_minutes}
                    onChange={(event) =>
                      setBacktestDraft({ ...backtestDraft, interval_minutes: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Start
                  <input
                    type="datetime-local"
                    value={backtestDraft.start}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, start: event.target.value })}
                  />
                </label>
                <label>
                  End
                  <input
                    type="datetime-local"
                    value={backtestDraft.end}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, end: event.target.value })}
                  />
                </label>
                <label>
                  Initial equity
                  <input
                    type="number"
                    min={1000}
                    value={backtestDraft.initial_equity}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, initial_equity: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Slippage (bps)
                  <input
                    type="number"
                    min={0}
                    step="0.1"
                    value={backtestDraft.slippage_bps}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, slippage_bps: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Commission/share
                  <input
                    type="number"
                    min={0}
                    step="0.0001"
                    value={backtestDraft.commission_per_share}
                    onChange={(event) =>
                      setBacktestDraft({ ...backtestDraft, commission_per_share: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Fill delay (bars)
                  <input
                    type="number"
                    min={0}
                    max={20}
                    value={backtestDraft.fill_delay_bars}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, fill_delay_bars: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Reject probability
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step="0.01"
                    value={backtestDraft.reject_probability}
                    onChange={(event) =>
                      setBacktestDraft({ ...backtestDraft, reject_probability: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Max holding bars
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={backtestDraft.max_holding_bars}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, max_holding_bars: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Random seed
                  <input
                    type="number"
                    min={1}
                    value={backtestDraft.random_seed}
                    onChange={(event) => setBacktestDraft({ ...backtestDraft, random_seed: Number(event.target.value) })}
                  />
                </label>
              </div>
              <button className="primary-button" disabled={busy || !canOperate} onClick={() => void handleLaunchBacktest()}>
                Run backtest
              </button>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Backtest history</h3>
                <p>Persisted reports from the research engine.</p>
              </div>
              <table className="data-table selectable">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Symbols</th>
                    <th>Return</th>
                    <th>Sharpe</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.map((report) => (
                    <tr
                      key={report.id}
                      className={selectedBacktestId === report.id ? "table-row-active" : undefined}
                      onClick={() => selectBacktest(report.id)}
                    >
                      <td>
                        <span className={statusTone(report.status)}>{report.status}</span>
                      </td>
                      <td>{report.symbols.join(", ")}</td>
                      <td>{report.total_return_pct.toFixed(2)}%</td>
                      <td>{report.sharpe_ratio.toFixed(2)}</td>
                      <td>{timestamp(report.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {backtests.length === 0 ? <p className="muted">No backtest reports yet.</p> : null}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Selected report</h3>
                <p>{selectedBacktest ? `Report ${selectedBacktest.id}` : "Select a report to inspect details."}</p>
              </div>
              {selectedBacktest ? (
                <>
                  <div className="profile-summary-grid">
                    <div className="summary-pill">
                      <span>Total trades</span>
                      <strong>{selectedBacktest.total_trades}</strong>
                    </div>
                    <div className="summary-pill">
                      <span>Rejected</span>
                      <strong>{selectedBacktest.rejected_orders}</strong>
                    </div>
                    <div className="summary-pill">
                      <span>Return</span>
                      <strong>{selectedBacktest.total_return_pct.toFixed(2)}%</strong>
                    </div>
                    <div className="summary-pill">
                      <span>Drawdown</span>
                      <strong>{selectedBacktest.max_drawdown_pct.toFixed(2)}%</strong>
                    </div>
                    <div className="summary-pill">
                      <span>Sharpe</span>
                      <strong>{selectedBacktest.sharpe_ratio.toFixed(2)}</strong>
                    </div>
                    <div className="summary-pill">
                      <span>Final equity</span>
                      <strong>{currency(selectedBacktest.final_equity)}</strong>
                    </div>
                  </div>
                  <div className="stack-list" style={{ marginTop: 12 }}>
                    <div className="stack-row">
                      <span>Expectancy</span>
                      <span>{currency(selectedBacktest.expectancy)}</span>
                    </div>
                    <div className="stack-row">
                      <span>Turnover</span>
                      <span>{selectedBacktest.turnover.toFixed(2)}x</span>
                    </div>
                    <div className="stack-row">
                      <span>Exposure (avg/max)</span>
                      <span>
                        {selectedBacktest.avg_exposure_pct.toFixed(2)}% / {selectedBacktest.max_exposure_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="stack-row">
                      <span>Walk-forward windows</span>
                      <span>{selectedBacktest.walk_forward.length}</span>
                    </div>
                    <div className="stack-row">
                      <span>Regimes</span>
                      <span>{selectedBacktest.regime_breakdown.length}</span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="muted">No report selected.</p>
              )}
            </section>

            <section className="panel settings-panel">
              <div className="panel-heading">
                <h3>Walk-forward and regime stats</h3>
                <p>Train/validation/test splits and trend/chop/gap/event behavior.</p>
              </div>
              {selectedBacktest ? (
                <>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Window</th>
                        <th>Trades</th>
                        <th>Return</th>
                        <th>Sharpe</th>
                        <th>Drawdown</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedBacktest.walk_forward.map((window, index) => (
                        <tr key={`${String(window.window)}-${index}`}>
                          <td>{String(window.window ?? index)}</td>
                          <td>{Number(window.trades ?? 0)}</td>
                          <td>{Number(window.total_return_pct ?? 0).toFixed(2)}%</td>
                          <td>{Number(window.sharpe_ratio ?? 0).toFixed(2)}</td>
                          <td>{Number(window.max_drawdown_pct ?? 0).toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <table className="data-table" style={{ marginTop: 14 }}>
                    <thead>
                      <tr>
                        <th>Regime</th>
                        <th>Trades</th>
                        <th>Rejected</th>
                        <th>Win rate</th>
                        <th>Expectancy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedBacktest.regime_breakdown.map((regime, index) => (
                        <tr key={`${String(regime.regime)}-${index}`}>
                          <td>{String(regime.regime ?? index)}</td>
                          <td>{Number(regime.trades ?? 0)}</td>
                          <td>{Number(regime.rejected_orders ?? 0)}</td>
                          <td>{Number(regime.win_rate ?? 0).toFixed(2)}%</td>
                          <td>{currency(Number(regime.expectancy ?? 0))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="muted">No backtest detail loaded.</p>
              )}
            </section>
          </div>
        ) : null}

        {!intakeRequired && section === "settings" && settingsDraft ? (
          <div className="dashboard-grid">
            <section className="panel settings-panel">
              <div className="panel-heading">
                <h3>Live safety controls</h3>
                <p>Environment allowlist, manual live enablement, flatten-all, broker kill, and session review.</p>
              </div>
              <div className="profile-summary-grid">
                <div className="summary-pill">
                  <span>Mode</span>
                  <strong>{settingsData?.mode}</strong>
                </div>
                <div className="summary-pill">
                  <span>Live enabled</span>
                  <strong>{settingsData?.live_enabled ? "yes" : "no"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Environment allowlist</span>
                  <strong>{settingsData?.live_trading_env_allowed ? "allowed" : "blocked"}</strong>
                </div>
                <div className="summary-pill">
                  <span>Order window</span>
                  <strong>{settingsData?.market_session.can_submit_orders ? "open" : "closed"}</strong>
                </div>
              </div>
              <div className="inline-action-row">
                <button
                  className="secondary-button"
                  disabled={busy || !isAdmin || settingsData?.mode !== "live" || !settingsData.live_start_allowed}
                  onClick={() => void handlePrepareLive()}
                >
                  Prepare live enablement
                </button>
                <button
                  className="ghost-button"
                  disabled={busy || !isAdmin || !settingsData?.live_enabled}
                  onClick={() => handleCommand(() => disableLiveExecution(), { success: "Live execution disabled." })}
                >
                  Disable live
                </button>
                <button
                  className="ghost-button"
                  disabled={busy || !canOperate}
                  onClick={() => handleCommand(() => brokerKill(), { success: "Broker kill activated." })}
                >
                  Broker kill
                </button>
              </div>
              <div className="settings-grid">
                <label>
                  Live approval code
                  <input
                    type="text"
                    value={liveApprovalCode}
                    onChange={(event) => setLiveApprovalCode(event.target.value)}
                    placeholder="Enter generated code"
                  />
                </label>
                <label>
                  Code expiry
                  <input type="text" value={timestamp(liveApproval?.expires_at ?? null)} readOnly />
                </label>
              </div>
              <button
                className="primary-button"
                disabled={busy || !isAdmin || !liveApprovalCode.trim()}
                onClick={() => handleEnableLive()}
              >
                Confirm live execution
              </button>
              {liveApproval ? (
                <div className="note-row">
                  Generated code: {liveApproval.approval_code}. It expires at {timestamp(liveApproval.expires_at)}.
                </div>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <h3>Operator sessions</h3>
                <p>Review active sessions and revoke stale ones. Non-admins only see their own sessions.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Last seen</th>
                    <th>Expiry</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((session) => (
                    <tr key={session.session_id}>
                      <td>{session.email}</td>
                      <td>{session.role}</td>
                      <td>{timestamp(session.last_seen_at)}</td>
                      <td>{timestamp(session.expires_at)}</td>
                      <td>
                        {isAdmin && !session.current ? (
                          <button
                            className="secondary-button inline-button"
                            disabled={busy}
                            onClick={() =>
                              handleCommand(() => revokeSession(session.session_id), {
                                success: "Session revoked."
                              })
                            }
                          >
                            Revoke
                          </button>
                        ) : (
                          <span className="muted">{session.current ? "Current" : "View only"}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="panel settings-panel">
              <div className="panel-heading">
                <h3>Bot settings</h3>
                <p>Consensus, risk budgets, cadence, watchlist symbols, and the saved agent intake.</p>
              </div>
              <AgentIntake
                profile={settingsDraft.selected_for_analysis}
                brokerSettings={settingsDraft.broker_settings}
                brokerCapabilityMatrix={settingsDraft.broker_capability_matrix}
                onChange={updateTradingProfile}
                onBrokerChange={updateBrokerSettings}
                title="Trading pattern and strategy intake"
                description="These broker and profile settings define both the research brief and the subset that can be executed."
              />
              <div className="settings-grid">
                <label>
                  Scan interval
                  <input
                    type="number"
                    value={settingsDraft.scan_interval_minutes}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, scan_interval_minutes: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Consensus threshold
                  <input
                    type="number"
                    step="0.01"
                    value={settingsDraft.consensus_threshold}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, consensus_threshold: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Max open positions
                  <input
                    type="number"
                    value={settingsDraft.max_open_positions}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, max_open_positions: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Max daily loss
                  <input
                    type="number"
                    step="0.001"
                    value={settingsDraft.max_daily_loss_pct}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, max_daily_loss_pct: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Position risk
                  <input
                    type="number"
                    step="0.001"
                    value={settingsDraft.max_position_risk_pct}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, max_position_risk_pct: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Symbol cap
                  <input
                    type="number"
                    step="0.01"
                    value={settingsDraft.max_symbol_notional_pct}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, max_symbol_notional_pct: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Cooldown minutes
                  <input
                    type="number"
                    value={settingsDraft.symbol_cooldown_minutes}
                    onChange={(event) =>
                      setSettingsDraft({ ...settingsDraft, symbol_cooldown_minutes: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  Model
                  <input
                    type="text"
                    value={settingsDraft.openai_model}
                    onChange={(event) => setSettingsDraft({ ...settingsDraft, openai_model: event.target.value })}
                  />
                </label>
              </div>
              <label className="watchlist-field">
                Watchlist
                <textarea
                  value={settingsDraft.watchlist.join(", ")}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...settingsDraft,
                      watchlist: event.target.value
                        .split(",")
                        .map((item) => item.trim().toUpperCase())
                        .filter(Boolean)
                    })
                  }
                />
              </label>
              <button
                className="primary-button"
                disabled={busy || !isAdmin}
                onClick={() => handleCommand(() => saveSettingsDraft(), { resetDraft: true, success: "Settings saved." })}
              >
                Save settings
              </button>
            </section>
          </div>
        ) : null}

        {flash ? <p className={flash.tone === "error" ? "error-text" : "info-text"}>{flash.text}</p> : null}
      </main>
    </div>
  );
}
