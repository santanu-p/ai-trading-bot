# Backend API

## Authentication

### `POST /auth/login`

Authenticates the single admin user and returns a bearer token.

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
  "access_token": "token",
  "token_type": "bearer",
  "expires_in_minutes": 720
}
```

## Health

### `GET /health`

Simple health probe.

Response:

```json
{
  "status": "ok"
}
```

## Settings

### `GET /settings`

Returns bot configuration and watchlist state.

### `PUT /settings`

Updates:

- scan interval
- consensus threshold
- max open positions
- max daily loss
- per-position risk
- symbol notional cap
- symbol cooldown
- OpenAI model
- watchlist

## Bot Control

### `POST /bot/start`

Marks the bot as running.

### `POST /bot/stop`

Marks the bot as stopped.

### `POST /bot/mode`

Request:

```json
{
  "mode": "paper"
}
```

Allowed values:

- `paper`
- `live`

### `POST /bot/kill-switch?enabled=true|false`

Enables or disables the kill switch.

## Operational Reads

### `GET /runs`

Returns recent worker scan runs.

Query params:

- `limit`

### `GET /decisions`

Returns recent committee decisions persisted as trade candidates.

### `GET /orders`

Returns recent order records.

### `GET /positions`

Returns current persisted positions.

### `GET /risk-events`

Returns recent risk and failure events.

## Backtests

### `POST /backtests`

Queues a backtest/replay request.

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

## Auth Model

- All routes except `/auth/login` and `/health` require a bearer token.
- Tokens are signed with the configured JWT secret and expiry.
- The current build assumes one admin identity.

