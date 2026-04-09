# Deployment Notes

## Intended Split

### Frontend

- Deploy `web/` to Vercel

### Backend

Deploy the API and worker to managed runtimes that support:

- long-running background workers
- Redis access
- Postgres access
- environment variables for secrets

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
- Run `alembic upgrade head` before starting API or worker services.
- Launch the worker with `celery -A tradingbot.worker.celery_app:celery_app worker -B --loglevel=INFO`.
- Set `WEB_ORIGIN` and `NEXT_PUBLIC_API_BASE_URL` consistently for the deployed frontend.
- For `staging`/`production`, startup validation now blocks boot if `SESSION_SECRET` is default, secure cookies are disabled, or required broker credentials are missing.
- If `ALLOW_LIVE_TRADING=true`, startup validation requires distinct paper and live credentials.

## Missing Production Hardening

This scaffold does not yet include:

- IaC
- secrets rotation
- HTTPS/reverse-proxy config
- audit retention policies
- external log/metrics/trace sinks
- managed on-call routing and pager integrations
- isolated staged environment promotion and rollback automation

Repo-local release and recovery documentation now lives in:

- [production-hardening-plan.md](production-hardening-plan.md)
- [release-governance.md](release-governance.md)
- [incident-playbooks.md](incident-playbooks.md)
- [disaster-recovery.md](disaster-recovery.md)
