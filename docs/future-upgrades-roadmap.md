# Future Upgrades Roadmap

This document outlines the next wave of improvements after the completion of all Phase 0–9 items in [expert-upgrade-roadmap.md](expert-upgrade-roadmap.md) and the repo-layer items in [production-hardening-plan.md](production-hardening-plan.md).

> [!NOTE]
> Everything described in the original roadmap (Phases 0–9) and the production hardening plan's repo-layer work is **already implemented and verified** in the current codebase. The items below represent the **next frontier** of improvements.

---

## Phase 10: Infrastructure as Code & Hosted Deployment

**Status**: Not started — this is the top remaining gap from the production hardening plan.

### 10.1 Infrastructure as Code (IaC)

- Define Terraform / Pulumi / CDK modules for `api`, `worker`, `web`, managed Postgres, managed Redis, and secrets manager
- Support environment parameterization: `dev`, `staging`, `paper`, `shadow-live`, `guarded-live`, `production`
- Pin infrastructure versions alongside application versions

### 10.2 Managed Secret Rotation

- Move session secrets, broker API keys, and OpenAI credentials into a hosted secrets manager (AWS Secrets Manager, GCP Secret Manager, or Azure Key Vault)
- Implement automatic rotation schedules with zero-downtime credential handoff
- Add audit trail for secret access and rotation events

### 10.3 Hosted Deployment Pipeline

- Build a versioned deploy, migration-review, and rollback workflow across staging and production
- Add canary/blue-green deployment support for the API and worker services
- Integrate database migration review as a deploy gate (not just CI)

### 10.4 Environment Isolation

- Fully separate staging, paper, shadow-live, and guarded-live environments with distinct secrets, broker accounts, and database instances
- Add environment promotion gates (paper metrics → shadow-live → guarded-live → production)

---

## Phase 11: External Observability Pipeline

**Status**: Not started — current observability is repo-local; needs external sinks for production.

### 11.1 Centralized Log, Metric & Trace Export

- Export structured JSON logs to a managed log backend (Datadog, Grafana Cloud, CloudWatch, etc.)
- Export metrics to a time-series backend (Prometheus, Datadog, CloudWatch Metrics)
- Add distributed tracing (OpenTelemetry) across API → worker → broker calls
- Correlate request IDs / run IDs across all services in the external backend

### 11.2 External Alerting & On-Call Integration

- Route `alert_*` events to PagerDuty, Opsgenie, or equivalent on-call tooling
- Add escalation policies: info → warning → page → auto-halt
- Add alert suppression / deduplication rules to avoid alert fatigue

### 11.3 SLA Dashboards

- Build hosted operator dashboards for broker health, worker health, live trade health
- Add SLA tracking: scan latency p50/p95/p99, reconciliation drift duration, time-to-fill distributions
- Add anomaly detection alerts on metric trends (not just thresholds)

---

## Phase 12: Broker Stream Supervision & Real-Time State Convergence

**Status**: Not started — current state sync is poll-based; needs real-time convergence.

### 12.1 Long-Running Broker WebSocket Supervisor

- Build a dedicated supervisor service for broker websocket connections (order updates, trade events, account events)
- Handle reconnection, backfill on reconnect, and heartbeat monitoring
- Integrate websocket events with the existing order state machine for sub-second state convergence

### 12.2 Real-Time Position & Exposure Tracking

- Update position and exposure state in real time from broker stream events
- Feed real-time P&L into circuit-breaker and drawdown logic (currently batch-evaluated)
- Add real-time portfolio exposure visualization in the dashboard

### 12.3 Market Data Streaming

- Add real-time bar / quote / trade streaming for monitored symbols
- Enable real-time signal evaluation (vs. current scan-interval approach)
- Support configurable latency modes: real-time, near-real-time, and batch

---

## Phase 13: Multi-Market & Multi-Broker Expansion

**Status**: Not started — the routing layer exists but only US cash equities are executable.

### 13.1 Add Broker Adapters for New Markets

- Add adapter(s) for Indian equities (Zerodha/Upstox/Angel One) or European equities (Interactive Brokers)
- Add adapter(s) for crypto (Binance, Coinbase)
- Each adapter must implement the full `BrokerAdapter` interface including reconciliation

### 13.2 Derivatives Execution

- Enable futures execution with rollover management against a real derivatives-capable broker
- Enable single-leg options execution with Greeks-aware risk checks
- Add spread/multi-leg support only after single-leg risk and reconciliation are stable

### 13.3 Cross-Market Portfolio Risk

- Extend portfolio risk engine to handle multiple currencies with FX conversion
- Add cross-market correlation exposure tracking
- Add venue-specific margin model awareness

---

## Phase 14: Advanced AI & Strategy Intelligence

**Status**: Not started — current committee is LLM-based; needs hybrid intelligence.

### 14.1 ML Signal Models

- Add a classical ML signal pipeline (gradient-boosted models on engineered features)
- Train on the feature set already computed in `features.py` and `indicators.py`
- Score ML signals alongside LLM committee signals for comparison and blending

### 14.2 Reinforcement Learning for Execution

- Train an RL agent for optimal order execution (timing, sizing, aggressiveness)
- Use the execution-quality TCA data already collected as training signal
- Start with simulation, then shadow-live before any live execution

### 14.3 Dynamic Strategy Selection

- Build a meta-agent that selects strategy parameters based on detected market regime
- Use regime classification already computed in backtests for regime-aware parameter switching
- Support A/B testing of strategy variants with controlled traffic splitting

### 14.4 LLM Fine-Tuning & Self-Improvement

- Fine-tune specialist models on the post-trade review and committee decision history
- Build a feedback loop: poor review scores → prompt registry update → A/B evaluation
- Track model version performance over time with statistical significance testing

---

## Phase 15: Advanced Backtesting & Research

**Status**: Not started — current backtest engine is solid but can go deeper.

### 15.1 Monte Carlo & Stress Testing

- Add Monte Carlo simulation on backtest equity curves to estimate tail risk
- Add historical stress scenario replay (flash crashes, halt events, gap opens)
- Add configurable adverse fill models (worst-case slippage scenarios)

### 15.2 Portfolio-Level Backtesting

- Upgrade from single-symbol to portfolio-level backtesting with capital allocation
- Model inter-symbol correlation effects during drawdowns
- Simulate portfolio rebalancing and position-sizing constraints

### 15.3 Strategy Evolution Lab

- Add hyperparameter optimization for risk thresholds and sizing parameters
- Add automated walk-forward parameter selection
- Build a strategy comparison dashboard with statistical hypothesis testing

---

## Phase 16: Operational Maturity

**Status**: Not started — rehearsals and drills for production incidents.

### 16.1 Incident Drills & Gamedays

- Schedule quarterly chaos engineering exercises (broker disconnect, data feed failure, database failover)
- Automate failure injection in staging environments
- Track drill outcomes and playbook improvements

### 16.2 Compliance & Audit Readiness

- Add automated daily trade report generation (P&L, fills, rejections, risk events)
- Add exportable audit trails in regulatory-friendly formats
- Add automated compliance checks (position limits, wash-sale detection, pattern day-trader rules)

### 16.3 Multi-Operator Support

- Add team-based access control with operator, reviewer, and admin roles per strategy
- Add operator activity audit logs with session attribution
- Add approval workflows for strategy parameter changes and risk limit modifications

### 16.4 Cost Optimization

- Track and report LLM token usage and cost per scan/decision
- Add intelligent scan scheduling (skip low-opportunity periods)
- Cache and reuse stable data (sector context, calendar data) to reduce API calls

---

## Phase 17: User Experience & Mobile

**Status**: Not started — dashboard exists but operator experience can be elevated.

### 17.1 Mobile Operator App

- Build a mobile-friendly dashboard (or native app) for on-the-go monitoring
- Include push notifications for critical alerts (kill-switch activation, large fills, reconciliation drift)
- Include one-tap flatten-all and kill-switch controls

### 17.2 Natural Language Bot Interface

- Add a Telegram/Discord/Slack bot for operator commands and status queries
- Support commands: status, flatten, kill, approve, reject, backtest summary
- Add conversational trade review ("why did you buy AAPL yesterday?")

### 17.3 Advanced Dashboard Visualizations

- Add real-time equity curve streaming in the dashboard
- Add interactive trade map (entry/exit points overlaid on candlestick charts)
- Add heatmaps for portfolio correlation, sector exposure, and P&L attribution
- Add strategy comparison views with side-by-side metric tables

---

## Priority Recommendation

If the goal is maximum value for the next development cycle:

| Priority | Phase | Rationale |
|----------|-------|-----------|
| 🔴 P0 | Phase 10 (IaC & Deployment) | Cannot go to production without this |
| 🔴 P0 | Phase 11 (External Observability) | Cannot operate production without external visibility |
| 🟡 P1 | Phase 12 (Broker Streaming) | Significantly improves execution latency and state accuracy |
| 🟡 P1 | Phase 16.1-16.2 (Drills & Compliance) | Required for any real-money operation |
| 🟢 P2 | Phase 13 (Multi-Market) | Expands addressable market but not required for US equities |
| 🟢 P2 | Phase 14 (Advanced AI) | Improves signal quality but current committee is functional |
| 🔵 P3 | Phase 15 (Advanced Backtesting) | Nice-to-have research depth |
| 🔵 P3 | Phase 17 (UX & Mobile) | Nice-to-have operator convenience |
