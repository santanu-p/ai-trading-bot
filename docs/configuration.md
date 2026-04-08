# Configuration

## Environment File

The root `.env.example` documents the current configuration surface.

## Core Variables

### Database and queue

- `DATABASE_URL`
- `REDIS_URL`

### Auth

- `SESSION_SECRET`
- `SESSION_EXPIRE_MINUTES`
- `SESSION_COOKIE_NAME`
- `SESSION_COOKIE_SECURE`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `ADMIN_PASSWORD_HASH`
- `OPERATOR_EMAIL`
- `OPERATOR_PASSWORD`
- `OPERATOR_PASSWORD_HASH`
- `REVIEWER_EMAIL`
- `REVIEWER_PASSWORD`
- `REVIEWER_PASSWORD_HASH`

Use either the plain password or the password hash for each configured role. The code will prefer the hash when present.

### OpenAI

- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### Gemini

- `GEMINI_API_KEY`
- `GEMINI_MODEL`

### Alpaca

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `ALPACA_PAPER_BASE_URL`
- `ALPACA_LIVE_BASE_URL`
- `ALPACA_DATA_BASE_URL`
- `ALPACA_MARKET_DATA_FEED`

### Frontend/API coordination

- `WEB_ORIGIN`
- `API_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`

### Live trading gates

- `ALLOW_LIVE_TRADING`
- `LIVE_TRADING_ALLOWED_BROKERS`
- `LIVE_ENABLE_CODE_TTL_MINUTES`
- `INTRADAY_FLATTEN_BUFFER_MINUTES`

## Runtime Defaults In Code

Current code defaults include:

- market timezone: `America/New_York`
- scan interval: `5`
- consensus threshold: `0.64`
- minimum approval votes: `2`

## Configuration Ownership

- The environment controls infrastructure and external providers.
- The database-backed bot settings control operator-tuned behavior such as watchlists and risk thresholds.
