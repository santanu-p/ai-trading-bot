# AI Trading Bot

A greenfield multi-agent intraday trading bot scaffold for Alpaca equities with:

- `backend/`: FastAPI API, SQLAlchemy models, Celery worker entrypoints, risk/execution services, and Alpaca/OpenAI/Gemini integrations
- `web/`: Next.js operator dashboard for bot control, decisions, orders, positions, risk, and settings
- `contracts/`: shared JSON schema for committee decisions
- `docs/`: architecture, API, setup, and deployment documentation

No dependencies were installed and no services were started while creating this repository.

## What This Repo Implements

- Alpaca-based paper/live-ready equities trading workflow
- 5-minute scan worker design for intraday decision cycles
- first-step agent intake for selecting trading pattern, instrument class, strategy family, risk profile, and market universe
- Multi-agent committee shape:
  - market agent
  - news agent
  - deterministic risk engine
  - execution service
- Operator dashboard for:
  - bot start/stop
  - mode switching
  - kill switch
  - settings and watchlist updates
  - decision/order/risk visibility
- Shared decision contract in [committee-decision.schema.json](contracts/committee-decision.schema.json)

## What This Repo Does Not Yet Do

- Install or pin local Python/Node environments on your machine
- Run migrations through Alembic
- Start API, worker, Postgres, Redis, or the web app
- Prove live trading behavior end-to-end against Alpaca
- Add production auth, secrets management, or cloud provisioning code

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
2. The backend stores bot settings and watchlist symbols in Postgres.
3. The worker wakes up on schedule and checks bot state.
4. For each enabled watchlist symbol, the worker fetches Alpaca bars and Alpaca news.
5. The market and news agents produce structured decisions.
6. The committee proposes a trade.
7. The risk engine deterministically approves or rejects it.
8. Approved decisions are sent to the broker adapter and persisted as orders/positions.
9. The dashboard polls the backend for the latest state.

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

- Static Python parse completed for all files in `backend/src` and `backend/tests`
- No dependency installation was performed
- No services were started
- No browser build or test run was executed

## Notes

- Some transient Python cache artifacts may exist from parse attempts that were blocked by the Windows sandbox; they are ignored by `.gitignore`.
- The current repository is a structured scaffold, not a production-hardened trading system.
