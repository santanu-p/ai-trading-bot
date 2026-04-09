# Incident Playbooks

These runbooks are the operator starting point for failure handling. They do not replace hosted-provider procedures for infrastructure recovery.

## Broker Outage

1. Stop approving new execution intents.
2. Arm the kill switch or use broker kill if open orders must be canceled immediately.
3. Run reconciliation and capture unresolved mismatch counts.
4. Confirm whether the outage is broker-side, credential-related, or network-related.
5. Keep live execution disabled until reconciliation returns to zero unresolved drift.

## Stale Or Missing Market Data

1. Confirm recent risk events for stale bars, delayed news, or missing candles.
2. Stop the bot if freshness failures are broad rather than symbol-specific.
3. Verify data-provider health before resuming scans.
4. Record the incident window and affected symbols in the daily ops notes.

## Malformed Model Output

1. Check `alert_malformed_outputs`, scan failures, and recent committee payloads.
2. Keep the bot in paper mode or stop new scans if malformed output is persistent.
3. Review prompt/version lineage before changing prompt or model configuration.
4. Record any prompt/model change in [strategy-change-log.md](strategy-change-log.md).

## Runaway Execution Or Unexpected Order Activity

1. Trigger broker kill immediately if orders are actively escaping expected policy.
2. Disable live execution.
3. Run reconciliation and inspect order transitions and fills.
4. Review recent audit logs for operator actions and recent settings changes.
5. Do not re-enable live execution until the cause and rollback path are explicit.

## Reconciliation Drift

1. Run reconciliation immediately.
2. If drift remains unresolved, keep live execution halted.
3. Compare broker open orders, local order transitions, fills, and positions.
4. Resume only after local state and broker state are aligned and documented.
