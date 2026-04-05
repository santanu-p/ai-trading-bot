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
- Separate paper and live credentials if you extend the configuration surface later.
- Treat `JWT_SECRET` and provider keys as platform-managed secrets.
- Ensure the worker and API share the same database and Redis.
- Set the frontend origin and API base URL consistently.

## Missing Production Hardening

This scaffold does not yet include:

- IaC
- secrets rotation
- HTTPS/reverse-proxy config
- rate limiting
- audit retention policies
- health/readiness probes beyond `/health`
- observability stack wiring
- scheduled trading-calendar gating

For the step-by-step path from this scaffold to a hardened deployment target, see [production-hardening-plan.md](production-hardening-plan.md).
