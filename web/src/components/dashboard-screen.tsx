"use client";

import Link from "next/link";
import { type FormEvent, startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";

import {
  getSettings,
  listDecisions,
  listOrders,
  listPositions,
  listRiskEvents,
  listRuns,
  login,
  startBot,
  stopBot,
  switchMode,
  toggleKillSwitch,
  updateSettings
} from "@/lib/api";
import type {
  BotSettingsResponse,
  BotSettingsUpdatePayload,
  BrokerSettings,
  CommitteeDecision,
  OrderResponse,
  PositionResponse,
  RiskEventResponse,
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
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filterInput, setFilterInput] = useState("");
  const [settingsDraft, setSettingsDraft] = useState<BotSettingsResponse | null>(null);
  const [settingsData, setSettingsData] = useState<BotSettingsResponse | null>(null);
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [decisions, setDecisions] = useState<CommitteeDecision[]>([]);
  const [orders, setOrders] = useState<OrderResponse[]>([]);
  const [positions, setPositions] = useState<PositionResponse[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEventResponse[]>([]);
  const deferredFilter = useDeferredValue(filterInput.trim().toLowerCase());

  useEffect(() => {
    const savedToken = window.localStorage.getItem("tradingbot.token");
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [settingsResponse, runsResponse, decisionsResponse, ordersResponse, positionsResponse, riskResponse] =
          await Promise.all([
            getSettings(token),
            listRuns(token),
            listDecisions(token),
            listOrders(token),
            listPositions(token),
            listRiskEvents(token)
          ]);
        if (cancelled) {
          return;
        }
        setSettingsData(settingsResponse);
        setSettingsDraft((current) => current ?? settingsResponse);
        setRuns(runsResponse);
        setDecisions(decisionsResponse);
        setOrders(ordersResponse);
        setPositions(positionsResponse);
        setRiskEvents(riskResponse);
      } catch (error) {
        if (!cancelled) {
          setLoginError(error instanceof Error ? error.message : "Failed to load dashboard data.");
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
  }, [token]);

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

  async function refreshNow() {
    if (!token) {
      return;
    }
    setLoading(true);
    try {
      const [settingsResponse, runsResponse, decisionsResponse, ordersResponse, positionsResponse, riskResponse] =
        await Promise.all([
          getSettings(token),
          listRuns(token),
          listDecisions(token),
          listOrders(token),
          listPositions(token),
          listRiskEvents(token)
        ]);
      setSettingsData(settingsResponse);
      setSettingsDraft((current) => current ?? settingsResponse);
      setRuns(runsResponse);
      setDecisions(decisionsResponse);
      setOrders(ordersResponse);
      setPositions(positionsResponse);
      setRiskEvents(riskResponse);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setLoginError("");
    try {
      const response = await login(email, password);
      window.localStorage.setItem("tradingbot.token", response.access_token);
      setToken(response.access_token);
      setPassword("");
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  function handleCommand(command: () => Promise<unknown>) {
    setBusy(true);
    startTransition(() => {
      command()
        .then(() => refreshNow())
        .catch((error) => setLoginError(error instanceof Error ? error.message : "Command failed."))
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
    return updateSettings(token, buildSettingsPayload(settingsDraft));
  }

  if (!token) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="eyebrow">AI Trading Bot</p>
          <h1>Operator Console</h1>
          <p className="muted">
            Authenticate with the backend admin account to manage the Alpaca paper/live bot.
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
          {loginError ? <p className="error-text">{loginError}</p> : null}
        </section>
      </main>
    );
  }

  const totalMarketValue = positions.reduce((total, position) => total + position.market_value, 0);
  const totalUnrealized = positions.reduce((total, position) => total + position.unrealized_pl, 0);
  const approvedDecisions = decisions.filter((decision) => decision.status === "approved").length;
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
  const startButtonLabel = intakeRequired
    ? "Complete intake first"
    : liveStartBlocked
      ? "Live start blocked"
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
            <span>Kill switch</span>
            <strong>{settingsData?.kill_switch_enabled ? "armed" : "off"}</strong>
          </div>
        </div>

        <div className="command-stack">
          <button
            className="primary-button"
            disabled={busy || intakeRequired || liveStartBlocked}
            onClick={() => handleCommand(() => startBot(token))}
          >
            {startButtonLabel}
          </button>
          <button className="secondary-button" disabled={busy} onClick={() => handleCommand(() => stopBot(token))}>
            Stop bot
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData || intakeRequired || Boolean(switchingToLive && !settingsData.live_start_allowed)}
            onClick={() =>
              handleCommand(() => switchMode(token, settingsData?.mode === "paper" ? "live" : "paper"))
            }
          >
            {switchingToLive && !settingsData?.live_start_allowed ? "Live mode blocked" : "Flip mode"}
          </button>
          <button
            className="ghost-button"
            disabled={busy || !settingsData}
            onClick={() => handleCommand(() => toggleKillSwitch(token, !settingsData?.kill_switch_enabled))}
          >
            Toggle kill switch
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
            <span>Risk events</span>
            <strong>{riskEvents.length}</strong>
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
          <button className="primary-button" disabled={busy} onClick={() => handleCommand(() => saveSettingsDraft())}>
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
              <table className="data-table">
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
                <h3>Execution log</h3>
                <p>Latest orders routed through Alpaca.</p>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Mode</th>
                    <th>Qty</th>
                    <th>Status</th>
                    <th>Sent</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.slice(0, 6).map((order) => (
                    <tr key={order.id}>
                      <td>{order.symbol}</td>
                      <td>{order.mode}</td>
                      <td>{order.quantity}</td>
                      <td>{order.status}</td>
                      <td>{timestamp(order.submitted_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
          <section className="panel">
            <div className="panel-heading">
              <h3>Orders</h3>
              <p>Filtered client and broker order states.</p>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Stop</th>
                  <th>Target</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredOrders.map((order) => (
                  <tr key={order.id}>
                    <td>{order.symbol}</td>
                    <td>{order.quantity}</td>
                    <td>{currency(order.limit_price)}</td>
                    <td>{currency(order.stop_loss)}</td>
                    <td>{currency(order.take_profit)}</td>
                    <td>{order.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
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
        ) : null}

        {!intakeRequired && section === "settings" && settingsDraft ? (
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
              disabled={busy}
              onClick={() => handleCommand(() => saveSettingsDraft())}
            >
              Save settings
            </button>
          </section>
        ) : null}

        {loginError ? <p className="error-text">{loginError}</p> : null}
      </main>
    </div>
  );
}
