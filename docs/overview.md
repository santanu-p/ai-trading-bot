# System Overview

## Goal

This repository is a server-first AI trading bot scaffold aimed at a single operator running an intraday workflow with explicit execution safety controls. The design favors explainable service boundaries over a monolithic script:

- `FastAPI` exposes the operator API
- `Celery` handles scheduled scans and backtests
- `SQLAlchemy` persists bot state
- `Next.js` provides the operator console
- `OpenAI` supplies the market and news agent reasoning
- `Alpaca` supplies broker, market data, and news data integrations

## Product Shape

The current build is intentionally narrow:

- single-tenant
- admin-operated
- Alpaca-backed execution flow (with capability gating for unsupported profiles)
- paper-first, live-ready interfaces
- scheduled intraday scans rather than low-latency execution

It is not a social trading product, a copy-trading marketplace, or a generalized quant research platform.

## Main Subsystems

### Backend API

The API owns:

- login/auth token issuance
- bot status changes
- trading mode changes
- kill-switch changes
- settings updates
- read APIs for runs, decisions, orders, positions, risk events, reconciliation mismatches, and execution intents
- read APIs for persisted backtest reports and per-report simulation detail
- order lifecycle controls (replace/cancel/cancel-all)
- reconciliation triggers and live-safety controls (flatten-all, broker-kill)
- backtest job submission

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
- deterministic risk checks
- execution-intent queueing and dispatch
- broker reconciliation, fill ingestion, and local position sync
- child-order repair and session-close flatten handoff
- persistence of run/candidate/order events
- research backtest execution with delayed/rejected fill simulation
- walk-forward/regime scoring and report persistence
- post-trade review queue generation for losing exits and recurring failure patterns

### Dashboard

The dashboard owns:

- operator login UI
- polling for current backend state
- control actions for start/stop/mode/kill switch/live-enable
- intent approval and rejection workflow
- reconciliation, order lifecycle, flatten-all, and broker-kill actions
- settings editing
- operational visibility for trades, decisions, and failures

## Data Ownership

- The backend is the source of truth for all application state.
- The dashboard should never call Alpaca or OpenAI directly.
- Broker responses, order transitions, and fills are persisted so the UI can reflect lifecycle state without re-deriving it.
- Decision payloads now persist feature snapshots, structured event context, and decision-time data timestamps for auditability.
- Agent runs now also persist model/prompt lineage and committee input snapshots for later trade-review comparisons.
