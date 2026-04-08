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
- Multi-agent committee shape:
  - market agent
  - news agent
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
6. The market and news agents produce structured decisions and the committee proposes a trade.
7. The risk engine deterministically approves or rejects it.
8. Approved decisions are persisted as execution intents instead of being submitted inline.
9. Operators review live intents when required, and the execution worker re-checks market hours, kill switch, broker connectivity, and live gates before broker submission.
10. The dashboard polls the backend for settings, intents, runs, orders, sessions, audit logs, and risk state.

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
- The current repository now includes the Phase 1 foundation work, but it is still not a production-hardened trading system.
