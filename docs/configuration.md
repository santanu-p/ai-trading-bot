# Configuration

## Environment File

The root `.env.example` is the starting point for local and hosted configuration. It includes all runtime variables used by the API, worker, stream supervisor, and web app, organized by functional group.

## Core Variables

### Database and queue

- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string

### Environment

- `ENVIRONMENT` — One of: `development`, `test`, `staging`, `production`

### Auth

- `SESSION_SECRET` — Must be ≥ 32 characters in staging/production
- `SESSION_EXPIRE_MINUTES` — Session lifetime (default: 720 = 12 hours)
- `SESSION_COOKIE_NAME`
- `CSRF_COOKIE_NAME`
- `CSRF_HEADER_NAME`
- `SESSION_COOKIE_SECURE` — Set `true` in production (HTTPS only)
- `CSRF_ORIGIN_ENFORCEMENT` — Keep enabled

### Operator accounts

- `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_PASSWORD_HASH`
- `OPERATOR_EMAIL` / `OPERATOR_PASSWORD` / `OPERATOR_PASSWORD_HASH`
- `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` / `REVIEWER_PASSWORD_HASH`

Use either the plain password or the password hash for each configured role. The code will prefer the hash when present.

Legacy fallback names still accepted by `config.py`:

- `JWT_SECRET`
- `JWT_EXPIRE_MINUTES`

### OpenAI

- `OPENAI_API_KEY`
- `OPENAI_MODEL` — Default: `gpt-5-mini`

### Gemini

- `GEMINI_API_KEY`
- `GEMINI_MODEL` — Default: `gemini-2.5-flash`

### Alpaca

- `ALPACA_API_KEY` / `ALPACA_API_SECRET` — Legacy fallback
- `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_API_SECRET` — Paper trading
- `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_API_SECRET` — Live trading
- `ALPACA_PAPER_BASE_URL` — Default: `https://paper-api.alpaca.markets`
- `ALPACA_LIVE_BASE_URL` — Default: `https://api.alpaca.markets`
- `ALPACA_DATA_BASE_URL` — Default: `https://data.alpaca.markets`
- `ALPACA_MARKET_DATA_FEED` — `iex` (free) or `sip` (paid)

The shared `ALPACA_API_*` pair is a fallback for development. If live trading is enabled, the runtime requires distinct paper and live credential pairs.

### Trading tuning

- `MARKET_TIMEZONE` — Default: `America/New_York`
- `SCAN_INTERVAL_MINUTES` — Default: `5`
- `CONSENSUS_THRESHOLD` — Default: `0.64`
- `MIN_APPROVAL_VOTES` — Default: `2`

### Rate limiting and security

- `REQUEST_BODY_MAX_BYTES` — Default: `1000000` (1 MB)
- `API_RATE_LIMIT_PER_MINUTE` — Default: `240`
- `AUTH_RATE_LIMIT_PER_MINUTE` — Default: `20`
- `RATE_LIMIT_WINDOW_SECONDS` — Default: `60`

### Stream supervisor

- `STREAM_POLL_INTERVAL_SECONDS` — Default: `5`

### Alert routing

- `ALERT_WEBHOOK_URLS` — Comma-separated generic webhook URLs (receives all severities)
- `ALERT_WEBHOOK_TIMEOUT_SECONDS` — Default: `5`
- `SLACK_WEBHOOK_URL` — Slack incoming webhook (receives `warning`+ alerts)
- `PAGERDUTY_WEBHOOK_URL` — PagerDuty Events API v2 (receives `critical`+ alerts)
- `OPSGENIE_WEBHOOK_URL` — Opsgenie webhook (receives `critical`+ alerts)

### ML model storage

- `ML_MODEL_DIR` — Directory for trained ML models. Default: `data/models`

### Live trading gates

- `ALLOW_LIVE_TRADING` — Master switch. Default: `false`
- `LIVE_TRADING_ALLOWED_BROKERS` — Comma-separated broker slugs
- `LIVE_ENABLE_CODE_TTL_MINUTES` — Default: `10`
- `INTRADAY_FLATTEN_BUFFER_MINUTES` — Default: `15`

### Frontend/API coordination

- `WEB_ORIGIN` — Frontend origin for CORS
- `NEXT_PUBLIC_API_BASE_URL` — API URL for the Next.js frontend

## Runtime Defaults In Code

Current code defaults include:

- market timezone: `America/New_York`
- scan interval: `5` minutes
- consensus threshold: `0.64`
- minimum approval votes: `2`
- alert suppression cooldown: `30` minutes
- ML signal blending: 30% ML / 70% LLM
- Monte Carlo simulations: `1000`
- FX rate cache TTL: `60` minutes

## Configuration Ownership

- The environment controls infrastructure, external providers, and operational tuning.
- The database-backed bot settings control operator-tuned behavior such as watchlists and risk thresholds.
- ML model weights are persisted to the local filesystem and loaded at prediction time.
- Alert suppression state and cost tracking are in-process and reset on restart.
