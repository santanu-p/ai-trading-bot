# Setup And Local Runbook

## Notes

- Backend requires Python 3.12 or newer.
- Web validation in CI uses Node 22.
- Use `.env.example` as the starting point, then adjust values for your environment.
- For Docker Compose or Codespaces/devcontainers, use service-host URLs inside `.env`:
  - `DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/tradingbot`
  - `REDIS_URL=redis://redis:6379/0`

## Suggested Local Setup

### Backend

1. Create a Python virtual environment.
2. Install the backend package from `backend/`.
3. Copy `.env.example` to `.env`.
4. Set session/admin credentials, provider keys, and `NEXT_PUBLIC_API_BASE_URL` when the web app is not served from the same local origin as the API.
5. Start Postgres and Redis.
6. Run the FastAPI app.
7. Run the Celery worker with beat enabled.

### Web

1. Install dependencies in `web/`.
2. Set `NEXT_PUBLIC_API_BASE_URL`.
3. Start the Next.js app.

## Suggested Local Commands

### Backend

```bash
cd backend
pip install -e .[dev]
alembic upgrade head
uvicorn tradingbot.api.main:app --reload
```

### Phase 9 Quality Gates (Local)

```bash
cd backend
ruff check src tests scripts
mypy src
pytest -q -m "not replay"
pytest -q -m replay
python scripts/check_schema_drift.py
```

```bash
cd web
npm install
npm run type-check
```

### Worker

```bash
cd backend
celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO
```

### Web

```bash
cd web
npm install
npm run dev
```

### Docker Compose

```bash
docker compose up --build
```

The checked-in Compose file runs `alembic upgrade head` before starting the API and worker services, and it overrides `DATABASE_URL`/`REDIS_URL` to use the Compose service names.

### GitHub Codespaces

The repo now includes a `.devcontainer/` setup for Codespaces.

After opening the repo in a Codespace:

1. Wait for `postCreateCommand` to finish installing backend and web dependencies.
2. Update `.env` with at least:
   - `DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/tradingbot`
   - `REDIS_URL=redis://redis:6379/0`
   - `SESSION_SECRET`
   - `ADMIN_PASSWORD`
   - `OPENAI_API_KEY` or `GEMINI_API_KEY`
   - `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_API_SECRET` or the legacy fallback pair `ALPACA_API_KEY` and `ALPACA_API_SECRET`
   - `ALPACA_LIVE_API_KEY` and `ALPACA_LIVE_API_SECRET` if `ALLOW_LIVE_TRADING=true`
   - `NEXT_PUBLIC_API_BASE_URL`
   - `ALLOW_LIVE_TRADING`
3. Start the API:

```bash
cd backend
uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000
```

4. Start the worker:

```bash
cd backend
celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO
```

5. Start the web app:

```bash
cd web
npm run dev -- --hostname 0.0.0.0 --port 3000
```

The Codespace devcontainer already starts Postgres and Redis as sidecar services.

## First-Run Checklist

- configure admin credentials
- configure session secret
- configure Alpaca paper credentials
- configure an OpenAI or Gemini API key
- run `alembic upgrade head`
- open the dashboard
- log in as admin
- populate a small watchlist
- keep mode on `paper`
- verify decisions and risk events before enabling any live path
