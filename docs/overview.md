# System Overview

## Goal

This repository is a server-first AI trading bot aimed at a single operator running an intraday workflow with explicit execution safety controls. The design favors explainable service boundaries over a monolithic script:

- `FastAPI` exposes the operator API and Prometheus metrics
- `Celery` handles scheduled scans, backtests, and stream supervisor health
- `SQLAlchemy` persists bot state
- `Next.js` provides the operator console
- `OpenAI` / `Gemini` supply the market and news agent reasoning
- `Alpaca` supplies broker, market data, and news data integrations

## Product Shape

The current build is intentionally narrow:

- single-tenant
- admin-operated
- Alpaca-backed execution flow (with capability gating for unsupported profiles)
- paper-first, live-ready interfaces
- scheduled intraday scans rather than low-latency execution
- extensible to additional brokers (Zerodha, IBKR, Binance, Coinbase) via the adapter protocol

It is not a social trading product, a copy-trading marketplace, or a generalized quant research platform.

## Main Subsystems

### Backend API

The API owns:

- login/session issuance
- bot status changes
- trading mode changes
- kill-switch changes
- settings updates
- read APIs for runs, decisions, orders, positions, risk events, reconciliation mismatches, and execution intents
- read APIs for persisted backtest reports and per-report simulation detail
- order lifecycle controls (replace/cancel/cancel-all)
- reconciliation triggers and live-safety controls (flatten-all, broker-kill)
- backtest job submission
- Prometheus-compatible metrics scrape endpoint (`/metrics`)
- component-level health checks (`/health/detailed`)

### Worker

The worker owns:

- periodic market scans
- watchlist iteration
- agent invocation
- feature engineering (volatility, ATR, gap, opening-range, relative-volume, multi-timeframe alignment)
- structured event enrichment (earnings/analyst/macro/sector/calendar context)
- data freshness and feed-quality gating before agent inference
- structured specialist committee formation with prompt-version lineage
- malformed-output repair flow for agent payloads
- deterministic portfolio-aware risk checks (gross/sector/correlation/event concentration)
- dynamic position sizing (ATR/volatility/confidence/equity-curve/loss-streak scaling)
- runtime risk guardrails (drawdown circuit checks, execution-failure review gating, severe-anomaly kill-switch automation)
- outcome-aware symbol cooldown enforcement
- execution-intent queueing and dispatch
- broker reconciliation, fill ingestion, and local position sync
- child-order repair and session-close flatten handoff
- persistence of run/candidate/order events
- research backtest execution with delayed/rejected fill simulation
- walk-forward/regime scoring and report persistence
- post-trade review queue generation for losing exits and recurring failure patterns
- stream supervisor lifecycle management (start/stop/health checks)

### Stream Supervisor

The stream supervisor owns:

- long-running broker WebSocket connections (Alpaca adapter with REST polling fallback)
- automatic reconnection with exponential backoff
- heartbeat monitoring and timeout detection
- event backfill from REST API on reconnect
- integration with the execution service order state machine
- supervisor registry for singleton lifecycle management

### Observability Pipeline

The observability pipeline owns:

- distributed tracing via `contextvars` (trace_id / span_id propagation)
- W3C Trace-Context header generation and parsing
- in-process metric counters and latency distributions
- Prometheus text exposition format export
- multi-channel alert dispatch (webhook, Slack, PagerDuty, Opsgenie)
- alert suppression / deduplication with configurable cooldown windows
- severity-based escalation routing (info → warning → critical → page)

### ML Signal Pipeline

The ML pipeline owns:

- feature matrix builder from computed indicators
- abstract model interface with predict / train / save / load
- gradient-boost decision stump ensemble (pure Python, no sklearn dependency)
- local filesystem model persistence (`data/models/`)
- signal blending with LLM committee confidence scores (configurable weights)

### Compliance & Cost Tracking

The compliance layer owns:

- automated daily trade report generation
- Pattern Day Trader (PDT) detection (FINRA 4-in-5 rule)
- IRS wash-sale detection across 30-day windows
- position concentration limit monitoring
- per-call LLM token usage and cost estimation
- aggregated spend reporting by provider, model, and operation
- intelligent scan scheduling based on market hours, volatility, and recency

### Multi-Currency Support

The FX service owns:

- currency conversion with cache → API → fallback rate resolution
- USD triangulation for cross-rates
- portfolio exposure aggregation in base currency

### Monte Carlo & Stress Testing

The simulation engine owns:

- Monte Carlo simulation with trade-return resampling
- tail risk estimation (VaR, CVaR at 95/99 confidence)
- 6 built-in stress scenarios (flash crash, circuit breaker, gap-down, liquidity crisis, vol spike, sector rotation)
- adverse fill modeling under different market conditions

### Dashboard

The dashboard owns:

- operator login UI
- polling plus SSE subscription for current backend state
- control actions for start/stop/mode/kill switch/live-enable
- intent approval and rejection workflow
- reconciliation, order lifecycle, flatten-all, and broker-kill actions
- settings editing
- operational visibility for trades, decisions, failures, review queues, prompt attribution, and open risk budget

## Data Ownership

- The backend is the source of truth for all application state.
- The dashboard should never call Alpaca or OpenAI directly.
- Broker responses, order transitions, and fills are persisted so the UI can reflect lifecycle state without re-deriving it.
- Decision payloads now persist feature snapshots, structured event context, and decision-time data timestamps for auditability.
- Agent runs now also persist model/prompt lineage and committee input snapshots for later trade-review comparisons.
- Symbol-level cooldown state is now persisted and refreshed from filled-exit outcomes so re-entry throttles survive worker restarts.
