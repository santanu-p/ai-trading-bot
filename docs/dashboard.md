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
- audit log
- run history

Risk displays risk events, reconciliation mismatches, and audit history.

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
