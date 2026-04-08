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

### `GET /authz/current`

Returns the current authenticated operator identity (`email`, `role`, `expires_at`, `session_id`).

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
- portfolio exposure caps (gross, sector, correlation, event-cluster)
- sizing controls (ATR multiplier, volatility target, equity-curve throttle, loss-streak throttle)
- circuit-breaker controls (drawdown pause, execution-failure review threshold, severe-anomaly kill-switch threshold)
- outcome-aware cooldown windows (base/profit/stopout/event/whipsaw)
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

Each `decision_payload` now includes:

- engineered feature snapshot
- structured event context
- data-quality diagnostics
- decision-time data timestamps
- committee metadata including specialist outputs, chair summary, model name, and prompt versions

### `GET /decisions`

Returns committee decisions persisted as trade candidates.

Phase 5 committee responses may also include:

- `chair_vote`
- `committee_notes`
- `agent_signals`
- `model_name`
- `prompt_versions`

### `GET /orders`

Returns persisted order records.

### `GET /orders/{order_id}/transitions`

Returns local order lifecycle transitions.

### `GET /orders/{order_id}/fills`

Returns recorded fills for an order.

### `POST /orders/{order_id}/replace`

Operator/admin endpoint. Replaces an existing order at the broker.

Request body fields are optional:

- `quantity`
- `limit_price`
- `stop_price`
- `take_profit`
- `time_in_force` (`day`, `gtc`, `ioc`, `fok`)

### `POST /orders/{order_id}/cancel`

Operator/admin endpoint. Cancels a single order.

### `POST /orders/cancel-all`

Operator/admin endpoint. Cancels all open orders.

Response includes:

- `canceled_orders`
- `flatten_submitted` (always `0` for this endpoint)

### `GET /positions`

Returns persisted positions.

### `GET /risk-events`

Returns risk and failure events.

Phase 5 adds `agent_output_malformed` and recurring `trade_review_pattern` events.
Phase 6 adds `auto_kill_switch` when severe anomaly clustering triggers an automatic safety halt.

## Trade Reviews

### `GET /trade-reviews`

Returns persisted post-trade reviews.

Query params:

- `status` (`queued` or `completed`)
- `loss_cause`
- `limit`

Each row includes:

- originating `source_run_id` when available
- `model_name`
- `prompt_versions`
- `review_score`
- realized `pnl` and `return_pct`
- classified `loss_cause`
- summary and structured review payload

### `GET /trade-reviews/summary`

Returns grouped review summaries by model and prompt signature so performance can be compared across committee versions.

### Symbol cooldown behavior

Filled exit orders now update persisted cooldown state, and subsequent scans enforce cooldown expiry before allowing new entries on the same symbol.

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

Response includes:

- `transitions_applied`
- `fills_ingested`
- `mismatches_created`
- `unresolved_mismatches`
- `live_paused` (`0` or `1`)

## Backtests

### `GET /backtests`

Returns persisted backtest report summaries (newest first).

Query params:

- `status` (optional: `queued`, `running`, `succeeded`, `failed`)
- `limit`

### `GET /backtests/{report_id}`

Returns a full backtest report:

- summary metrics
- walk-forward window metrics
- regime breakdown
- equity-curve payload
- symbol breakdown
- simulated trades

### `POST /backtests`

Operator/admin endpoint. Queues a research backtest request and persists a report row immediately with `queued` status.

Request:

```json
{
  "symbols": ["AAPL", "MSFT"],
  "start": "2026-04-01T13:30:00Z",
  "end": "2026-04-03T20:00:00Z",
  "interval_minutes": 5,
  "initial_equity": 100000,
  "slippage_bps": 5.0,
  "commission_per_share": 0.005,
  "fill_delay_bars": 1,
  "reject_probability": 0.03,
  "max_holding_bars": 24,
  "random_seed": 42
}
```

Response:

```json
{
  "accepted": true,
  "task_id": "celery-task-id",
  "report_id": "backtest-report-uuid"
}
```
