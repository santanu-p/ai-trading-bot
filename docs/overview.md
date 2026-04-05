# System Overview

## Goal

This repository is a server-first AI trading bot scaffold aimed at a single operator running an intraday equities workflow on Alpaca. The design favors explainable service boundaries over a monolithic script:

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
- long-only equities flow
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
- read APIs for runs, decisions, orders, positions, and risk events
- backtest job submission

### Worker

The worker owns:

- periodic market scans
- watchlist iteration
- agent invocation
- committee formation
- deterministic risk checks
- order submission
- persistence of run/candidate/order events
- backtest job execution

### Dashboard

The dashboard owns:

- operator login UI
- polling for current backend state
- control actions for start/stop/mode/kill switch
- settings editing
- operational visibility for trades, decisions, and failures

## Data Ownership

- The backend is the source of truth for all application state.
- The dashboard should never call Alpaca or OpenAI directly.
- Broker responses are persisted so the UI can reflect current status without re-deriving it.

