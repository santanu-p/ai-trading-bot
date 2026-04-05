# Setup And Local Runbook

## Constraint

This repository was created without installing dependencies locally. The steps below are documentation for the future setup phase, not steps that were executed during implementation.

## Suggested Local Setup

### Backend

1. Create a Python virtual environment.
2. Install the backend package from `backend/`.
3. Copy `.env.example` to `.env`.
4. Set Alpaca and OpenAI credentials.
5. Start Postgres and Redis.
6. Run the FastAPI app.
7. Run the Celery worker with beat enabled.

### Web

1. Install dependencies in `web/`.
2. Set `NEXT_PUBLIC_API_BASE_URL`.
3. Start the Next.js app.

## Suggested Local Commands

These were not run during this task.

### Backend

```bash
cd backend
pip install -e .[dev]
uvicorn tradingbot.api.main:app --reload
```

### Worker

```bash
cd backend
celery -A tradingbot.worker.celery_app.celery_app worker -B --loglevel=INFO
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

## First-Run Checklist

- configure admin credentials
- configure JWT secret
- configure Alpaca paper credentials
- configure OpenAI API key
- open the dashboard
- log in as admin
- populate a small watchlist
- keep mode on `paper`
- verify decisions and risk events before enabling any live path

