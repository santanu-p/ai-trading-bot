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

The operator authenticates against the backend and stores the JWT in `localStorage`.

### Polling

The dashboard polls the backend every 30 seconds for:

- settings
- runs
- decisions
- orders
- positions
- risk events

### Actions

The sidebar exposes:

- Start bot
- Stop bot
- Flip mode
- Toggle kill switch

The `Start bot` action is disabled until the intake is complete.

### Data Views

Overview displays:

- current positions
- committee feed
- execution log
- run history

Settings displays editable fields for all configurable guardrails and the watchlist.

## Frontend Notes

- The UI is built without a component library.
- Styling is contained in `web/app/globals.css`.
- The main surface is [dashboard-screen.tsx](/D:/project1/web/src/components/dashboard-screen.tsx).
- API helpers live in [api.ts](/D:/project1/web/src/lib/api.ts).

## Current Limitations

- JWT is stored in `localStorage`, which is acceptable for this scaffold but not ideal for hardened production auth.
- No websocket streaming.
- No optimistic state reconciliation.
- No route protection on the server side beyond the client-side login gate.
