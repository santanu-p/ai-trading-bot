# Backend API

## Auth Model

- All routes except `/auth/login` and `/health` require a secure HTTP-only session cookie.
- The backend supports `reviewer`, `operator`, and `admin` roles.
- Session state is persisted in `operator_sessions`, can expire, and can be revoked by an admin.

## Authentication

### `POST /auth/login`

Authenticates an operator and sets the session cookie.

Request:

```json
{
  "email": "admin@example.com",
  "password": "change-me"
}
```

Response:

```json
{
  "authenticated": true,
  "email": "admin@example.com",
  "role": "admin",
  "expires_at": "2026-04-08T12:00:00Z",
  "session_id": "uuid"
}
```

### `GET /auth/me`

Returns the currently authenticated operator session.

### `POST /auth/logout`

Revokes the current session and clears the cookie.

### `GET /auth/sessions`

Returns session history.

- admins can inspect all sessions or filter by `email`
- non-admins only see their own sessions

### `POST /auth/sessions/{session_id}/revoke`

Admin-only forced logout for a specific session.

## Health

### `GET /health`

Simple health probe.

## Settings

### `GET /settings`

Returns:

- bot status and mode
- `live_enabled` and environment live gating
- watchlist and risk configuration
- broker metadata and capability matrix
- analysis scope vs executable scope
- current market session state

### `PUT /settings`

Admin-only update for:

- scan interval
- consensus threshold
- open-position and loss caps
- model selection
- watchlist
- broker metadata
- strategy intake fields

## Bot Control

### `POST /bot/start`

Operator/admin endpoint. Starts the worker loop after intake and execution-scope checks.

### `POST /bot/stop`

Operator/admin endpoint. Stops the worker loop.

### `POST /bot/mode`

Switches between `paper` and `live`.

### `POST /bot/kill-switch?enabled=true|false`

Operator/admin endpoint. Arms or clears the global kill switch.

### `POST /bot/live/prepare`

Admin-only endpoint. Generates a short-lived live-enablement code.

### `POST /bot/live/enable`

Admin-only endpoint. Requires the live-enablement code and sets `live_enabled=true`.

### `POST /bot/live/disable`

Admin-only endpoint. Clears `live_enabled` and any pending approval code.

### `POST /bot/flatten-all`

Operator/admin endpoint. Cancels open orders and requests a flatten-all action.

### `POST /bot/broker-kill`

Operator/admin endpoint. Forces broker-side order cancellation and disables live execution.

## Intent And Execution Reads

### `GET /execution-intents`

Returns recent execution intents.

Query params:

- `status`
- `limit`

### `POST /execution-intents/{intent_id}/approve`

Operator/admin endpoint. Approves an execution intent and queues it for the execution worker.

### `POST /execution-intents/{intent_id}/reject`

Operator/admin endpoint. Rejects an execution intent with a `detail` query string reason.

## Operational Reads

### `GET /runs`

Returns recent worker scan runs.

### `GET /decisions`

Returns committee decisions persisted as trade candidates.

### `GET /orders`

Returns persisted order records.

### `GET /orders/{order_id}/transitions`

Returns local order lifecycle transitions.

### `GET /orders/{order_id}/fills`

Returns recorded fills for an order.

### `POST /orders/{order_id}/cancel`

Operator/admin endpoint. Cancels a single order.

### `POST /orders/cancel-all`

Operator/admin endpoint. Cancels all open orders.

### `GET /positions`

Returns persisted positions.

### `GET /risk-events`

Returns risk and failure events.

### `GET /audit-logs`

Returns recent audit log rows.

Query params:

- `action`
- `actor`
- `limit`

### `GET /reconciliation/mismatches`

Returns reconciliation mismatches.

Query params:

- `include_resolved`
- `limit`

### `POST /reconciliation/run`

Operator/admin endpoint. Runs an immediate reconciliation pass.

## Backtests

### `POST /backtests`

Operator/admin endpoint. Queues a replay/backtest request.

Request:

```json
{
  "symbols": ["AAPL", "MSFT"],
  "start": "2026-04-01T13:30:00Z",
  "end": "2026-04-03T20:00:00Z",
  "interval_minutes": 5
}
```

Response:

```json
{
  "accepted": true,
  "task_id": "celery-task-id"
}
```
