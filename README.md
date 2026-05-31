# AI Trading Bot

AI Trading Bot is a Docker-ready, multi-agent intraday trading system for Alpaca paper/live equities. It includes a FastAPI backend, Celery worker/beat scheduler, PostgreSQL, Redis, and a Next.js operator dashboard.

> **Safety default:** the project starts in **paper trading** mode. Live trading is blocked unless you explicitly provide live credentials and enable the live-trading safeguards described below.

## What is included

- **LLM trade committee** using OpenAI or Google Gemini for structured trade decisions.
- **Alpaca integration** for account snapshots, market data, news, order placement, cancellations, fills, and reconciliation.
- **Risk controls** for position limits, daily loss limits, exposure caps, cooldowns, kill switch, and live-mode gates.
- **Agent memory** that persists compact per-symbol decision rollups, post-trade lessons, and risk/execution-quality patterns for future scans.
- **Execution workflow** with execution intents, approval/rejection, order lifecycle tracking, fills, and flatten-all controls.
- **Dashboard** for login, profile setup, bot start/stop, settings, orders, decisions, risk, and backtests.
- **Backtesting and replay** using bundled fixtures/imported market data.

## Prerequisites

Install these before running locally:

| Tool | Version |
| --- | --- |
| Docker + Docker Compose | Docker 24+ recommended |
| Git | 2.40+ recommended |

For non-Docker development you also need Python 3.12+, Node.js 22+, PostgreSQL 16+, and Redis 7+.

## 1. Clone the repository

```bash
git clone https://github.com/santanu-p/ai-trading-bot.git
cd ai-trading-bot
```

## 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
# Required security/login settings
ENVIRONMENT=development
WEB_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
SESSION_SECRET=replace-with-a-random-string-at-least-32-characters
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-password

# Required LLM provider: set at least one provider
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
# or use Gemini instead of OpenAI
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# Required for the default US Alpaca paper-trading profile
ALPACA_PAPER_API_KEY=PK...
ALPACA_PAPER_API_SECRET=...
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_MARKET_DATA_FEED=iex

# Keep live trading disabled until you intentionally configure it
ALLOW_LIVE_TRADING=false
```

Generate a good `SESSION_SECRET` with one of these commands:

```bash
openssl rand -hex 32
# or
python -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Start everything with Docker Compose

```bash
docker compose up --build
```

Docker Compose starts:

| Service | URL/Port | Purpose |
| --- | --- | --- |
| `postgres` | `localhost:5432` | database |
| `redis` | `localhost:6379` | Celery broker/result backend |
| `api` | `http://localhost:8000` | FastAPI backend |
| `worker` | background | Celery worker + beat scheduler |
| `web` | `http://localhost:3000` | operator dashboard |

The backend container runs database migrations automatically before starting the API. The worker container also runs migrations before starting Celery.

## 4. Verify the stack

In a second terminal, run:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed
curl http://localhost:8000/metrics
```

Then open <http://localhost:3000> and log in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.

## 5. Configure the bot before trading

The first database startup creates two market profiles:

- `us-alpaca` — default Alpaca-backed US equities profile.
- `india-paper` — imported-file paper profile for India-market research/backtests.

For the US Alpaca profile:

1. Open **Settings** in the dashboard.
2. Complete the trading-profile intake if prompted.
3. Add a watchlist, for example `AAPL`, `MSFT`, `NVDA`, `SPY`.
4. Confirm risk limits, scan interval, consensus threshold, and mode.
5. Keep mode set to **Paper** for initial operation.
6. Click **Start Bot**.

Once the bot status is running, Celery beat queues market scans at `SCAN_INTERVAL_MINUTES`. The worker collects account/market/news data, retrieves recent symbol memory, asks the LLM committee for decisions, applies risk checks, and creates execution intents/orders according to the profile and risk settings.

### Memory management

The bot uses a lightweight durable memory service rather than LangGraph for the current direct committee workflow. Each symbol/profile can accumulate:

- Decision memory: compact summaries of recent approvals/rejections, confidence, thesis, and risk notes.
- Post-trade learning memory: reusable lessons from completed trade reviews, including recurring loss patterns such as bad execution or avoidable risk.
- Risk memory: recent cooldowns, risk events, repeated rejections, poor fill quality, and high slippage.

These memories are saved in the database and fed back into future scans through the committee context, deterministic pre-trade risk notes, and execution-quality feedback. LangGraph remains a future option if the system grows into a checkpointed graph with retries, reflection, human-review nodes, and explicit memory-write edges.

## Running in paper trading

Paper trading requires these `.env` values:

```env
OPENAI_API_KEY=sk-...          # or GEMINI_API_KEY=...
ALPACA_PAPER_API_KEY=PK...
ALPACA_PAPER_API_SECRET=...
ALLOW_LIVE_TRADING=false
```

Recommended first run:

```bash
docker compose up --build
# log in at http://localhost:3000
# add watchlist -> save settings -> start bot
```

## Enabling live trading intentionally

Live trading is intentionally gated. Do **not** enable it until paper trading and risk settings have been validated.

To make live mode available:

```env
ALLOW_LIVE_TRADING=true
LIVE_TRADING_ALLOWED_BROKERS=alpaca
ALPACA_LIVE_API_KEY=...
ALPACA_LIVE_API_SECRET=...
ALPACA_LIVE_BASE_URL=https://api.alpaca.markets
SESSION_COOKIE_SECURE=true   # required for staging/production HTTPS deployments
ENVIRONMENT=production       # or staging when deployed securely
```

Live mode also requires the dashboard live-enable flow. The API generates a short-lived approval code, and an admin must submit that code before live execution is enabled.

## Useful commands

```bash
# Stop the stack but keep database data
docker compose down

# Stop the stack and delete database volume
docker compose down -v

# View API logs
docker compose logs -f api

# View worker logs
docker compose logs -f worker

# Run migrations manually in the API container
docker compose exec api alembic upgrade head
```

## Local development without Docker

Start only Postgres and Redis:

```bash
docker compose up -d postgres redis
```

Install and run the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, run the worker:

```bash
cd backend
source .venv/bin/activate
celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO
```

Install and run the web app:

```bash
cd web
npm ci
npm run dev
```

## Testing and validation

Backend:

```bash
cd backend
python -m pytest
python -m ruff check src tests
```

Frontend:

```bash
cd web
npm run type-check
npm run build
```

Docker build smoke test:

```bash
docker compose build api worker web
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| API container says `.env` is missing | Run `cp .env.example .env` from the repo root. |
| API/worker fails during `alembic upgrade head` | Rebuild with `docker compose build --no-cache api worker`, then run `docker compose up`. |
| Healthcheck fails with curl errors | Rebuild the backend image; curl is installed in the backend image for the Compose healthcheck. |
| Bot starts but no decisions are generated | Add enabled watchlist symbols, complete the trading-profile intake, and make sure the market session is open. |
| LLM errors | Set a valid `OPENAI_API_KEY` or `GEMINI_API_KEY` and confirm the configured model is available to your account. |
| Alpaca credential errors | Set both key and secret for paper mode: `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_API_SECRET`. |
| Browser cannot call API | Confirm `WEB_ORIGIN=http://localhost:3000`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, and that the API is healthy. |

## Repository layout

```text
backend/              FastAPI, Celery, SQLAlchemy models, Alembic migrations, tests
web/                  Next.js dashboard
contracts/            JSON schema contracts
docs/                 Architecture, operations, deployment, and runbooks
docker-compose.yml    Full local stack
.env.example          Environment variable template
```

## Security notes

- Start with Alpaca paper trading.
- Do not commit `.env` or API keys.
- Use a strong `SESSION_SECRET` and strong admin password.
- Use HTTPS and secure cookies for staging/production.
- Keep `ALLOW_LIVE_TRADING=false` unless you are deliberately enabling live execution.
- Review dashboard risk settings and kill-switch behavior before any live deployment.
