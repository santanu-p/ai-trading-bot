# Expert Upgrade Roadmap

This file describes what to add or modify in the future to move this repository from a useful scaffold to an expert-grade trading system.

Important: "expert-grade" here means stronger research quality, execution quality, risk discipline, observability, and operational safety. It does not mean guaranteed profits.

For the production deployment, safety, and recovery path, see [production-hardening-plan.md](production-hardening-plan.md).

Status note as of 2026-04-08:

- Phase 0 broker-scope alignment and capability-gating items are implemented in the current repo.
- Phase 1 foundation items are also implemented in the current repo.
- Phase 2 broker-execution items are now implemented in the current repo.
- Phase 3 research-quality items are now implemented in the current repo.
- Phase 4 data-depth items are now implemented in the current repo.
- Phase 5 agent-intelligence items are now implemented in the current repo.
- Phase 6 portfolio-risk engine items are now implemented in the current repo.
- Phase 7 execution-quality items are now implemented in the current repo.
- Phase 8 observability and operations baseline items are now implemented in the current repo.
- Phase 9 testing and release-discipline items are now implemented in the current repo.
- The remaining sections below describe the next upgrade path after Phase 9.

Additional repo-local status note as of 2026-04-09:

- control-plane CSRF protection, request-size limits, and sliding-window rate limiting are now in the repo
- alert webhook dispatch and dashboard-facing SSE operations streaming are now in the repo
- the dashboard now renders open risk budget, trade-review queues, prompt attribution, and committee disagreement summaries
- release-governance docs, a PR evidence template, and a release-guard workflow are now in the repo
- the main remaining gaps after these additions are hosted branch-protection enforcement, broader replay failure injection, release rollout controls across environments, multi-market broker expansion, and direct broker-native streaming

## Critical Scope Decision

The repo now asks the operator to choose patterns such as intraday, delivery, futures, and options, but the current execution layer is still Alpaca-oriented and cash-equity only.

Before treating this as a real auto-trading system, make this decision explicit:

1. `US equities expert bot`
   Keep Alpaca and narrow real execution to supported US cash-equity workflows.
2. `Multi-market / F&O expert bot`
   Keep Alpaca for US equities, but add one or more broker adapters that actually support delivery, futures, and options for the target market.

Until that scope decision is implemented in code, non-cash-equity patterns should stay analysis-only by design.

## Current Baseline

The current repo already has:

- a FastAPI control plane
- a Celery worker for scheduled scans
- Alpaca broker/data/news adapters
- OpenAI-based market/news agent hooks
- deterministic risk validation
- a Next.js operator dashboard
- a first-step intake for trading pattern, instrument class, strategy family, risk profile, and market universe

The biggest gaps are not UI polish. They are broker coverage, order lifecycle realism, research depth, risk sophistication, evaluation discipline, and production hardening.

## Current Execution Reality

Current repo reality after Phases 0-9:

- The core order lifecycle, reconciliation, execution-quality/TCA, observability, and release-discipline baselines are implemented.
- Broker/profile capability gating is explicit, and unsupported selections are analysis-only by design.
- Execution remains intentionally focused on the currently supported US cash-equity workflow; futures/options are not yet executable in this repo.
- The largest remaining gaps are multi-market broker expansion, advanced operator analytics depth, realtime event streaming, and production hardening controls.
- Repo-local operator analytics depth and backend event-stream transport have improved, but direct broker-native streaming and hosted production controls still remain.

## Priority Order

Recommended order:

1. Market scope and broker alignment
2. Safety and correctness
3. Broker execution completeness
4. Research and backtesting quality
5. Data quality and feature depth
6. Portfolio construction
7. Model and agent sophistication
8. Production operations and scaling

## Phase 0: Align Market Scope And Broker Coverage

### Make product support explicit in the UX and API

Original issue:

- the intake can capture delivery, futures, and options intent, but execution support is still limited

What to add or modify:

- split `selected_for_analysis` from `supported_for_execution`
- show a capability matrix in the dashboard
- block live start when the chosen profile is not executable with the selected broker
- persist the reason for any analysis-only downgrade

Suggested files:

- [store.py](../backend/src/tradingbot/services/store.py)
- [settings.py](../backend/src/tradingbot/schemas/settings.py)
- [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx)
- [agent-intake.tsx](../web/src/components/agent-intake.tsx)

### Decide the real broker families this repo will support

Current issue:

- Alpaca is a good fit for the current scaffold, but it is not a generic answer for delivery plus futures plus options across markets

What to add or modify:

- decide whether v2 is Alpaca-only US equities, Alpaca plus a derivatives-capable broker family, or true multi-broker routing by asset class and venue
- persist broker account metadata such as venue, timezone, base currency, permissions, and account type
- move broker selection into bot settings instead of assuming one broker path

### Add a broker capability registry

What to add or modify:

- define capabilities such as cash equities, shorting, futures, options, bracket or OCO orders, stop-market and stop-limit, replace and cancel, websocket order streams, and paper and live modes
- require capability checks before agent prompting, risk approval, and broker execution

Suggested files:

- new `backend/src/tradingbot/services/broker_capabilities.py`
- expand [adapters.py](../backend/src/tradingbot/services/adapters.py)
- expand [store.py](../backend/src/tradingbot/services/store.py)

## Phase 1: Fix The Foundations

Current repo status: completed.

### Replace startup table creation with real migrations

Current issue:

- [main.py](../backend/src/tradingbot/api/main.py) uses `Base.metadata.create_all(...)`

What to add or modify:

- add Alembic configuration and migration scripts
- remove implicit table creation from app startup
- version all schema changes

Why:

- expert systems need reproducible schema evolution and safe deploys

Implemented:

- Alembic config and initial migration now live under `backend/alembic/`
- startup `create_all(...)` has been removed from the API boot path

### Add explicit market-hours and trading-calendar gating

Original issue:

- the worker runs on a fixed interval but does not yet enforce exchange calendars, holiday handling, or product-session rules

What to add or modify:

- add a market calendar service in `backend/src/tradingbot/services/`
- block scans and order submission outside market hours
- support half-days, venue-specific timezones, and product sessions
- add session-aware rules such as end-of-day flattening when required by the strategy or product type

Suggested files:

- new `backend/src/tradingbot/services/calendar.py`
- update [tasks.py](../backend/src/tradingbot/worker/tasks.py)
- update [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- scans and submissions now use a market calendar service
- half-days, venue timezone handling, and session-close flatten rules are enforced

### Separate paper and live safety modes more aggressively

Original issue:

- the code supports paper/live mode switching, but expert-grade systems need stronger live-mode friction

What to add or modify:

- add a `live_enabled` gate separate from mode
- add environment-level live trading allowlist
- require human approval or multi-step confirmation for live orders
- log every live order decision path
- add manual flatten-all and broker kill actions

Suggested files:

- [settings.py](../backend/src/tradingbot/schemas/settings.py)
- [models.py](../backend/src/tradingbot/models.py)
- [trading.py](../backend/src/tradingbot/api/routers/trading.py)
- dashboard settings UI in [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx)

Implemented:

- `live_enabled` is now separate from mode
- live trading is gated by environment allowlists and short-lived admin approval codes
- flatten-all and broker-kill controls are exposed in the API and dashboard

### Split decisioning from execution

Original issue:

- [tasks.py](../backend/src/tradingbot/worker/tasks.py) both decides and submits orders in one path

What to add or modify:

- queue approved order intents to a dedicated execution worker
- make the handoff idempotent
- re-check kill switch, market hours, and broker connectivity at the execution boundary
- isolate model failures from broker failures

Suggested files:

- [tasks.py](../backend/src/tradingbot/worker/tasks.py)
- new `backend/src/tradingbot/worker/execution_tasks.py`
- expand [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- approved decisions are persisted as execution intents
- a dedicated execution worker performs the final submission boundary checks
- execution remains idempotent through stored intent metadata

### Harden auth and operator controls

Original issue:

- dashboard token is stored in `localStorage`
- current auth model is single-admin and minimal

What to add or modify:

- move to secure cookies or short-lived access + refresh flow
- add role-based access for operator, reviewer, admin
- add session expiry, audit trail filtering, and forced logout support

Implemented:

- the dashboard now uses secure cookies instead of `localStorage`
- operator roles, session expiry, audit trails, and forced logout support are live

## Phase 2: Build Real Broker Execution

Current repo status: completed.

### Expand `BrokerAdapter` into a full execution interface

Current issue:

- the current adapter shape is enough for a scaffold but not for a production trading engine

What to add or modify:

- add methods for account snapshots, open orders, positions, place order, replace order, cancel order, cancel all orders, get order by broker ID, and fetch fills
- separate market-data adapters cleanly from execution adapters
- add broker-specific error normalization

Suggested files:

- expand [adapters.py](../backend/src/tradingbot/services/adapters.py)
- expand [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- execution adapters now expose account snapshots, open orders, positions, place/replace/cancel/cancel-all, get-order, fetch-fills, and close-all-positions
- market-data/news adapters are separated from execution adapters
- broker errors are normalized into category-aware `BrokerAPIError` responses

### Add a real order state machine

Current issue:

- local orders are persisted with a simplified status model

What to add or modify:

- represent new, accepted, pending-trigger, partially-filled, filled, canceled, expired, replaced, rejected, and suspended states
- persist every transition with timestamps
- show lifecycle history in the dashboard

Suggested files:

- [models.py](../backend/src/tradingbot/models.py)
- [execution.py](../backend/src/tradingbot/services/execution.py)
- dashboard routes under `web/app/`

Implemented:

- order states now include new, accepted, pending-trigger, partially-filled, filled, canceled, expired, replaced, rejected, and suspended
- every order transition is persisted in `order_state_transitions`
- the API and dashboard expose transition/fill lifecycle views per order

### Add broker reconciliation and event ingestion

Current issue:

- broker truth and local database truth can drift with no recovery path

What to add or modify:

- poll or stream orders and positions from the broker
- reconcile local state with broker state on a schedule
- flag mismatches as high-priority events
- pause live trading on unresolved mismatches
- persist every state transition, fill, reject, and cancel event

Suggested files:

- new `backend/src/tradingbot/services/reconciliation.py`
- expand [adapters.py](../backend/src/tradingbot/services/adapters.py)
- expand [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- reconciliation now compares broker open orders with local orders, applies broker snapshots, and records mismatches
- fill ingestion and position sync run as part of reconciliation passes
- unresolved mismatches in live mode automatically pause execution by arming the kill switch
- reconciliation is available both from worker scheduling and an operator API endpoint

### Add pre-trade broker and exchange validation

What to add or modify:

- validate tick size, lot size, contract multiplier, expiry state, option chain availability, shortability, buying power, margin usage, exchange order caps, and price bands
- reject structurally invalid orders before broker submission

Suggested files:

- new `backend/src/tradingbot/services/pretrade.py`
- expand [risk.py](../backend/src/tradingbot/services/risk.py)
- expand [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- pre-trade validation now checks tick size, lot size, contract multiplier, expiry, option-chain availability, shortability, buying power, margin usage, open-order caps, and price bands
- structurally invalid orders are blocked before broker submission and persisted as risk events

### Add support for real order types and exit handling

What to add or modify:

- support the broker-capable subset of market, limit, stop-market, stop-limit, bracket, OCO, trailing stop, and IOC/FOK/GTC where supported
- add replace and amend flows
- repair broken child orders
- flatten positions when kill switch or end-of-session rules require it

Implemented:

- the broker adapter now maps market/limit/stop/stop-limit/bracket/OCO/trailing-stop and day/gtc/ioc/fok where supported by the broker
- order replace and cancel-all flows are implemented in the service layer and exposed via operator endpoints
- bracket child-order repair is executed after scans
- flatten-all is available for manual actions and session-close enforcement

### Add derivatives and contract-master support

Current issue:

- futures and options can be selected in the intake, but there is no executable contract model behind them

What to add or modify:

- add an instrument master for equities, futures, and options
- store contract metadata such as expiry, strike, right, multiplier, lot size, exchange, and symbol mapping
- add option-chain selection logic and futures rollover rules
- support single-leg options first, then spreads only after risk and reconciliation are solid

Suggested files:

- new `backend/src/tradingbot/services/contracts.py`
- expand [models.py](../backend/src/tradingbot/models.py)

Implemented:

- instrument contracts are persisted in `instrument_contracts` with expiry/strike/right/multiplier/lot/tick/exchange metadata
- option-chain contract selection and futures rollover helpers are implemented in the contract-master service
- pre-trade checks are now contract-aware, with cash-equity auto-registration for symbols without explicit entries

### Add multi-broker routing when needed

What to add or modify:

- route by market, instrument class, and account permissions
- isolate one broker outage from the rest of the system
- keep broker-specific translations out of agent prompts and core risk logic

Implemented:

- execution now routes through `ExecutionBrokerRouter` using instrument-class and permission requirements
- broker routing and broker-specific payload mapping are isolated in adapter code, not agent prompts or core risk logic
- routing failures are surfaced as normalized broker errors so one broker path can fail without corrupting core execution state

## Phase 3: Build Real Research Quality

Current repo status: completed.

### Upgrade backtesting from placeholder to research engine

Current issue:

- current backtest task is a structural stub

What to add or modify:

- use historical bars and historical news across a defined period
- simulate fills with slippage and commissions
- simulate delayed fills and rejected orders
- compute equity curve, drawdown, Sharpe, win rate, expectancy, turnover, and exposure
- persist backtest reports

Suggested files:

- expand [backtest.py](../backend/src/tradingbot/services/backtest.py)
- expand [tasks.py](../backend/src/tradingbot/worker/tasks.py)
- add backtest result models to [models.py](../backend/src/tradingbot/models.py)
- add backtest API endpoints and dashboard views

Implemented:

- backtests now run as a deterministic research engine using historical bars and historical news over the requested period
- fill simulation now includes slippage, commissions, delayed fills, and probabilistic broker-side rejections
- reports now compute and persist equity curve, drawdown, Sharpe, win rate, expectancy, turnover, and exposure metrics
- reports, walk-forward windows, regime breakdowns, equity-curve payloads, and per-trade simulation rows are persisted in dedicated backtest tables
- operator APIs now expose queued/succeeded/failed backtest reports plus full report detail views
- dashboard now includes a dedicated Backtests route for launching runs and reviewing saved report metrics

### Add walk-forward testing and regime evaluation

What to add or modify:

- split backtests into train/validation/test windows
- score performance by market regime
- compare behavior during trend, chop, gap-driven, and event-heavy sessions

Why:

- expert systems must survive outside one lucky sample

Implemented:

- each run now includes train/validation/test walk-forward windows with per-window metric summaries
- each run now scores regime behavior across trend/chop/gap-driven/event-heavy classifications

### Add replay datasets and deterministic fixtures

What to add or modify:

- build fixed replay fixtures for bars, news, and broker responses
- run the same decision path deterministically in tests
- lock down expected outputs for risk and execution rules

Suggested files:

- `backend/tests/fixtures/`
- more test coverage under `backend/tests/`

Implemented:

- deterministic replay fixtures were added under `backend/tests/fixtures/` for bars, news, expected backtest snapshots, and broker fill events
- fixture-backed tests now assert deterministic backtest outputs and stable fill-ingestion behavior from replayed broker data

## Phase 4: Expand Data Depth

Current repo status: completed.

### Add richer market features

Current issue:

- current features are intentionally simple

What to add or modify:

- intraday volatility features
- gap statistics
- relative volume
- ATR and stop-distance features
- opening range structure
- trend alignment across multiple timeframes
- market index context such as SPY/QQQ breadth or trend state

Suggested files:

- expand [indicators.py](../backend/src/tradingbot/services/indicators.py)
- add feature engineering service modules

Implemented:

- indicator computation now includes intraday volatility, gap statistics, relative volume, ATR/stop-distance context, opening-range structure, and multi-timeframe trend alignment
- a dedicated feature service now merges per-symbol features with SPY/QQQ market-index context and a regime score

### Add structured event data

What to add or modify:

- earnings dates
- analyst actions
- macro releases
- sector ETF context
- economic calendar and market-moving scheduled events

Why:

- many bad trades are bad because the context is incomplete

Implemented:

- structured event extraction now tags earnings-date headlines, analyst actions, and macro-release mentions from symbol news
- symbol-level sector ETF context is now appended as structured event data
- recurring scheduled macro templates are now included as economic-calendar events in the decision context payload

### Add data validation and freshness checks

What to add or modify:

- reject stale bars
- reject delayed news snapshots when timeliness matters
- detect missing candles or abnormal feed gaps
- tag every decision with data timestamps

Suggested files:

- [adapters.py](../backend/src/tradingbot/services/adapters.py)
- new validation module in `backend/src/tradingbot/services/`

Implemented:

- scan-time data-quality validation now rejects stale bars, delayed news snapshots, missing-candle windows, and abnormal feed gaps before agent inference
- rejected symbols are persisted as explicit data-quality trade rejections and risk events
- every decision payload now includes data timestamps, quality diagnostics, structured events, and engineered feature snapshots

## Phase 5: Improve Agent Intelligence

Current repo status: completed.

### Move from two-agent prompts to a structured committee

Current issue:

- current setup is market agent + news agent + deterministic risk

What to add or modify:

- add specialized agents:
  - technical structure agent
  - catalyst agent
  - market regime agent
  - portfolio exposure agent
  - execution quality agent
- add a final chair/aggregator agent that only summarizes, not overrides hard risk rules

Suggested files:

- expand [agents.py](../backend/src/tradingbot/services/agents.py)
- expand [committee.py](../backend/src/tradingbot/services/committee.py)
- add agent prompt/version registry

Implemented:

- the worker now runs a structured specialist committee with technical-structure, catalyst, market-regime, portfolio-exposure, and execution-quality roles
- a chair summary now synthesizes specialist views into the final pre-risk thesis without bypassing deterministic risk rules
- committee payloads now persist specialist signals, chair vote, committee notes, model name, and prompt-version lineage

### Add prompt and model versioning

What to add or modify:

- store prompt templates by version
- store model name, prompt version, and input snapshot per run
- compare performance by model and prompt version

Why:

- expert systems need explainable changes and measurable iteration

Implemented:

- prompt templates now live in a dedicated prompt registry with explicit per-role versions
- each agent run now stores the model name, prompt-version map, and shared input snapshot used for the committee
- post-trade reviews can now be grouped by model/prompt signature for performance comparison

### Add strict output validation and repair flow

What to add or modify:

- validate every agent payload against schema
- auto-retry malformed outputs with a repair prompt
- reject the trade if the payload stays malformed

Suggested files:

- [committee-decision.schema.json](../contracts/committee-decision.schema.json)
- [schemas/trading.py](../backend/src/tradingbot/schemas/trading.py)
- [agents.py](../backend/src/tradingbot/services/agents.py)

Implemented:

- specialist and chair payloads are now schema-validated before use
- malformed agent outputs trigger an automatic repair call with the target schema embedded in the repair payload
- if a role still returns malformed output after repair, the trade is rejected and persisted as an explicit `agent_output_malformed` event rather than crashing the scan

### Add post-trade review and feedback loops

What to add or modify:

- score each closed trade versus its original thesis
- classify losses by cause:
  - bad signal
  - bad context
  - bad execution
  - avoidable risk
- build a review queue for recurring failure patterns

Implemented:

- filled exit orders now generate persisted post-trade reviews tied back to the originating run when lineage is available
- losing trades are classified into `bad_signal`, `bad_context`, `bad_execution`, or `avoidable_risk` buckets
- queued review rows and recurring-pattern warnings now provide a lightweight feedback loop for repeated failure modes

## Phase 6: Upgrade Risk Into A Real Portfolio Engine

Current repo status: completed.

### Replace symbol-level checks with portfolio-aware risk

Current issue:

- current risk is mostly single-trade and single-symbol based

What to add or modify:

- cap total gross exposure
- cap correlation exposure
- cap sector exposure
- cap event clustering
- scale position size by volatility and conviction

Suggested files:

- [risk.py](../backend/src/tradingbot/services/risk.py)
- [execution.py](../backend/src/tradingbot/services/execution.py)

Implemented:

- deterministic risk now enforces gross exposure caps, sector concentration caps, correlation concentration caps, and event-cluster gating
- risk validation now uses runtime portfolio metrics and active cooldown state, not only single-symbol checks

### Add dynamic position sizing

What to add or modify:

- ATR-based sizing
- volatility-targeted sizing
- equity-curve based throttling
- strategy confidence scaling

Implemented:

- position size now combines stop-distance risk budget with ATR-aware stop normalization
- volatility target scaling, confidence scaling, equity-curve throttling, and loss-streak throttling are applied before final approved quantity is persisted

### Add drawdown and circuit-breaker logic

What to add or modify:

- stop new entries after intraday drawdown thresholds
- reduce size after loss streaks
- require manual review after repeated execution failures
- auto-enable kill switch after severe anomalies

Implemented:

- new entry approvals are blocked when drawdown circuit thresholds are breached
- repeated execution-failure clusters now force manual-review style rejection notes at the risk boundary
- severe anomaly clusters now auto-enable the kill switch and emit explicit `auto_kill_switch` risk events

### Add symbol cooldowns that reflect outcome and context

What to add or modify:

- separate cooldowns for stop-outs vs profit exits
- longer cooldown after high-volatility event failures
- avoid immediate re-entry after news whipsaws

Implemented:

- symbol cooldowns are now persisted in `symbol_cooldowns` and checked before new entries
- exit-driven cooldown typing now differentiates `profit_exit`, `stop_out`, `news_whipsaw`, and `event_failure`
- high-volatility event losses now apply extended cooldown windows before re-entry

## Phase 7: Optimize Execution Quality

Current repo status: completed.

### Model real execution, not just decision quality

Current issue:

- current execution path is structurally correct but simplified

What to add or modify:

- estimate slippage before order submission
- avoid thin names or unstable spreads
- reject trades with poor fill quality expectations
- adapt order type and aggressiveness to liquidity

Implemented:

- execution now computes a pre-submit execution-quality preview using quote spread, depth, and symbol features
- expected spread/slippage and liquidity score are evaluated before broker submission, with hard reject on poor expected fill quality
- order aggressiveness now adapts between aggressive, balanced, and passive plans, including time-in-force and entry style tuning

### Add venue, liquidity, and routing logic

What to add or modify:

- avoid thin names or unstable spreads
- pick order aggressiveness from liquidity and spread conditions
- route by venue or broker when more than one execution path exists
- reject trades with poor expected fill quality

Implemented:

- execution adapters now expose liquidity snapshots and quote-derived venue context where available
- submission routing now records venue and broker context in execution-quality metadata for downstream analytics
- thin/unstable spread conditions are rejected before order placement rather than after failed fills

Suggested files:

- [adapters.py](../backend/src/tradingbot/services/adapters.py)
- [execution.py](../backend/src/tradingbot/services/execution.py)
- new routing logic in `backend/src/tradingbot/services/`

### Add execution analytics and post-trade TCA

What to add or modify:

- measure intended entry versus actual fill
- measure slippage, spread cost, cancel rate, reject rate, and time-to-fill
- compare execution quality by symbol, venue, broker, and order type
- feed poor execution outcomes back into symbol selection and risk sizing

Implemented:

- execution-quality samples are now persisted per order with intended vs realized price, slippage, spread cost, fill ratio, and time-to-fill
- API endpoints now expose both raw execution-quality samples and grouped TCA summaries by symbol/venue/broker/order type
- scan-time symbol selection now blocks entries when execution quality is persistently poor
- deterministic risk sizing now applies execution-feedback scaling so degraded fill quality reduces approved position size

## Phase 8: Improve Observability And Operations

Current repo status: completed.

### Add structured logging and metrics

What to add or modify:

- JSON logs
- request IDs
- run IDs propagated through services
- counters for approvals, rejections, malformed outputs, execution failures
- latency metrics for Alpaca and OpenAI calls

Implemented:

- API middleware now emits structured JSON logs with request IDs, status codes, and request-latency measurements.
- worker and execution task boundaries now emit counters and latency metrics for scans, reconciliation, intent execution, and backtests.
- Alpaca and LLM client calls now emit latency/counter telemetry for success and error paths.
- a performance summary API now exposes aggregated counters and latency distributions for operator visibility.

### Add alerts

What to add or modify:

- notify on repeated worker failures
- notify on kill-switch activation
- notify on broker reconciliation mismatch
- notify on unusually high rejection rates or malformed agent outputs

Implemented:

- alert synthesis now emits `alert_worker_failures`, `alert_high_rejection_rate`, and `alert_malformed_outputs` based on recent runtime windows.
- kill-switch and reconciliation pause conditions now emit dedicated operational alerts.
- alerts are persisted as risk events with `alert_*` codes and exposed through a dedicated alerts API read.

### Add dashboard depth for operators

What to add or modify:

- performance charts
- backtest result pages
- per-symbol audit history
- per-agent disagreement analysis
- open risk budget visualization

Implemented:

- the risk dashboard now includes a performance snapshot panel with rejection pressure, malformed/scan-failure counts, and top metric latency/counter tables.
- the risk dashboard now includes an operational alerts panel sourced from persisted `alert_*` events.
- execution-quality/TCA panels remain integrated with filtering and now sit alongside the new observability surface.

Suggested files:

- [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx)
- new route pages under `web/app/`

## Phase 9: Improve Testing And Release Discipline

Current repo status: completed.

### Expand tests beyond unit checks

What to add or modify:

- API tests
- worker task tests
- broker adapter contract tests
- model payload validation tests
- end-to-end replay tests

Implemented:

- API integration coverage now includes auth/session flow, protected observability endpoints, and request-ID middleware behavior.
- worker task coverage now validates intent dispatch and replay-task output contracts.
- broker adapter contract coverage now validates routing guardrails plus Alpaca error/order normalization behavior.
- payload validation coverage now verifies committee decision model constraints and enum alignment against `committee-decision.schema.json`.
- replay E2E coverage now runs deterministic fixture-backed regression checks under a dedicated `replay` pytest marker.

### Add CI and quality gates

What to add or modify:

- lint
- type checks
- unit tests
- replay regression tests
- schema drift checks

Implemented:

- CI workflow now runs backend lint (`ruff`), backend type checks (`mypy`), backend unit tests, replay-regression tests, and web TypeScript checks.
- schema drift validation now runs as a dedicated quality gate using `backend/scripts/check_schema_drift.py`.
- replay regression is now isolated into marker-based test gates for clear pass/fail release evidence.

### Add release notes for strategy changes

What to add or modify:

- treat strategy logic changes like product releases
- document changes in prompt versions, risk rules, execution behavior, and thresholds

Implemented:

- strategy changes are now documented in [strategy-change-log.md](./strategy-change-log.md) with a structured release template.
- the strategy change log now includes release entries for Phase 7, Phase 8, and Phase 9, including replay evidence and rollback notes.

## Suggested New Files And Modules

High-value additions:

- `backend/src/tradingbot/services/broker_capabilities.py`
- `backend/src/tradingbot/services/calendar.py`
- `backend/src/tradingbot/services/contracts.py`
- `backend/src/tradingbot/services/pretrade.py`
- `backend/src/tradingbot/services/reconciliation.py`
- `backend/src/tradingbot/services/portfolio.py`
- `backend/src/tradingbot/services/features.py`
- `backend/src/tradingbot/services/prompt_registry.py`
- `backend/src/tradingbot/services/evaluation.py`
- `backend/src/tradingbot/services/alerts.py`
- `backend/src/tradingbot/api/routers/backtests.py`
- `backend/src/tradingbot/api/routers/performance.py`
- `backend/src/tradingbot/worker/execution_tasks.py`
- `backend/src/tradingbot/worker/replay_tasks.py`
- `backend/tests/fixtures/`
- `docs/strategy-change-log.md`

Status: the files above now exist in the current repo.

## Must-Have Features Before Calling This A Real Auto-Trading Bot

Minimum bar:

- real broker capability mapping, not assumed execution
- full order lifecycle handling with partial fills and cancel or replace
- broker reconciliation against local truth
- market calendar and session gating
- realistic backtests with fill modeling
- portfolio-aware risk and circuit breakers
- operator-visible live safety controls
- deterministic handling of unsupported products and broken broker states

## Suggested Immediate Next 5 Upgrades

If the goal is maximum improvement for the next development cycle, do these first:

1. Enable GitHub branch protection so `CI` and `Release Guard` are required and reviewer approval is enforced at the host level.
2. Expand replay fixtures across more symbols/regimes and add failure-injection scenarios for broker/provider instability.
3. Add release-level controls for strategy/risk threshold rollout and rollback auditability across staged environments.
4. Expand multi-market broker coverage beyond executable US cash equities.
5. Add direct broker-native streaming or tighter sub-second state convergence beyond the current backend SSE layer.

## Definition Of "Expert" For This Repo

This bot becomes meaningfully closer to expert-grade when it can do all of the following:

- explain why it entered or rejected a trade
- prove the strategy across replay and walk-forward tests
- execute only products the broker and venue actually support
- manage the full lifecycle of entries, exits, fills, cancels, and replacements
- protect capital with deterministic portfolio-aware risk
- handle bad provider and broker responses safely
- reconcile broker truth with internal truth
- surface failures clearly to the operator
- evolve prompts, models, broker support, and thresholds without losing auditability
