# Deployment Notes

## Intended Split

### Frontend

- Deploy `web/` to Vercel

### Backend

Deploy the API and worker to a managed runtime that supports:

- long-running background workers
- Redis access
- Postgres access
- environment variables for secrets

The original plan assumed a managed backend platform alongside Vercel.

## Required Hosted Dependencies

- Postgres
- Redis
- Alpaca credentials
- OpenAI credentials

## Deployment Concerns

- Do not enable live mode by default.
- Configure separate paper and live broker credentials (`ALPACA_PAPER_API_*`, `ALPACA_LIVE_API_*`).
- Treat `SESSION_SECRET` and provider keys as platform-managed secrets.
- Ensure the worker and API share the same database and Redis.
- Run `alembic upgrade head` before starting API or worker revisions.
- Set the frontend origin and API base URL consistently.
- For `staging`/`production`, startup validation now blocks boot if `SESSION_SECRET` is default, secure cookies are disabled, or required broker credentials are missing.
- If `ALLOW_LIVE_TRADING=true`, startup validation requires distinct paper and live credentials.

## Missing Production Hardening

This scaffold does not yet include:

- IaC
- secrets rotation
- HTTPS/reverse-proxy config
- rate limiting
- audit retention policies
- observability stack wiring
- CSRF hardening for cookie-based auth

For the step-by-step path from this scaffold to a hardened deployment target, see [production-hardening-plan.md](production-hardening-plan.md).
