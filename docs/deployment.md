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
- OpenAI or Gemini credentials

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

## Production Observability (Implemented)

The following observability features are built into the backend:

- **Prometheus metrics**: Scrape `GET /metrics` for counters and duration histograms
- **Health checks**: `GET /health/detailed` provides component-level status (DB, Redis, LLM, broker, tracing)
- **Distributed tracing**: trace_id/span_id propagation via `contextvars` with W3C Trace-Context headers
- **Multi-channel alerts**: severity-based routing to webhook, Slack, PagerDuty, and Opsgenie with suppression/deduplication
- **LLM cost tracking**: per-call token usage and cost estimation with aggregated reporting

## Stream Supervisor (Implemented)

- Celery-managed broker stream supervision with automatic reconnect and backfill
- REST polling fallback (production deployments should add the `websockets` library for sub-second latency)
- Auto-restart via periodic health-check task

## Compliance & Reporting (Implemented)

- Automated daily trade reports
- PDT detection, wash-sale detection, position limit monitoring
- Monte Carlo risk simulation (VaR/CVaR, stress scenarios)

## Remaining Production Hardening

This scaffold does not yet include:

- IaC (Terraform/Pulumi/CDK) for cloud provisioning
- secrets rotation via managed services (AWS Secrets Manager, GCP Secret Manager)
- HTTPS/reverse-proxy config (use nginx, Caddy, or a cloud load balancer)
- audit retention policies with automated cleanup
- isolated staged environment promotion and rollback automation

Repo-local release and recovery documentation lives in:

- [production-hardening-plan.md](production-hardening-plan.md)
- [release-governance.md](release-governance.md)
- [incident-playbooks.md](incident-playbooks.md)
- [disaster-recovery.md](disaster-recovery.md)
