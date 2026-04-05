# Expert Upgrade Roadmap

This file describes what to add or modify in the future to move this repository from a useful scaffold to an expert-grade trading system.

Important: "expert-grade" here means stronger research quality, execution quality, risk discipline, observability, and operational safety. It does not mean guaranteed profits.

## Current Baseline

The current repo already has:

- a FastAPI control plane
- a Celery worker for scheduled scans
- Alpaca broker/data/news adapters
- OpenAI-based market/news agent hooks
- deterministic risk validation
- a Next.js operator dashboard

The biggest gaps are not UI polish. They are research depth, execution realism, risk sophistication, evaluation discipline, and production hardening.

## Priority Order

Recommended order:

1. Safety and correctness
2. Research and backtesting quality
3. Data quality and feature depth
4. Execution quality
5. Portfolio construction
6. Model/agent sophistication
7. Production operations and scaling

## Phase 1: Fix The Foundations

### 1. Replace startup table creation with real migrations

Current issue:

- [main.py](/D:/project1/backend/src/tradingbot/api/main.py) uses `Base.metadata.create_all(...)`

What to add or modify:

- add Alembic configuration and migration scripts
- remove implicit table creation from app startup
- version all schema changes

Why:

- expert systems need reproducible schema evolution and safe deploys

### 2. Add explicit market-hours and trading-calendar gating

Current issue:

- the worker runs on a fixed interval but does not yet enforce exchange calendars or holiday handling

What to add or modify:

- add a market calendar service in `backend/src/tradingbot/services/`
- block scans and order submission outside market hours
- support half-days and US holidays

Suggested files:

- new `backend/src/tradingbot/services/calendar.py`
- update [tasks.py](/D:/project1/backend/src/tradingbot/worker/tasks.py)
- update [execution.py](/D:/project1/backend/src/tradingbot/services/execution.py)

### 3. Separate paper and live safety modes more aggressively

Current issue:

- the code supports paper/live mode switching, but expert-grade systems need stronger live-mode friction

What to add or modify:

- add a `live_enabled` gate separate from mode
- add environment-level live trading allowlist
- require human approval or multi-step confirmation for live orders
- log every live order decision path

Suggested files:

- [settings.py](/D:/project1/backend/src/tradingbot/schemas/settings.py)
- [models.py](/D:/project1/backend/src/tradingbot/models.py)
- [trading.py](/D:/project1/backend/src/tradingbot/api/routers/trading.py)
- dashboard settings UI in [dashboard-screen.tsx](/D:/project1/web/src/components/dashboard-screen.tsx)

### 4. Harden auth and operator controls

Current issue:

- dashboard token is stored in `localStorage`
- current auth model is single-admin and minimal

What to add or modify:

- move to secure cookies or short-lived access + refresh flow
- add role-based access for operator, reviewer, admin
- add session expiry, audit trail filtering, and forced logout support

## Phase 2: Build Real Research Quality

### 5. Upgrade backtesting from placeholder to research engine

Current issue:

- current backtest task is a structural stub

What to add or modify:

- use historical bars and historical news across a defined period
- simulate fills with slippage and commissions
- simulate delayed fills and rejected orders
- compute equity curve, drawdown, Sharpe, win rate, expectancy, turnover, and exposure
- persist backtest reports

Suggested files:

- expand [backtest.py](/D:/project1/backend/src/tradingbot/services/backtest.py)
- expand [tasks.py](/D:/project1/backend/src/tradingbot/worker/tasks.py)
- add backtest result models to [models.py](/D:/project1/backend/src/tradingbot/models.py)
- add backtest API endpoints and dashboard views

### 6. Add walk-forward testing and regime evaluation

What to add or modify:

- split backtests into train/validation/test windows
- score performance by market regime
- compare behavior during trend, chop, gap-driven, and event-heavy sessions

Why:

- expert systems must survive outside one lucky sample

### 7. Add replay datasets and deterministic fixtures

What to add or modify:

- build fixed replay fixtures for bars, news, and broker responses
- run the same decision path deterministically in tests
- lock down expected outputs for risk and execution rules

Suggested files:

- `backend/tests/fixtures/`
- more test coverage under `backend/tests/`

## Phase 3: Expand Data Depth

### 8. Add richer market features

Current issue:

- current features are intentionally simple

What to add or modify:

- intraday volatility features
- gap statistics
- relative volume
- ATR and stop-distance features
- opening range structure
- trend alignment across multiple timeframes
- market index context such as SPY/QQQ breadth or trend state

Suggested files:

- expand [indicators.py](/D:/project1/backend/src/tradingbot/services/indicators.py)
- add feature engineering service modules

### 9. Add structured event data

What to add or modify:

- earnings dates
- analyst actions
- macro releases
- sector ETF context
- economic calendar and market-moving scheduled events

Why:

- many bad trades are bad because the context is incomplete

### 10. Add data validation and freshness checks

What to add or modify:

- reject stale bars
- reject delayed news snapshots when timeliness matters
- detect missing candles or abnormal feed gaps
- tag every decision with data timestamps

Suggested files:

- [adapters.py](/D:/project1/backend/src/tradingbot/services/adapters.py)
- new validation module in `backend/src/tradingbot/services/`

## Phase 4: Improve Agent Intelligence

### 11. Move from two-agent prompts to a structured committee

Current issue:

- current setup is market agent + news agent + deterministic risk

What to add or modify:

- add specialized agents:
  - technical structure agent
  - catalyst agent
  - market regime agent
  - portfolio exposure agent
  - execution quality agent
- add a final chair/aggregator agent that only summarizes, not overrides hard risk rules

Suggested files:

- expand [agents.py](/D:/project1/backend/src/tradingbot/services/agents.py)
- expand [committee.py](/D:/project1/backend/src/tradingbot/services/committee.py)
- add agent prompt/version registry

### 12. Add prompt and model versioning

What to add or modify:

- store prompt templates by version
- store model name, prompt version, and input snapshot per run
- compare performance by model and prompt version

Why:

- expert systems need explainable changes and measurable iteration

### 13. Add strict output validation and repair flow

What to add or modify:

- validate every agent payload against schema
- auto-retry malformed outputs with a repair prompt
- reject the trade if the payload stays malformed

Suggested files:

- [committee-decision.schema.json](/D:/project1/contracts/committee-decision.schema.json)
- [schemas/trading.py](/D:/project1/backend/src/tradingbot/schemas/trading.py)
- [agents.py](/D:/project1/backend/src/tradingbot/services/agents.py)

### 14. Add post-trade review and feedback loops

What to add or modify:

- score each closed trade versus its original thesis
- classify losses by cause:
  - bad signal
  - bad context
  - bad execution
  - avoidable risk
- build a review queue for recurring failure patterns

## Phase 5: Upgrade Risk Into A Real Portfolio Engine

### 15. Replace symbol-level checks with portfolio-aware risk

Current issue:

- current risk is mostly single-trade and single-symbol based

What to add or modify:

- cap total gross exposure
- cap correlation exposure
- cap sector exposure
- cap event clustering
- scale position size by volatility and conviction

Suggested files:

- [risk.py](/D:/project1/backend/src/tradingbot/services/risk.py)
- [execution.py](/D:/project1/backend/src/tradingbot/services/execution.py)

### 16. Add dynamic position sizing

What to add or modify:

- ATR-based sizing
- volatility-targeted sizing
- equity-curve based throttling
- strategy confidence scaling

### 17. Add drawdown and circuit-breaker logic

What to add or modify:

- stop new entries after intraday drawdown thresholds
- reduce size after loss streaks
- require manual review after repeated execution failures
- auto-enable kill switch after severe anomalies

### 18. Add symbol cooldowns that reflect outcome and context

What to add or modify:

- separate cooldowns for stop-outs vs profit exits
- longer cooldown after high-volatility event failures
- avoid immediate re-entry after news whipsaws

## Phase 6: Improve Execution Quality

### 19. Model real execution, not just decision quality

Current issue:

- current execution path is structurally correct but simplified

What to add or modify:

- estimate slippage before order submission
- avoid thin names or unstable spreads
- reject trades with poor fill quality expectations
- adapt order type and aggressiveness to liquidity

### 20. Add broker reconciliation

What to add or modify:

- poll or sync orders and positions from Alpaca
- reconcile broker truth with local database truth
- flag mismatches as high-priority events

Suggested files:

- [adapters.py](/D:/project1/backend/src/tradingbot/services/adapters.py)
- [execution.py](/D:/project1/backend/src/tradingbot/services/execution.py)
- new reconciliation worker task

### 21. Add order state machine support

What to add or modify:

- represent pending, partially filled, canceled, expired, and replaced states explicitly
- persist state transitions and timestamps
- show lifecycle history in the dashboard

## Phase 7: Improve Observability And Operations

### 22. Add structured logging and metrics

What to add or modify:

- JSON logs
- request IDs
- run IDs propagated through services
- counters for approvals, rejections, malformed outputs, execution failures
- latency metrics for Alpaca and OpenAI calls

### 23. Add alerts

What to add or modify:

- notify on repeated worker failures
- notify on kill-switch activation
- notify on broker reconciliation mismatch
- notify on unusually high rejection rates or malformed agent outputs

### 24. Add dashboard depth for operators

What to add or modify:

- performance charts
- backtest result pages
- per-symbol audit history
- per-agent disagreement analysis
- open risk budget visualization

Suggested files:

- [dashboard-screen.tsx](/D:/project1/web/src/components/dashboard-screen.tsx)
- new route pages under `web/app/`

## Phase 8: Improve Testing And Release Discipline

### 25. Expand tests beyond unit checks

What to add or modify:

- API tests
- worker task tests
- broker adapter contract tests
- model payload validation tests
- end-to-end replay tests

### 26. Add CI and quality gates

What to add or modify:

- lint
- type checks
- unit tests
- replay regression tests
- schema drift checks

### 27. Add release notes for strategy changes

What to add or modify:

- treat strategy logic changes like product releases
- document changes in prompt versions, risk rules, execution behavior, and thresholds

## Suggested New Files And Modules

High-value additions:

- `backend/src/tradingbot/services/calendar.py`
- `backend/src/tradingbot/services/reconciliation.py`
- `backend/src/tradingbot/services/portfolio.py`
- `backend/src/tradingbot/services/features.py`
- `backend/src/tradingbot/services/prompt_registry.py`
- `backend/src/tradingbot/services/evaluation.py`
- `backend/src/tradingbot/services/alerts.py`
- `backend/src/tradingbot/api/routers/backtests.py`
- `backend/src/tradingbot/api/routers/performance.py`
- `backend/src/tradingbot/worker/replay_tasks.py`
- `backend/tests/fixtures/`
- `docs/strategy-change-log.md`

## Suggested Immediate Next 5 Upgrades

If the goal is maximum improvement for the next development cycle, do these first:

1. Add Alembic migrations and remove `create_all` startup schema creation.
2. Implement real backtest persistence and performance metrics.
3. Add market calendar enforcement and stale-data checks.
4. Add broker reconciliation and explicit order lifecycle states.
5. Upgrade the risk engine to portfolio-aware sizing and drawdown circuit breakers.

## Definition Of "Expert" For This Repo

This bot becomes meaningfully closer to expert-grade when it can do all of the following:

- explain why it entered or rejected a trade
- prove the strategy across replay and walk-forward tests
- protect capital with deterministic portfolio-aware risk
- handle bad provider responses safely
- reconcile broker truth with internal truth
- surface failures clearly to the operator
- evolve prompts, models, and thresholds without losing auditability

