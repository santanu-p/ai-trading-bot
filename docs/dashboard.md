# Dashboard

## Purpose

The dashboard is an operator console rather than a marketing site or analyst workspace. It is optimized for:

- status visibility
- fast controls
- dense scanning of orders, decisions, and failures
- direct settings updates

## Routes

- `/` overview
- `/orders`
- `/decisions`
- `/risk`
- `/backtests`
- `/settings`

## First-Run Intake

Before the bot can be started, the operator now has to complete an agent-intake flow. The UI asks for:

- trading pattern
- instrument class
- strategy family
- risk profile
- market universe
- extra notes for the agents

These answers are persisted in backend settings and injected into the market/news agent prompts before they analyze the watchlist.

## UX Model

### Login

The operator authenticates against the backend with a secure HTTP-only cookie session.

Roles:

- `reviewer`: read-only visibility
- `operator`: bot controls and intent approvals
- `admin`: settings changes, live enablement, and forced logout

### Polling

The dashboard polls the backend every 30 seconds for:

- settings
- execution intents
- runs
- decisions
- orders
- positions
- risk events
- audit logs
- operator sessions
- backtest report summaries

### Actions

The sidebar exposes:

- Start bot
- Stop bot
- Flip mode
- Toggle kill switch
- Reconcile now
- Cancel all open orders
- Flatten all
- Sign out

The `Start bot` action is disabled until the intake is complete.

The settings route adds:

- live enablement code generation
- live enable/disable controls
- broker kill
- session review and admin revocation
- full bot settings editing for admins

### Data Views

Overview displays:

- market session state
- live-safety state
- execution-intent review queue
- broker capability coverage
- current positions
- committee feed
- decision-time feature/event/timestamp context from scan payloads
- audit log
- run history

Backtests displays:

- research backtest launch form
- persisted report history
- report metrics (return/drawdown/sharpe/win rate/expectancy/turnover/exposure)
- walk-forward window summary
- regime-level performance breakdown

Risk displays risk events, reconciliation mismatches, and audit history.
Risk events now include explicit data-quality rejection codes when stale or incomplete feeds block symbols.
Risk also now includes execution-quality analytics panels for grouped TCA summaries and recent per-order fill-quality samples.
Operators can now filter these execution-quality panels by summary dimension (`symbol`/`venue`/`broker`/`order_type`) and sample filters (symbol, order status, row limits).
Risk now also includes a Phase 8 observability surface:

- an operational alerts panel sourced from `alert_*` backend events
- a performance snapshot panel with recent rejection pressure, malformed-output counts, scan-failure counts, portfolio position/exposure metrics, latest equity signals, and top latency/counter metrics

Settings displays editable fields for all configurable guardrails and the watchlist plus live safety controls and session management.

## Frontend Notes

- The UI is built without a component library.
- Styling is contained in `web/app/globals.css`.
- The main surface is [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx).
- API helpers live in [api.ts](../web/src/lib/api.ts).

## Current Limitations

- No websocket streaming.
- No optimistic state reconciliation.
- Frontend type-check/build validation was not run in this task because local Node dependencies were intentionally not installed.
