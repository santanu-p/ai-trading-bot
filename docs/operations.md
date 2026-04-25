# Operations Runbook

## Safe Operating Defaults

- Keep the bot in `paper` mode first.
- Start with a very small watchlist.
- Watch risk events before trusting approvals.
- Treat live mode as unsafe until end-to-end broker behavior is validated.

## Daily Operator Flow

1. Log into the dashboard.
2. Confirm the bot is in the intended mode.
3. Confirm `live_enabled` is in the intended state (live only).
4. Confirm the kill switch is off.
5. Confirm watchlist and risk limits.
6. Start the bot.
7. Review pending execution intents and approve/reject as needed.
8. Monitor decisions, orders, reconciliation mismatches, and risk events.
9. Use the Backtests view to run replay studies before changing thresholds or model settings.
10. Stop the bot if event quality degrades or provider failures accumulate.

## Kill Switch Guidance

Use the kill switch when:

- provider responses are unstable
- agent output becomes malformed
- the worker is producing repeated failures
- order behavior looks inconsistent
- you need an immediate operational halt

## Failure Classes To Watch

- `scan_failure`
- `trade_rejected`
- `risk_rejected`
- `pretrade_rejected`
- `broker_submit_failed`
- `broker_stream_unknown_order`
- `reconciliation_unresolved`
- `alert_worker_failures`
- `alert_high_rejection_rate`
- `alert_malformed_outputs`
- `alert_kill_switch_activated`
- `alert_reconciliation_unresolved`

## Release Discipline Checks

Before shipping strategy, prompt, risk-threshold, or execution-logic changes:

See [setup.md](setup.md) for the exact local commands and [release-governance.md](release-governance.md) for the PR evidence requirements.

1. Run backend lint/type/unit/replay checks and the web type-check.
2. Run schema drift verification.
3. Record a release entry in [strategy-change-log.md](strategy-change-log.md) with replay evidence and rollback notes.
4. Record explicit approver sign-off in the release entry and name the independent reviewer in the PR release-control section.

## Incident References

- [incident-playbooks.md](incident-playbooks.md)
- [disaster-recovery.md](disaster-recovery.md)

## Before Any Live Use

- validate paper trades thoroughly
- verify bracket order behavior on Alpaca
- verify buying power and position reconciliation
- verify market-hours gating
- verify cooldown logic
- verify dashboard state matches broker state
- confirm hosted secret handling, HTTPS, and alert-routing integrations are in place

## Current Operational Gaps

- no externalized metrics/trace sink (telemetry is currently in-process only)
- webhook alert delivery is generic only; managed pager/on-call routing is still external
- the dashboard has a backend SSE stream, and broker trade-update payloads now have a repo-local parser/ingestion path; a long-running broker websocket supervisor still needs hosted deployment wiring
- backup/PITR, restore drills, and queue-loss expectations still depend on hosted platform configuration
