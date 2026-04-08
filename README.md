# AI Trading Bot

A greenfield multi-agent intraday trading bot scaffold for Alpaca equities with:

- `backend/`: FastAPI API, SQLAlchemy models, Celery worker entrypoints, risk/execution services, and Alpaca/OpenAI/Gemini integrations
- `web/`: Next.js operator dashboard for bot control, decisions, orders, positions, risk, and settings
- `contracts/`: shared JSON schema for committee decisions
- `docs/`: architecture, API, setup, and deployment documentation

No dependencies were installed and no services were started while creating this repository.

## What This Repo Implements

- Alpaca-based paper/live equities trading workflow with explicit live enablement
- 5-minute scan worker design for intraday decision cycles
- first-step agent intake for selecting trading pattern, instrument class, strategy family, risk profile, and market universe
- Alembic-based schema migrations under `backend/alembic/`
- exchange-session and trading-calendar gating with half-day and end-of-session flatten rules
- queued execution intents with a dedicated execution worker boundary
- secure HTTP-only operator sessions with role-based access for `reviewer`, `operator`, and `admin`
- persisted Phase 3 research backtests with:
  - slippage + commission modeling
  - delayed fill and rejected-order simulation
  - walk-forward train/validation/test scoring
  - regime breakdown (trend/chop/gap-driven/event-heavy)
  - per-report equity-curve and per-trade simulation history
- Phase 4 data-depth upgrades with:
  - richer feature engineering (volatility/gap/ATR/relative-volume/opening-range/multi-timeframe alignment)
  - SPY/QQQ index context merged into symbol features
  - structured event extraction (earnings/analyst/macro/sector/calendar context)
  - scan-time data-quality gating (stale bars, delayed news, missing candles, feed-gap detection)
  - decision payload timestamp/quality/feature/event audit tags
- Phase 5 agent-intelligence upgrades with:
  - structured specialist committee (technical/catalyst/regime/portfolio/execution-quality plus chair)
  - prompt registry with persisted per-run model and prompt-version lineage
  - schema-repair retries for malformed agent outputs
  - post-trade review queue and grouped review summaries by model/prompt signature
- Phase 6 portfolio-risk upgrades with:
  - portfolio-aware exposure controls (gross/sector/correlation/event clustering)
  - dynamic sizing (ATR/volatility/confidence/equity-curve/loss-streak scaling)
  - drawdown and anomaly circuit breakers with automatic kill-switch activation
  - persisted contextual symbol cooldowns (`profit_exit`, `stop_out`, `news_whipsaw`, `event_failure`)
- Multi-agent committee shape:
  - structured specialist committee
  - deterministic risk engine
  - execution intent handoff
  - execution service
- Operator dashboard for:
  - bot start/stop
  - mode switching
  - kill switch
  - live enable/disable workflow
  - execution-intent review
  - session visibility and forced logout
  - audit-log visibility
  - settings and watchlist updates
  - decision/order/risk visibility
  - backtest launch and report review
- Shared decision contract in [committee-decision.schema.json](contracts/committee-decision.schema.json)

## What This Repo Does Not Yet Do

- Install or pin local Python/Node environments on your machine
- Start API, worker, Postgres, Redis, or the web app
- Prove live trading behavior end-to-end against Alpaca
- Add full production secret management, rate limiting, CSRF protection, or cloud provisioning code

## Repo Layout

```text
.
|- backend/
|  |- src/tradingbot/
|  |  |- api/
|  |  |- schemas/
|  |  |- services/
|  |  `- worker/
|  `- tests/
|- contracts/
|- docs/
`- web/
```

## Runtime Model

- API: `uvicorn tradingbot.api.main:app`
- Worker: `celery -A tradingbot.worker.celery_app.celery_app worker -B`
- Web: `next dev` or `next start`
- Local orchestration target: `docker-compose.yml`
- GitHub Codespaces target: `.devcontainer/`

## Core Flow

1. The operator authenticates in the dashboard.
2. The backend issues a secure cookie-backed session and enforces operator roles on every control-plane route.
3. Alembic migrations manage schema changes before the API and worker start.
4. The worker wakes up on schedule, checks bot state, and enforces market-session rules.
5. For each enabled watchlist symbol, the worker fetches Alpaca bars and Alpaca news.
6. The worker computes engineered features, merges index context, extracts structured events, and validates data freshness/feed integrity.
7. A specialist committee produces structured decisions, the chair summarizes them, and malformed outputs get one repair pass before rejection.
8. The risk engine deterministically approves or rejects the committee proposal with portfolio-aware limits and dynamic sizing.
9. Approved decisions are persisted as execution intents instead of being submitted inline.
10. Operators review live intents when required, and the execution worker re-checks market hours, kill switch, broker connectivity, and live gates before broker submission.
11. Filled exits generate post-trade reviews tied back to model/prompt lineage and update outcome-aware symbol cooldown state.
12. The dashboard and API poll/read settings, intents, runs, orders, sessions, audit logs, risk state, and review queues.

## Documentation

- [System overview](./docs/overview.md)
- [Architecture](./docs/architecture.md)
- [Backend API](./docs/api.md)
- [Dashboard](./docs/dashboard.md)
- [Configuration](./docs/configuration.md)
- [Setup and local runbook](./docs/setup.md)
- [Deployment notes](./docs/deployment.md)
- [Operations runbook](./docs/operations.md)
- [Expert upgrade roadmap](./docs/expert-upgrade-roadmap.md)
- [Production hardening plan](./docs/production-hardening-plan.md)

## Verification Performed

- `pytest backend/tests -q` completed successfully in the current environment with `PYTHONPATH=backend/src`
- No dependency installation was performed
- No services were started
- Frontend type-check/build validation was not executed because local Node dependencies were intentionally not installed

## Notes

- Some transient Python cache artifacts may exist from parse attempts that were blocked by the Windows sandbox; they are ignored by `.gitignore`.
- The current repository now includes Phase 0-6 roadmap work, but it is still not a production-hardened trading system.
