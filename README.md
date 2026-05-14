# 🤖 AI Trading Bot

A production-grade, multi-agent intraday trading system for US equities via [Alpaca](https://alpaca.markets). Combines a specialist LLM committee (OpenAI / Gemini), deterministic risk engine, and execution-quality feedback loops into a fully automated decision → execution → review pipeline.

---

## ✨ Key Features

| Area | Capabilities |
|------|-------------|
| **Multi-Agent AI Committee** | 7 specialist agents (technical, catalyst, regime, portfolio, execution-quality, risk, chair) produce structured trade decisions with confidence scoring |
| **Deterministic Risk Engine** | Portfolio-aware exposure limits, dynamic ATR/volatility sizing, correlation-aware clustering, drawdown circuit breakers, and kill-switch activation |
| **Execution Quality** | Pre-submit liquidity gating, adaptive order aggressiveness, VWAP tracking, fill-quality TCA analytics, and execution feedback loops |
| **Operator Dashboard** | Next.js control plane with bot start/stop, mode switching, kill switch, intent review, session management, audit logs, and risk panels |
| **Multi-Profile Support** | Seeded `us-alpaca` and `india-paper` profiles with exchange-aware session handling (NYSE/NASDAQ, NSE/BSE) |
| **Backtesting** | Walk-forward backtests with slippage/commission modeling, regime breakdown, Monte Carlo simulation, VaR/CVaR estimation, and stress testing |
| **Observability** | Structured JSON logging, Prometheus-compatible `/metrics` endpoint, distributed tracing, multi-channel alerts (webhook/Slack/PagerDuty) |
| **Compliance** | PDT detection, wash-sale monitoring, position limit checks, daily trade reports, and LLM cost tracking |
| **ML Signals** | Classical gradient-boost signal models with LLM committee score blending (30/70 ML/LLM default weights) |

---

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Operator Dashboard (Next.js)            │
│  Bot Control · Intent Review · Risk Panels · Audit Logs     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP + SSE
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI Backend (Uvicorn)                │
│  Auth · Trading · Settings · Performance · Health · Metrics │
└──────────────┬────────────────────────────┬─────────────────┘
               │                            │
    ┌──────────▼──────────┐     ┌───────────▼──────────┐
    │   Celery Worker     │     │  Stream Supervisor    │
    │  Scans · Execution  │     │  WebSocket / Polling  │
    │  Reviews · Flatten  │     │  Order State Machine  │
    └──────────┬──────────┘     └───────────┬──────────┘
               │                            │
    ┌──────────▼────────────────────────────▼──────────┐
    │              Service Layer                        │
    │  LLM Committee · Risk Engine · Execution Service │
    │  Features/Indicators · Compliance · ML Signals   │
    │  FX · Monte Carlo · Cost Tracking · Alerts       │
    └──────────┬────────────────────────────┬──────────┘
               │                            │
    ┌──────────▼──────────┐     ┌───────────▼──────────┐
    │  PostgreSQL 16      │     │  Redis 7             │
    │  (SQLAlchemy + ORM) │     │  (Celery Broker)     │
    └─────────────────────┘     └──────────────────────┘
               │
    ┌──────────▼──────────┐
    │  Alpaca Broker API  │
    │  Paper / Live       │
    └─────────────────────┘
```

---

## 📁 Repository Layout

```
.
├── backend/                    # Python backend (FastAPI + Celery)
│   ├── src/tradingbot/
│   │   ├── api/                # FastAPI routers (auth, trading, health, metrics, etc.)
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Core business logic (35 modules)
│   │   │   ├── adapters.py     # Broker adapter protocol + Alpaca implementation
│   │   │   ├── agents.py       # LLM specialist agents
│   │   │   ├── committee.py    # Multi-agent committee orchestration
│   │   │   ├── risk.py         # Deterministic risk engine
│   │   │   ├── execution.py    # Order lifecycle + VWAP tracking
│   │   │   ├── compliance.py   # PDT / wash-sale / position limits
│   │   │   ├── ml_signals.py   # ML signal pipeline + gradient boost
│   │   │   ├── monte_carlo.py  # Monte Carlo simulation + stress tests
│   │   │   ├── otel.py         # Distributed tracing (trace_id/span_id)
│   │   │   ├── metrics.py      # Counters + durations + Prometheus export
│   │   │   ├── alert_dispatch.py # Multi-channel alert routing
│   │   │   ├── stream_supervisor.py  # WebSocket broker streaming
│   │   │   ├── fx.py           # FX conversion service
│   │   │   ├── cost_tracking.py # LLM cost tracking + scan scheduling
│   │   │   └── ...             # 20+ more service modules
│   │   ├── worker/             # Celery tasks (scans, execution, streaming)
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── enums.py            # Trading enums (status, roles, brokers, currency)
│   │   ├── config.py           # Centralized env-based settings
│   │   └── utils.py            # Shared utility functions
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest test suite (55+ tests)
│   ├── scripts/                # Schema drift, deployment scripts
│   ├── pyproject.toml          # Python dependencies
│   └── Dockerfile
├── web/                        # Next.js 15 operator dashboard
│   ├── app/                    # App router pages
│   ├── src/                    # React components + hooks
│   ├── package.json
│   └── Dockerfile
├── contracts/                  # Shared JSON schemas
│   └── committee-decision.schema.json
├── docs/                       # Architecture, API, ops, and roadmap docs
├── .devcontainer/              # GitHub Codespaces configuration
├── .github/                    # CI workflows + PR template
├── docker-compose.yml          # Full-stack orchestration
├── .env.example                # Environment variable template
└── README.md
```

---

## 🔧 Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Python** | ≥ 3.12 | Backend runtime |
| **Node.js** | ≥ 22 | Frontend (Next.js 15) |
| **PostgreSQL** | ≥ 16 | Primary data store |
| **Redis** | ≥ 7 | Celery broker + cache |
| **Docker** *(optional)* | ≥ 24 | For `docker compose` deployment |
| **Git** | ≥ 2.40 | Version control |

### External Service Accounts

| Service | Required? | Purpose |
|---------|-----------|---------|
| [Alpaca](https://alpaca.markets) | **Yes** | Broker API for paper/live trading |
| [OpenAI](https://platform.openai.com) **or** [Google Gemini](https://ai.google.dev) | **Yes** (one) | LLM provider for the AI committee |
| Slack / PagerDuty / Opsgenie | Optional | Alert routing destinations |

---

## 🚀 Quick Start

### Option A: Docker Compose (Recommended)

The fastest way to get everything running with a single command.

```bash
# 1. Clone the repository
git clone https://github.com/santanu-p/ai-trading-bot.git
cd ai-trading-bot

# 2. Create your environment file
cp .env.example .env
```

Edit `.env` with your actual credentials (see [Environment Variables](#-environment-variables) below):

```env
# Required: Generate a strong secret (≥ 32 chars)
SESSION_SECRET=your-random-secret-string-at-least-32-characters

# Required: Admin login
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=your-strong-admin-password

# Required: At least one LLM provider
OPENAI_API_KEY=sk-...            # Option 1: OpenAI
GEMINI_API_KEY=AIza...           # Option 2: Google Gemini

# Required: Alpaca paper trading credentials
ALPACA_PAPER_API_KEY=PK...
ALPACA_PAPER_API_SECRET=...
```

```bash
# 3. Launch the full stack
docker compose up --build

# The following services will start:
#   PostgreSQL  →  localhost:5432
#   Redis       →  localhost:6379
#   Backend API →  localhost:8000
#   Celery Worker (background, with beat scheduler)
#   Dashboard   →  localhost:3000
```

```bash
# 4. Verify the stack is healthy
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed
curl http://localhost:8000/metrics
```

Open **http://localhost:3000** in your browser and log in with your admin credentials.

---

### Option B: Local Development Setup

For development with hot-reload and direct debugging access.

#### Step 1 — Start Infrastructure Services

You need PostgreSQL and Redis running. Use Docker for just the databases:

```bash
# Start only Postgres + Redis
docker compose up postgres redis -d
```

Or install them natively:
- **PostgreSQL**: Create a database called `tradingbot`
- **Redis**: Default port 6379

#### Step 2 — Backend Setup

```bash
# Navigate to the backend directory
cd backend

# Create a Python virtual environment
python -m venv .venv

# Activate it
# Linux/Mac:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat

# Install the package with dev dependencies
pip install -e ".[dev]"

# Copy environment file
cd ..
cp .env.example .env
# Edit .env with your credentials (see Environment Variables section below)
```

#### Step 3 — Database Migrations

```bash
cd backend

# Set the Python path
# Linux/Mac:
export PYTHONPATH=src
# Windows (PowerShell):
$env:PYTHONPATH = "src"

# Run migrations
alembic upgrade head
```

#### Step 4 — Start the Backend API

```bash
cd backend
uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at **http://localhost:8000**. Useful endpoints:
- `GET /health` — basic health check
- `GET /health/detailed` — component-level status (DB, Redis, LLM, broker)
- `GET /metrics` — Prometheus-compatible metrics

#### Step 5 — Start the Celery Worker

Open a **separate terminal** (keep the API running):

```bash
cd backend

# Activate virtual environment (same as Step 2)
# Set PYTHONPATH (same as Step 3)

# Start the worker with the beat scheduler
celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO
```

The worker handles:
- Scheduled market scans (every 5 minutes by default)
- Execution intent processing
- Position flattening at market close
- Post-trade reviews
- Stream supervisor health checks

#### Step 6 — Start the Dashboard

Open a **third terminal**:

```bash
cd web

# Install dependencies from the lockfile
npm ci

# Set the API URL
# Linux/Mac:
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
# Windows (PowerShell):
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000"

# Start the dev server
npm run dev
```

Open **http://localhost:3000** and log in.

---

### Option C: GitHub Codespaces

1. Open the repo in a Codespace
2. Wait for `postCreateCommand` to finish
3. Create `.env` with your credentials
4. Start the services:

```bash
# Terminal 1: API
cd backend && uvicorn tradingbot.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Worker
cd backend && celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO

# Terminal 3: Dashboard
cd web && npm run dev -- --hostname 0.0.0.0 --port 3000
```

Postgres and Redis are automatically started as Codespace sidecar services.

---

## 🔐 Environment Variables

Copy `.env.example` → `.env` and configure the following groups:

### Core Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/tradingbot` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `ENVIRONMENT` | `development` | One of: `development`, `test`, `staging`, `production` |
| `WEB_ORIGIN` | `http://localhost:3000` | Frontend origin for CORS |

### Authentication & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_SECRET` | `change-me` | **Must be ≥ 32 chars in staging/production** |
| `SESSION_EXPIRE_MINUTES` | `720` | Session lifetime (12 hours) |
| `ADMIN_EMAIL` | `admin@example.com` | Admin login email |
| `ADMIN_PASSWORD` | `change-me` | Admin login password |
| `OPERATOR_EMAIL` | *(empty)* | Optional operator account |
| `REVIEWER_EMAIL` | *(empty)* | Optional reviewer account |
| `SESSION_COOKIE_SECURE` | `false` (dev) | Set `true` in production (HTTPS only) |
| `CSRF_ORIGIN_ENFORCEMENT` | `true` | CSRF origin check — keep enabled |

### LLM Provider (at least one required)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI model name |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |

### Alpaca Broker

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPACA_PAPER_API_KEY` | *(empty)* | Paper trading API key |
| `ALPACA_PAPER_API_SECRET` | *(empty)* | Paper trading API secret |
| `ALPACA_LIVE_API_KEY` | *(empty)* | Live trading API key (only if `ALLOW_LIVE_TRADING=true`) |
| `ALPACA_LIVE_API_SECRET` | *(empty)* | Live trading API secret |
| `ALPACA_PAPER_BASE_URL` | `https://paper-api.alpaca.markets` | Paper API endpoint |
| `ALPACA_LIVE_BASE_URL` | `https://api.alpaca.markets` | Live API endpoint |
| `ALPACA_DATA_BASE_URL` | `https://data.alpaca.markets` | Market data endpoint |
| `ALPACA_MARKET_DATA_FEED` | `iex` | Data feed (`iex` free tier, `sip` paid) |

### Trading Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SCAN_INTERVAL_MINUTES` | `5` | How often the worker scans the watchlist |
| `CONSENSUS_THRESHOLD` | `0.64` | Minimum committee confidence for execution |
| `MIN_APPROVAL_VOTES` | `2` | Minimum specialist votes required |
| `ALLOW_LIVE_TRADING` | `false` | Master switch for real money trading |
| `INTRADAY_FLATTEN_BUFFER_MINUTES` | `15` | Minutes before close to flatten positions |
| `STREAM_POLL_INTERVAL_SECONDS` | `5` | Broker stream polling frequency |

### Rate Limiting & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_BODY_MAX_BYTES` | `1000000` | Max request body size (1MB) |
| `API_RATE_LIMIT_PER_MINUTE` | `240` | General API rate limit |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `20` | Auth endpoint rate limit |

### Alerts (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERT_WEBHOOK_URLS` | *(empty)* | Comma-separated webhook URLs |
| `ALERT_WEBHOOK_TIMEOUT_SECONDS` | `5` | Webhook delivery timeout |

---

## 📊 First-Run Checklist

After starting all services for the first time:

1. ✅ Open **http://localhost:3000** and log in with your admin credentials
2. ✅ Verify the health dashboard shows all components green at `/health/detailed`
3. ✅ Navigate to **Settings** and confirm the trading mode is set to **Paper**
4. ✅ Add 3-5 symbols to the watchlist (e.g., `AAPL`, `MSFT`, `GOOGL`, `TSLA`, `NVDA`)
5. ✅ Start the bot from the dashboard — the worker will begin scanning on the next market-hours interval
6. ✅ Monitor the **Decisions** panel for committee outputs
7. ✅ Check the **Risk Events** panel for risk engine activity
8. ✅ Review execution intents before enabling auto-execution

> ⚠️ **Important**: Keep the bot in **Paper** mode until you have verified decisions, fills, and risk behavior over multiple trading sessions. Never enable `ALLOW_LIVE_TRADING=true` without thorough paper trading validation.

---

## 🧪 Running Tests

```bash
cd backend

# Set Python path
# Linux/Mac:
export PYTHONPATH=src
# Windows:
$env:PYTHONPATH = "src"

# Run the full test suite
python -m pytest tests/ -q

# Run only unit tests (skip replay tests)
python -m pytest tests/ -q -m "not replay"

# Run replay regression tests
python -m pytest tests/ -q -m replay

# Run with verbose output
python -m pytest tests/ -v --tb=short
```

### Quality Gates (CI-equivalent)

```bash
cd backend

# Lint check
ruff check src tests scripts

# Type check
mypy src

# Schema drift check
python scripts/check_schema_drift.py

# Frontend type check
cd ../web && npm run type-check
```

---

## 📈 Monitoring & Observability

### Prometheus Metrics

The `/metrics` endpoint is **publicly accessible** (no auth) for Prometheus scraping:

```bash
curl http://localhost:8000/metrics
```

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'tradingbot'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:8000']
```

### Detailed Health Checks

```bash
curl http://localhost:8000/health/detailed | python -m json.tool
```

Returns component-level status for: database, Redis, LLM provider, broker, and tracing.

### Alert Channels

Configure alert routing via environment variables:

| Channel | Variable | Minimum Severity |
|---------|----------|-----------------|
| Webhook | `ALERT_WEBHOOK_URLS` | `info` |
| Slack | `SLACK_WEBHOOK_URL` | `warning` |
| PagerDuty | `PAGERDUTY_WEBHOOK_URL` | `critical` |
| Opsgenie | `OPSGENIE_WEBHOOK_URL` | `critical` |

---

## 🔄 Core Trading Flow

```
1. Operator authenticates → secure cookie session
2. Worker wakes on schedule → checks bot state + market hours
3. For each watchlist symbol:
   a. Fetch Alpaca bars + news
   b. Compute features (volatility, ATR, gap, volume, opening range, index context)
   c. Validate data freshness + feed integrity
4. Specialist committee produces structured decisions
5. Risk engine approves/rejects with portfolio-aware limits
6. Approved → persisted as execution intents
7. Execution boundary checks liquidity + spread quality
8. Operators review intents (when required)
9. Execution worker submits to Alpaca (re-checks market hours, kill switch, live gates)
10. Fill/cancel/reject outcomes → TCA analytics + execution quality feedback
11. Exits → post-trade reviews with model/prompt lineage tracking
12. Dashboard updates via SSE operations stream
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [System Overview](./docs/overview.md) | High-level system description |
| [Architecture](./docs/architecture.md) | Component architecture and data flow |
| [Backend API](./docs/api.md) | Full API endpoint reference |
| [Dashboard Guide](./docs/dashboard.md) | Operator dashboard features |
| [Configuration](./docs/configuration.md) | All configuration options |
| [Setup & Runbook](./docs/setup.md) | Detailed setup instructions |
| [Deployment](./docs/deployment.md) | Production deployment notes |
| [Operations](./docs/operations.md) | Operational runbook |
| [Release Governance](./docs/release-governance.md) | Release process and PR template |
| [Incident Playbooks](./docs/incident-playbooks.md) | Incident response procedures |
| [Disaster Recovery](./docs/disaster-recovery.md) | DR procedures |
| [Expert Upgrade Roadmap](./docs/expert-upgrade-roadmap.md) | Detailed upgrade plan |
| [Future Upgrades Roadmap](./docs/future-upgrades-roadmap.md) | Phases 10-17 roadmap |
| [Production Hardening](./docs/production-hardening-plan.md) | Production readiness plan |
| [Strategy Change Log](./docs/strategy-change-log.md) | Strategy iteration history |

---

## 🗺️ Roadmap Status

| Phase | Name | Status |
|-------|------|--------|
| 0–9 | Core Engine, Data, AI, Risk, Execution, Observability, Testing | ✅ Complete |
| 10 | Infrastructure as Code | ⚠️ Requires cloud provider |
| 11 | External Observability Pipeline | ✅ Code layer complete |
| 12 | Broker Stream Supervision | ✅ Code layer complete |
| 13 | Multi-Broker Expansion | 🔶 Foundation complete |
| 14 | Advanced AI & ML Signals | 🔶 Foundation complete |
| 15 | Monte Carlo & Stress Testing | ✅ Code layer complete |
| 16 | Compliance & Cost Tracking | 🔶 Partially complete |
| 17 | Mobile & Chat Bots | 📋 Planned |

---

## ⚠️ Disclaimers

- This is a **research and development** trading system. Use at your own risk.
- **Paper trade extensively** before considering any live trading.
- The system does not guarantee profits. Markets are unpredictable.
- No financial advice is provided. This is a software engineering project.
- India market support is currently limited to paper execution via imported files.

---

## 🧾 License

See [LICENSE](./LICENSE) for details.
