# Disaster Recovery

This document describes the safe restart posture for the trading control plane.

## Targets

- `RPO`: 5 minutes or better for trading metadata when hosted backups and PITR are enabled
- `RTO`: 30 minutes or better for paper environments; tighter only after live operations are proven stable

## Recovery Expectations

- Postgres should provide managed backups and point-in-time recovery
- Redis is treated as recoverable-but-ephemeral; queue loss must be assumed unless the hosted service guarantees persistence
- the API and worker must not resume trading activity until broker reconciliation has completed after recovery

## Cold-Start Sequence

1. Restore Postgres from the selected recovery point.
2. Recreate Redis and assume transient queue state may be lost.
3. Run database migrations and boot the API in a non-trading state.
4. Run reconciliation before starting normal scans or execution workers.
5. Verify unresolved mismatch count is zero.
6. Re-enable paper or live activity only after operator review.

## Restore Drill Expectations

- rehearse Postgres restore against a non-production environment
- confirm audit logs, order lifecycle rows, fills, positions, and trade reviews are present after restore
- document drill date, restore duration, mismatch count, and any manual repair steps
