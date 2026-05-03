# Architecture

## High-Level Topology

```text
               Next.js Dashboard
                      |
                      v
                 FastAPI API ─── /metrics (Prometheus)
                      |          /health/detailed
            +---------+---------+
            |                   |
            v                   v
         Postgres           Redis/Celery
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
                 Worker                Stream Supervisor
                    |                       |
       +------------+------------+         |
       |            |            |         |
       v            v            v         v
   OpenAI/      Alpaca APIs   ML Signal  Alpaca WebSocket
   Gemini       (REST)        Pipeline   (Polling Fallback)
```

## Backend Layers

### API Layer

Located in `backend/src/tradingbot/api`.

Responsibilities:

- request validation
- auth gating
- route registration
- API serialization
- Prometheus metrics export (`/metrics`)
- component-level health checks (`/health/detailed`)

Key files:

- [main.py](../backend/src/tradingbot/api/main.py)
- [dependencies.py](../backend/src/tradingbot/api/dependencies.py)
- [trading.py](../backend/src/tradingbot/api/routers/trading.py)
- [metrics_export.py](../backend/src/tradingbot/api/routers/metrics_export.py)

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

- Alpaca broker/data/news adapters (with protocol support for Zerodha, IBKR, Binance, Coinbase)
- OpenAI and Gemini agent runners with retry/backoff logic
- indicator and feature computation
- structured event extraction (earnings, analyst actions, macro/calendar, sector context)
- scan-time data quality validation (staleness, missing candles, feed gaps, delayed news)
- prompt registry and versioned committee prompts
- committee proposal/finalization across specialist roles plus chair summary
- output-schema repair flow for malformed agent payloads
- deterministic risk validation
- execution-quality modeling and adaptive aggressiveness planning
- market calendar/session enforcement
- execution persistence
- execution intent queuing and approval handling
- post-submit execution/TCA analytics and symbol-quality feedback
- distributed tracing context propagation (trace_id/span_id via `otel.py`)
- structured JSON logging and in-process metric aggregation with Prometheus export
- multi-channel alert dispatch (webhook/Slack/PagerDuty/Opsgenie) with severity routing and suppression
- stream supervisor framework with Alpaca WebSocket adapter
- FX conversion service with rate caching and USD triangulation
- ML signal pipeline with gradient-boost ensemble and LLM score blending
- Monte Carlo simulation and stress testing (VaR/CVaR, 6 built-in scenarios)
- compliance reporting (PDT detection, wash-sale detection, position limits)
- LLM cost tracking and intelligent scan scheduling
- settings persistence
- research backtest simulation (slippage, commission, delayed fills, rejects)
- walk-forward and regime scoring
- persisted backtest report assembly
- post-trade review generation and recurring-pattern classification

Key service modules (35 total):

| Module | Purpose |
|--------|---------|
| `adapters.py` | Broker adapter protocol + Alpaca implementation |
| `agents.py` | LLM specialist agents |
| `committee.py` | Multi-agent committee orchestration |
| `risk.py` | Deterministic risk engine |
| `execution.py` | Order lifecycle + VWAP tracking |
| `otel.py` | Distributed tracing (trace_id/span_id) |
| `metrics.py` | Counters + durations + Prometheus export |
| `alert_dispatch.py` | Multi-channel alert routing with suppression |
| `stream_supervisor.py` | WebSocket broker streaming framework |
| `ml_signals.py` | ML signal pipeline + gradient boost |
| `monte_carlo.py` | Monte Carlo simulation + stress tests |
| `compliance.py` | PDT / wash-sale / position limits |
| `cost_tracking.py` | LLM cost tracking + scan scheduling |
| `fx.py` | FX conversion service |
| `llm_clients.py` | OpenAI/Gemini clients with retry logic |

### Worker Layer

Located in `backend/src/tradingbot/worker`.

Responsibilities:

- task registration
- beat schedule
- recurring market scans
- execution-intent dispatch
- asynchronous backtests with persisted report lifecycle (`queued` -> `running` -> `succeeded`/`failed`)
- stream supervisor lifecycle tasks (start/stop/health-check)

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
- intraday drawdown circuit thresholds
- stop distance sanity with ATR-aware normalization
- buying power
- single-symbol notional cap
- gross exposure cap
- sector and correlation concentration caps
- event-cluster concentration caps
- cooldown state
- runtime execution-failure guardrails

Sizing is then scaled by:

- volatility target
- strategy confidence
- equity-curve drawdown throttle
- loss-streak throttle
- execution-quality feedback scale

### 7. Intent handoff

If approved, the worker persists an execution intent instead of submitting inline.

### 8. Execution boundary

A dedicated execution task re-checks kill switch state, market session, live enablement, and broker connectivity before broker submission.
The execution service also computes pre-submit fill-quality expectations (spread/slippage/liquidity) and can reject poor setups before they reach the broker.

### 9. Execution analytics and feedback

Order outcomes persist execution-quality samples with intended vs realized fill metrics, slippage, spread cost, and time-to-fill.
Recent symbol-level quality is summarized into feedback signals that can block weak symbols or throttle risk sizing in subsequent scans.

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

## Observability And Alert Flow

1. API middleware assigns/propagates a request ID and emits structured request-start/request-complete logs.
2. Distributed tracing context (`otel.py`) provides trace_id and span_id propagation across API → worker → broker calls via `contextvars`.
3. Worker and execution tasks emit counters and latency distributions for scan/reconciliation/intent/backtest boundaries.
4. Alpaca adapter and LLM clients emit external-call latency and success/error counters.
5. Prometheus-compatible `/metrics` endpoint exposes all counters and duration histograms for external scraping.
6. `/health/detailed` provides component-level status for database, Redis, LLM provider, broker, and tracing.
7. Alert synthesis evaluates runtime windows and emits persisted `alert_*` events for worker instability, reconciliation stress, kill-switch activation, and rejection/malformed spikes.
8. Multi-channel alert dispatch routes alerts by severity: info → webhook, warning → + Slack, critical → + PagerDuty/Opsgenie, with per-code suppression and deduplication.
9. Operators consume these signals via `/performance/summary`, `/alerts`, and `/stream/operations`.

## Stream Supervisor Flow

1. Celery task starts a `StreamSupervisor` in a daemon thread for a given trading profile.
2. The supervisor connects to the broker (Alpaca WebSocket or REST polling fallback).
3. Events are parsed and processed through the execution service order state machine.
4. On disconnect, the supervisor automatically reconnects with exponential backoff (1s → 60s).
5. On reconnect, missed events are backfilled from the broker REST API.
6. A periodic health-check task auto-restarts dead supervisors for enabled profiles.

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
- `symbol_cooldowns`
- `execution_quality_samples`
- `trade_reviews`
- `audit_logs`
- `backtest_reports`
- `backtest_trades`

Schema evolution is versioned with Alembic under `backend/alembic/`.

## Current Limitations

- Sector/correlation concentration currently uses heuristic buckets rather than a full factor model
- The stream supervisor uses REST polling as a WebSocket fallback since Python stdlib lacks a WebSocket client — a production deployment should add the `websockets` library for true sub-second latency
- ML model training currently uses a pure-Python gradient-boost implementation; production ML pipelines should integrate scikit-learn or similar for performance
- Production secret rotation and managed edge controls still remain external
