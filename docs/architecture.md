# Architecture

## High-Level Topology

```text
Next.js dashboard
        |
        v
    FastAPI API
        |
        +--------------------+
        |                    |
        v                    v
     Postgres             Redis/Celery
                              |
                              v
                           Worker
                              |
                 +------------+------------+
                 |                         |
                 v                         v
             OpenAI API               Alpaca APIs
```

## Backend Layers

### API Layer

Located in `backend/src/tradingbot/api`.

Responsibilities:

- request validation
- auth gating
- route registration
- API serialization

Key files:

- [main.py](../backend/src/tradingbot/api/main.py)
- [dependencies.py](../backend/src/tradingbot/api/dependencies.py)
- [trading.py](../backend/src/tradingbot/api/routers/trading.py)

### Schema Layer

Located in `backend/src/tradingbot/schemas`.

Responsibilities:

- request/response models
- committee decision shape
- settings payloads
- auth payloads

### Service Layer

Located in `backend/src/tradingbot/services`.

Responsibilities:

- Alpaca broker/data/news adapters
- OpenAI agent runner
- indicator computation
- committee proposal/finalization
- deterministic risk validation
- market calendar/session enforcement
- execution persistence
- execution intent queuing and approval handling
- settings persistence
- backtest orchestration

### Worker Layer

Located in `backend/src/tradingbot/worker`.

Responsibilities:

- task registration
- beat schedule
- recurring market scans
- execution-intent dispatch
- asynchronous backtests

## Trading Decision Flow

### 1. Market data collection

The worker pulls recent intraday bars and recent symbol news from Alpaca.

### 2. Feature preparation

The service computes simple indicators:

- SMA 10
- SMA 20
- RSI 14
- average volume
- momentum percentage

### 3. Agent generation

- The market agent evaluates the technical setup.
- The news agent evaluates catalyst quality and sentiment.

Each agent must produce a structured JSON payload conforming to the shared decision shape.

### 4. Committee proposal

The committee service merges the market/news outputs into a single proposed trade idea.

### 5. Deterministic risk review

The risk engine checks:

- direction support
- max open positions
- daily loss budget
- stop distance sanity
- buying power
- single-symbol notional cap
- current symbol exposure
- cooldown state

### 6. Intent handoff

If approved, the worker persists an execution intent instead of submitting inline.

### 7. Execution boundary

A dedicated execution task re-checks kill switch state, market session, live enablement, and broker connectivity before broker submission.

## Storage Model

Current ORM models cover:

- `bot_settings`
- `watchlist_symbols`
- `operator_sessions`
- `agent_runs`
- `trade_candidates`
- `execution_intents`
- `orders`
- `order_state_transitions`
- `order_fills`
- `positions`
- `instrument_contracts`
- `reconciliation_mismatches`
- `risk_events`
- `portfolio_snapshots`
- `audit_logs`

Schema evolution is versioned with Alembic under `backend/alembic/`.

## Current Limitations

- No websocket/event streaming
- No sector exposure model
- Frontend build/type validation was not run in this task because local Node dependencies were intentionally not installed
- The current auth/session layer is stronger than the original scaffold, but still needs production extras such as CSRF hardening, rate limiting, and managed secret rotation
