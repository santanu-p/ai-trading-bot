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
  getCurrentSession,
  getSettings,
  listAuditLogs,
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
  BotSettingsResponse,
  BotSettingsUpdatePayload,
  BrokerSettings,
  CommitteeDecision,
  ExecutionIntentResponse,
  LiveEnablePrepareResponse,
  LoginResponse,
  OrderFillResponse,
  OrderResponse,
  OrderTransitionResponse,
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

type SectionName = "overview" | "orders" | "decisions" | "risk" | "settings";

const sections: Array<{ href: string; label: string; key: SectionName }> = [
  { href: "/", label: "Overview", key: "overview" },
  { href: "/orders", label: "Orders", key: "orders" },
  { href: "/decisions", label: "Decisions", key: "decisions" },
  { href: "/risk", label: "Risk", key: "risk" },
  { href: "/settings", label: "Settings", key: "settings" }
];

interface Props {
  section: SectionName;
}

function buildSettingsPayload(draft: BotSettingsResponse): BotSettingsUpdatePayload {
  return {
    scan_interval_minutes: draft.scan_interval_minutes,
    consensus_threshold: draft.consensus_threshold,
    max_open_positions: draft.max_open_positions,
    max_daily_loss_pct: draft.max_daily_loss_pct,
    max_position_risk_pct: draft.max_position_risk_pct,
    max_symbol_notional_pct: draft.max_symbol_notional_pct,
    symbol_cooldown_minutes: draft.symbol_cooldown_minutes,
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
  const [mismatches, setMismatches] = useState<ReconciliationMismatchResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
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
    setMismatches([]);
    setAuditLogs([]);
    setSessions([]);
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

  async function loadDashboardData(resetDraft = false) {
    const [
      settingsResponse,
      runsResponse,
      decisionsResponse,
      executionIntentResponse,
      ordersResponse,
      positionsResponse,
      riskResponse,
      mismatchesResponse,
      auditResponse,
      sessionResponse
    ] = await Promise.all([
      getSettings(),
      listRuns(),
      listDecisions(),
      listExecutionIntents(undefined, 24),
      listOrders(),
      listPositions(),
      listRiskEvents(),
      listReconciliationMismatches(),
      listAuditLogs(24),
      listSessions()
    ]);

    setSettingsData(settingsResponse);
    setSettingsDraft((current) => (resetDraft || current === null ? settingsResponse : current));
    setRuns(runsResponse);
    setDecisions(decisionsResponse);
    setExecutionIntents(executionIntentResponse);
    setOrders(ordersResponse);
    setPositions(positionsResponse);
    setRiskEvents(riskResponse);
    setMismatches(mismatchesResponse);
    setAuditLogs(auditResponse);
    setSessions(sessionResponse);

    const nextSelectedOrderId = ordersResponse.some((order) => order.id === selectedOrderId)
      ? selectedOrderId
      : ordersResponse[0]?.id ?? null;
    setSelectedOrderId(nextSelectedOrderId);
    await loadOrderLifecycle(nextSelectedOrderId);
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
  }, [operator, selectedOrderId]);

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

  function canCancel(status: string) {
    return ["new", "accepted", "pending_trigger", "partially_filled", "suspended"].includes(status);
  }

  function selectOrder(orderId: number) {
    setSelectedOrderId(orderId);
    void loadOrderLifecycle(orderId);
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
