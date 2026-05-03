# Setup & Local Runbook

This guide covers every setup path in detail: local development, Docker Compose, and GitHub Codespaces.

---

## System Requirements

| Component | Minimum Version | Check Command |
|-----------|----------------|---------------|
| Python | 3.12+ | `python --version` |
| Node.js | 22+ | `node --version` |
| PostgreSQL | 16+ | `psql --version` |
| Redis | 7+ | `redis-server --version` |
| Docker *(optional)* | 24+ | `docker --version` |
| Docker Compose *(optional)* | 2.20+ | `docker compose version` |

---

## 1. Get External API Keys

Before any setup path, you need API keys from these services:

### Alpaca (Required — Broker)

1. Go to [https://alpaca.markets](https://alpaca.markets) and create a free account
2. Navigate to **Paper Trading** → **API Keys**
3. Generate an API key pair — you'll get:
   - `ALPACA_PAPER_API_KEY` (starts with `PK`)
   - `ALPACA_PAPER_API_SECRET`
4. **For live trading** (later): Generate separate live keys under the Live Trading section

### LLM Provider (Required — At Least One)

**Option A: OpenAI**
1. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a new API key → `OPENAI_API_KEY` (starts with `sk-`)
3. Default model: `gpt-5-mini` (configurable via `OPENAI_MODEL`)

**Option B: Google Gemini**
1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Create an API key → `GEMINI_API_KEY` (starts with `AIza`)
3. Default model: `gemini-2.5-flash` (configurable via `GEMINI_MODEL`)

---

## 2. Environment File Setup

```bash
# From the project root
cp .env.example .env
```

Open `.env` in your editor and fill in the required values:

```env
# ─── REQUIRED ─────────────────────────────────────────────

# Infrastructure (defaults work for local / Docker Compose)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tradingbot
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
WEB_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Security — Generate a strong random string (≥ 32 chars)
# Linux/Mac: openssl rand -hex 32
# PowerShell: [System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()
SESSION_SECRET=<your-random-secret-here>

# Admin credentials
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=<strong-password>

# LLM provider (at least one)
OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AIza...

# Broker credentials (paper trading)
ALPACA_PAPER_API_KEY=PK...
ALPACA_PAPER_API_SECRET=...

# ─── OPTIONAL ─────────────────────────────────────────────

# Additional operator accounts
# OPERATOR_EMAIL=operator@yourdomain.com
# OPERATOR_PASSWORD=<password>
# REVIEWER_EMAIL=reviewer@yourdomain.com
# REVIEWER_PASSWORD=<password>

# Trading tuning
SCAN_INTERVAL_MINUTES=5
CONSENSUS_THRESHOLD=0.64
ALLOW_LIVE_TRADING=false

# Alert destinations
# ALERT_WEBHOOK_URLS=https://hooks.slack.com/services/...,https://...
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
# PAGERDUTY_WEBHOOK_URL=https://events.pagerduty.com/v2/enqueue
```

> **⚠️ Docker Compose note**: When using `docker compose`, the `DATABASE_URL` and `REDIS_URL` are automatically overridden to use Docker service names (`postgres`, `redis`). Your `.env` values for these are only used for local development.

---

## 3A. Docker Compose Setup (Recommended)

This is the easiest path — one command starts everything.

```bash
# Build and start all services
docker compose up --build

# Or run in the background
docker compose up --build -d
```

**What starts:**

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | PostgreSQL 16 with healthcheck |
| `redis` | 6379 | Redis 7 with healthcheck |
| `api` | 8000 | FastAPI backend (runs migrations automatically) |
| `worker` | — | Celery worker with beat scheduler |
| `web` | 3000 | Next.js dashboard |

**Verify the stack:**

```bash
# Check all services are healthy
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check detailed component health
curl http://localhost:8000/health/detailed

# View logs
docker compose logs -f api
docker compose logs -f worker
```

**Stop everything:**

```bash
docker compose down

# Stop and remove volumes (⚠️ deletes database data)
docker compose down -v
```

---

## 3B. Local Development Setup

### Step 1: Start Database & Cache

**Option A: Docker (recommended for databases only)**

```bash
docker compose up postgres redis -d
```

**Option B: Native PostgreSQL + Redis**

```bash
# PostgreSQL — create the database
createdb tradingbot

# Redis — start the server
redis-server
```

### Step 2: Backend Installation

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate it
# Linux/Mac:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat

# Install the package with dev dependencies
pip install -e ".[dev]"
```

### Step 3: Database Migrations

```bash
cd backend

# Set PYTHONPATH
# Linux/Mac:
export PYTHONPATH=src
# Windows PowerShell:
$env:PYTHONPATH = "src"

# Run all migrations
alembic upgrade head
```

### Step 4: Start the API Server

```bash
cd backend
uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000
```

Verify: `curl http://localhost:8000/health`

### Step 5: Start the Celery Worker

**Open a new terminal** (keep the API running):

```bash
cd backend
# Activate venv and set PYTHONPATH (same as Steps 2-3)
celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO
```

### Step 6: Start the Dashboard

**Open another terminal:**

```bash
cd web
npm install
npm run dev
```

Verify: Open `http://localhost:3000` in your browser.

---

## 3C. GitHub Codespaces Setup

1. Open the repository in a GitHub Codespace
2. Wait for `postCreateCommand` to finish (installs backend + web dependencies)
3. Create `.env` in the project root with your credentials
4. Start services in three terminals:

```bash
# Terminal 1: API
cd backend && uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Worker
cd backend && celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO

# Terminal 3: Dashboard
cd web && npm run dev -- --hostname 0.0.0.0 --port 3000
```

PostgreSQL and Redis are automatically started as Codespace sidecar services. The forwarded ports (3000, 5432, 6379, 8000) are configured in `.devcontainer/devcontainer.json`.

---

## 4. First-Run Walkthrough

Once all services are running:

### 4.1 Login

1. Open **http://localhost:3000** in your browser
2. Login with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from your `.env`
3. You'll see the operator dashboard with bot controls

### 4.2 Configure Settings

1. Navigate to **Settings**
2. Verify the trading mode is set to **Paper**
3. Confirm the scan interval (default: 5 minutes)
4. Set the consensus threshold (default: 0.64)

### 4.3 Populate the Watchlist

1. Navigate to the **Watchlist** section
2. Add 3-5 US equity symbols to start with:
   - `AAPL` — Apple
   - `MSFT` — Microsoft
   - `GOOGL` — Alphabet
   - `TSLA` — Tesla
   - `NVDA` — NVIDIA

### 4.4 Start the Bot

1. Click **Start Bot** from the dashboard controls
2. The Celery worker will begin scanning on the next 5-minute interval during market hours (9:30 AM – 4:00 PM ET)
3. Outside market hours, scans will be skipped automatically

### 4.5 Monitor Activity

| Panel | What to Watch |
|-------|---------------|
| **Decisions** | Committee outputs with specialist agent votes and confidence scores |
| **Execution Intents** | Pending, approved, and executed trade intents |
| **Orders** | Live order status from Alpaca (new → filled/canceled) |
| **Positions** | Current open positions with P&L |
| **Risk Events** | Risk engine activity (rejections, circuit breakers, cooldowns) |
| **Audit Log** | Full operational audit trail |

### 4.6 Verify Prometheus Metrics

```bash
curl http://localhost:8000/metrics
```

You should see metrics like:
```
# HELP tradingbot_worker_scan_invocations Counter worker.scan.invocations
# TYPE tradingbot_worker_scan_invocations counter
tradingbot_worker_scan_invocations 3
```

---

## 5. Running Tests

```bash
cd backend

# Set PYTHONPATH
# Linux/Mac:
export PYTHONPATH=src
# Windows PowerShell:
$env:PYTHONPATH = "src"

# Full test suite
python -m pytest tests/ -q

# Skip replay regression tests (faster)
python -m pytest tests/ -q -m "not replay"

# Run only replay regression tests
python -m pytest tests/ -q -m replay

# Verbose output with short tracebacks
python -m pytest tests/ -v --tb=short
```

### Quality Gates

Run these before any PR or release:

```bash
cd backend

# Lint
ruff check src tests scripts

# Type check
mypy src

# Unit tests
python -m pytest tests/ -q -m "not replay"

# Replay regression
python -m pytest tests/ -q -m replay

# Schema drift check
python scripts/check_schema_drift.py
```

```bash
cd web

# TypeScript type check
npm run type-check
```

---

## 6. Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: tradingbot` | Set `PYTHONPATH=src` (or `$env:PYTHONPATH = "src"` on Windows) |
| `Connection refused` on PostgreSQL | Ensure Postgres is running on port 5432; check `DATABASE_URL` |
| `Connection refused` on Redis | Ensure Redis is running on port 6379; check `REDIS_URL` |
| `SESSION_SECRET must be set` | You're in `staging`/`production` mode — set a strong secret ≥ 32 chars |
| `ALPACA_PAPER_API_KEY and _SECRET must be set together` | Set both the key and secret for paper trading |
| Alembic migration fails | Ensure the `tradingbot` database exists: `createdb tradingbot` |
| Worker not scanning | Bot must be started from the dashboard; scans only run during market hours |
| No decisions appearing | Check worker logs; ensure LLM API key is valid and has credit |
| Docker Compose build fails | Run `docker compose build --no-cache` to force a clean rebuild |

### Checking Logs

```bash
# Docker Compose logs
docker compose logs -f api
docker compose logs -f worker

# Local: API logs appear in the terminal running uvicorn
# Local: Worker logs appear in the terminal running celery
```

### Resetting the Database

```bash
# Docker Compose
docker compose down -v
docker compose up --build

# Local
cd backend
alembic downgrade base
alembic upgrade head
```

---

## 7. Production Deployment Notes

For production deployment, ensure:

1. **Security hardened `.env`**:
   ```env
   ENVIRONMENT=production
   SESSION_SECRET=<64-char-random-string>
   SESSION_COOKIE_SECURE=true
   CSRF_ORIGIN_ENFORCEMENT=true
   ```

2. **Separate paper and live credentials** — the system blocks startup if they match

3. **Database backups** — configure PostgreSQL point-in-time recovery

4. **Monitoring** — scrape `/metrics` with Prometheus and set up Grafana dashboards

5. **Alert routing** — configure at least one webhook for critical alerts

6. **Rate limiting** — defaults are safe but can be tuned for your traffic

See [docs/deployment.md](./docs/deployment.md) and [docs/operations.md](./docs/operations.md) for full production guidance.
