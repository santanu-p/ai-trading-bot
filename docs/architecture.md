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
- indicator and feature computation
- structured event extraction (earnings, analyst actions, macro/calendar, sector context)
- scan-time data quality validation (staleness, missing candles, feed gaps, delayed news)
- prompt registry and versioned committee prompts
- committee proposal/finalization across specialist roles plus chair summary
- output-schema repair flow for malformed agent payloads
- deterministic risk validation
- market calendar/session enforcement
- execution persistence
- execution intent queuing and approval handling
- settings persistence
- research backtest simulation (slippage, commission, delayed fills, rejects)
- walk-forward and regime scoring
- persisted backtest report assembly
- post-trade review generation and recurring-pattern classification

### Worker Layer

Located in `backend/src/tradingbot/worker`.

Responsibilities:

- task registration
- beat schedule
- recurring market scans
- execution-intent dispatch
- asynchronous backtests with persisted report lifecycle (`queued` -> `running` -> `succeeded`/`failed`)

## Trading Decision Flow

### 1. Market data collection

The worker pulls recent intraday bars and recent symbol news from Alpaca.

### 2. Feature preparation

The service computes engineered features, including:

- SMA 10 / SMA 20 / RSI 14
- intraday volatility and ATR stop-distance context
- gap statistics and opening-range structure
- relative volume and multi-timeframe trend alignment
- SPY/QQQ index trend and breadth context

### 3. Data-quality gate

Before agent calls, the worker validates:

- bar freshness
- delayed news snapshots when timeliness matters
- missing-candle ratio
- abnormal feed gaps

Symbols that fail these checks are persisted as explicit data-quality rejections.

### 4. Agent generation

- The technical-structure specialist evaluates setup quality.
- The catalyst specialist evaluates news and event context.
- The market-regime specialist evaluates the broader tape.
- The portfolio-exposure specialist evaluates crowding and account state.
- The execution-quality specialist evaluates likely fill quality.
- The chair summarizes specialist views into a single pre-risk recommendation.

Each role must produce a structured JSON payload conforming to its schema. Malformed outputs trigger one repair pass before the trade is rejected.

### 5. Committee proposal

The committee service merges specialist outputs into a single proposed trade idea, requiring majority-style approval plus chair alignment before the deterministic risk layer sees the trade.

### 6. Deterministic risk review

The risk engine checks:

- direction support
- max open positions
- daily loss budget
- stop distance sanity
- buying power
- single-symbol notional cap
- current symbol exposure
- cooldown state

### 7. Intent handoff

If approved, the worker persists an execution intent instead of submitting inline.

### 8. Execution boundary

A dedicated execution task re-checks kill switch state, market session, live enablement, and broker connectivity before broker submission.

## Post-Trade Review Flow

1. Filled exit orders are detected during fill ingestion.
2. The evaluation service resolves the originating run/model/prompt lineage when available.
3. The closed trade is scored against its original thesis.
4. Losing trades are classified into failure causes such as `bad_signal`, `bad_context`, `bad_execution`, or `avoidable_risk`.
5. Negative reviews are queued for operator follow-up and recurring patterns raise a warning event.

## Backtest Research Flow

1. Operator queues a backtest request (`/backtests`) with simulation parameters.
2. API persists a `backtest_reports` row in `queued` status.
3. Worker picks up the task and marks it `running`.
4. Backtest service replays historical bars/news, simulates delayed/rejected fills, and applies slippage + commission.
5. Service computes portfolio metrics, walk-forward windows, regime breakdown, and equity-curve payload.
6. Worker persists summary + detail payloads in `backtest_reports` and per-trade rows in `backtest_trades`.

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
- `backtest_reports`
- `backtest_trades`

Schema evolution is versioned with Alembic under `backend/alembic/`.

## Current Limitations

- No websocket/event streaming
- No sector exposure model
- Frontend build/type validation was not run in this task because local Node dependencies were intentionally not installed
- The current auth/session layer is stronger than the original scaffold, but still needs production extras such as CSRF hardening, rate limiting, and managed secret rotation
