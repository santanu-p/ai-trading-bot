# Production Hardening Plan

This document describes the path from the current scaffold to a production-hardened trading system.

Important: "production-hardened" does not mean "fully autonomous with no human oversight" and it does not mean "guaranteed profitable." It means the system can be deployed, operated, observed, changed, and recovered safely under real-world failure conditions.

## What Production-Hardened Means Here

For this repo, production-hardened means:

- the deployed system is reproducible and versioned
- every trading action is auditable
- broker state and internal state are continuously reconciled
- unsupported products cannot accidentally reach execution
- live trading has explicit gates, approvals, and circuit breakers
- failures degrade safely into halt or analysis-only modes
- operators can see, understand, and stop the system quickly
- releases are controlled and reversible
- backups, recovery procedures, and incident playbooks exist

## Current Gap

The current repo is still a scaffold. It has API, worker, dashboard, risk checks, and a narrow broker path, but it does not yet have:

- infrastructure as code
- hardened auth/session handling
- secrets rotation
- full order lifecycle tracking
- broker reconciliation
- reliable deploy and rollback flow
- persistent observability pipeline
- disaster recovery procedures
- production change management

## Production Readiness Exit Criteria

Do not call the system production-hardened until all of these are true:

- database schema changes are migration-driven
- all services have health, readiness, and liveness checks
- all production secrets are externally managed and rotated
- live trading requires explicit enablement beyond mode selection
- broker reconciliation runs continuously and halts on unresolved drift
- order lifecycle events are persisted and queryable
- market-calendar gating blocks invalid sessions
- observability covers logs, metrics, alerts, traces, and audit events
- deployment and rollback steps are documented and rehearsed
- backup and restore are tested
- operator incident playbooks exist for broker outage, bad fills, model failure, and data staleness

## Target Production Shape

Recommended target:

- `web/` deployed separately from the backend
- API service separated from worker service
- Redis isolated from Postgres
- production and paper environments fully separated
- staging and production environments fully separated
- one execution queue and one reconciliation queue
- one source of truth for bot settings and live safety gates

Suggested baseline topology:

1. `web` on Vercel or an equivalent frontend host
2. `api` on a managed container or VM platform
3. `worker` on a managed container or VM platform
4. `postgres` as a managed database with backups and point-in-time recovery
5. `redis` as a managed instance
6. centralized log and metrics backend
7. secrets manager for provider keys and JWT material

## Phase 1: Stabilize The Core Runtime

Goal:

- make the current system deployable without relying on implicit local behavior

Required changes:

- add Alembic and remove startup schema creation
- split API and worker deploy units clearly
- add environment-specific config validation on startup
- add health, readiness, and dependency checks for API and worker
- add startup failure when required secrets or broker settings are missing
- ensure paper and live credentials are separate and validated independently

Repo areas:

- [main.py](../backend/src/tradingbot/api/main.py)
- [config.py](../backend/src/tradingbot/config.py)
- [celery_app.py](../backend/src/tradingbot/worker/celery_app.py)
- [deployment.md](deployment.md)

Exit gate:

- a fresh environment can be deployed using versioned migrations and explicit env config only

## Phase 2: Harden Broker Execution

Goal:

- make trade submission and broker-state tracking reliable enough for controlled live use

Required changes:

- expand the broker interface beyond submit-only behavior
- add full order state tracking
- add reconciliation against broker truth
- add event ingestion from broker streams or polling
- add idempotent execution tasks
- add pre-trade validation for product support, lot size, tick size, and session rules
- halt on unresolved broker-state drift

Repo areas:

- [adapters.py](../backend/src/tradingbot/services/adapters.py)
- [execution.py](../backend/src/tradingbot/services/execution.py)
- [tasks.py](../backend/src/tradingbot/worker/tasks.py)
- [store.py](../backend/src/tradingbot/services/store.py)

Exit gate:

- every submitted order can be traced from local intent to broker acknowledgement to final fill or cancel state

## Phase 3: Add Live Safety Controls

Goal:

- ensure live trading can fail closed, not fail open

Required changes:

- separate `paper`, `live_requested`, and `live_enabled`
- require a second explicit approval for live enablement
- add a global flatten-all action
- add per-strategy and per-broker kill switches
- auto-disable live trading on repeated rejects, reconciliation drift, stale data, or model anomalies
- add mandatory session gating and end-of-day behavior by strategy type

Repo areas:

- [trading.py](../backend/src/tradingbot/api/routers/trading.py)
- [settings.py](../backend/src/tradingbot/schemas/settings.py)
- [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx)
- [operations.md](operations.md)

Exit gate:

- there is no path where a broken provider, stale feed, or accidental mode flip can silently keep live execution active

## Phase 4: Add Observability And Incident Response

Goal:

- make the system diagnosable during real failures

Required changes:

- emit structured JSON logs
- attach request IDs, run IDs, and order IDs across API, worker, and broker calls
- publish metrics for scan runs, approvals, rejects, execution latency, reconciliation drift, and provider failures
- add alerts for kill switch activation, worker failure loops, broker disconnects, and drift events
- add dashboards for operator health, broker health, and live trade health
- add incident playbooks for:
  - broker outage
  - stale market data
  - malformed model output
  - runaway order loop
  - reconciliation mismatch

Repo areas:

- new `backend/src/tradingbot/services/alerts.py`
- new `backend/src/tradingbot/services/reconciliation.py`
- [operations.md](operations.md)

Exit gate:

- an operator can answer what failed, when it failed, what the system did automatically, and what state is safe right now

## Phase 5: Secure The Control Plane

Goal:

- reduce the chance that operator auth, secrets, or configuration changes become the failure source

Required changes:

- replace `localStorage` token handling with secure cookies or short-lived access plus refresh tokens
- add role-based access for operator, reviewer, and admin
- add session expiry and forced logout
- store production secrets in a secrets manager
- rotate JWT and provider credentials
- add IP and user audit history for sensitive actions
- add rate limiting and request size limits
- add CSRF protection if cookie auth is used

Repo areas:

- [auth.py](../backend/src/tradingbot/api/routers/auth.py)
- [security.py](../backend/src/tradingbot/security.py)
- [dashboard-screen.tsx](../web/src/components/dashboard-screen.tsx)

Exit gate:

- sensitive actions such as live enablement, kill switch release, and settings changes are attributable and access-controlled

## Phase 6: Harden Data And Model Inputs

Goal:

- prevent bad or late data from becoming bad trades

Required changes:

- add bar/news freshness checks
- detect missing candles and abnormal data gaps
- require timestamp provenance on every decision
- separate transient feed failures from hard invalid data states
- add prompt and model versioning
- add schema validation and repair flow for agent outputs
- freeze live execution if agent outputs become malformed above threshold

Repo areas:

- [agents.py](../backend/src/tradingbot/services/agents.py)
- [committee.py](../backend/src/tradingbot/services/committee.py)
- [adapters.py](../backend/src/tradingbot/services/adapters.py)
- [committee-decision.schema.json](../contracts/committee-decision.schema.json)

Exit gate:

- the system can prove what data and prompt versions produced each trading decision

## Phase 7: Add Release Discipline

Goal:

- make changes measurable, reversible, and safe to ship

Required changes:

- add CI for lint, types, tests, schema checks, and replay regression
- add staging environment separate from production
- require migration review before deploy
- require paper-trading soak period before live rollout
- add release notes for strategy, risk, and execution changes
- add deployment rollback steps
- add feature flags for broker support and live safety changes

Repo areas:

- repo root CI config
- [expert-upgrade-roadmap.md](expert-upgrade-roadmap.md)
- new `docs/strategy-change-log.md`

Exit gate:

- every change has a known validation path, deploy path, and rollback path

## Phase 8: Add Backup, Recovery, And Continuity

Goal:

- ensure the system can recover from platform or data loss without unsafe restart behavior

Required changes:

- enable managed database backups and PITR
- document Redis recovery expectations and queue-loss behavior
- persist enough execution intent data to resume safely
- add restore drills for Postgres
- add cold-start recovery logic that re-syncs broker state before resuming execution
- define RPO and RTO targets

Suggested targets:

- `RPO`: 5 minutes or better for trading metadata
- `RTO`: 30 minutes or better for paper; stricter if live is enabled

Exit gate:

- after a restart or restore, the system re-enters a safe state before it can trade again

## Phase 9: Controlled Path To Live Trading

Goal:

- move from scaffold to production in stages rather than one cutover

Recommended rollout:

1. `Local development`
   Only structural validation and tests.
2. `Hosted staging`
   Full stack deployed, but no live broker permission.
3. `Paper trading soak`
   Run continuously for multiple sessions with reconciliation and alerts enabled.
4. `Shadow live`
   Observe real broker/account state while not auto-executing.
5. `Limited live pilot`
   Very small watchlist, tight risk caps, manual review of all fills.
6. `Guarded live`
   Auto-execution allowed only after pilot metrics stay within tolerance.

Required live-entry criteria:

- zero unresolved reconciliation drift
- stable provider error rates
- stable worker uptime
- acceptable paper-trading and shadow-trading metrics
- kill switch and flatten-all actions tested
- rollback and incident playbooks rehearsed

## Production Checklist

Before enabling real live trading, confirm:

- migrations are in place
- production secrets are externally managed
- staging exists and is isolated
- paper and live accounts are separated
- broker capabilities are explicit
- unsupported products are blocked before execution
- reconciliation is running
- order lifecycle events are persisted
- alerting is wired
- backup and restore are tested
- live enablement needs explicit approval
- operator playbooks exist

## Immediate Next 10 Hardening Tasks

1. Add Alembic migrations and remove startup `create_all`.
2. Introduce a broker capability registry and execution support matrix.
3. Split decisioning from execution into separate worker paths.
4. Build a real order state model with transition history.
5. Add broker reconciliation and drift-triggered live halt.
6. Add market-calendar and session gating.
7. Replace dashboard token storage with hardened auth/session handling.
8. Add structured logs, metrics, and critical alerts.
9. Create staging and paper-soak deployment workflow.
10. Write incident runbooks for broker outage, stale data, and runaway execution.

## Final Standard

This repo should be considered production-hardened only when:

- it fails safe under provider, broker, and infrastructure faults
- it can be deployed and rolled back predictably
- it can be audited after every trading day
- it can recover from restart without unsafe duplicate execution
- it exposes enough telemetry for fast operator diagnosis
- its live controls are stronger than its trading logic
