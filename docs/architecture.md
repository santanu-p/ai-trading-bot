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
- execution persistence
- settings persistence
- backtest orchestration

### Worker Layer

Located in `backend/src/tradingbot/worker`.

Responsibilities:

- task registration
- beat schedule
- recurring market scans
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

### 6. Execution

If approved, the execution service submits a bracket order through the broker adapter and persists the result.

## Storage Model

Current ORM models cover:

- `bot_settings`
- `watchlist_symbols`
- `agent_runs`
- `trade_candidates`
- `orders`
- `positions`
- `risk_events`
- `portfolio_snapshots`
- `audit_logs`

The current app boot path uses `Base.metadata.create_all(...)` on startup when `AUTO_CREATE_TABLES` is enabled.

## Current Limitations

- No Alembic migration flow is wired yet
- No explicit market-hours calendar enforcement yet
- No websocket/event streaming
- No account reconciliation worker
- No sector exposure model
- No human approval queue for live trading

