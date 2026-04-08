# Strategy Change Log

This log treats strategy, risk, execution, and prompt changes as release artifacts.
Each entry is expected to carry replay evidence and rollback notes.

## Entry Template

- Release ID:
- Date (UTC):
- Scope:
- Prompt/version changes:
- Risk-rule changes:
- Execution-behavior changes:
- Threshold/config changes:
- Replay evidence:
- Rollback plan:
- Approver:

## Releases

### Release ID: phase7-execution-quality-v1

- Date (UTC): 2026-04-08
- Scope: execution quality modeling and TCA persistence
- Prompt/version changes: committee payload now includes execution-quality context for downstream decisioning
- Risk-rule changes: symbol-level execution feedback can throttle size or block new entries
- Execution-behavior changes: pre-submit spread/slippage/liquidity gating and adaptive aggressiveness
- Threshold/config changes: execution-quality policy defaults for spread/slippage/liquidity feedback
- Replay evidence: fixture-based backtest and fill replay tests in [backend/tests/test_phase3_backtest.py](../backend/tests/test_phase3_backtest.py)
- Rollback plan: disable execution-quality gating path and revert to baseline bracket submission logic
- Approver: admin operator

### Release ID: phase8-observability-operations-v1

- Date (UTC): 2026-04-08
- Scope: structured telemetry and operational alerting
- Prompt/version changes: none
- Risk-rule changes: none
- Execution-behavior changes: none (instrumentation and alert synthesis only)
- Threshold/config changes: runtime alert thresholds for worker failures, rejection pressure, and malformed output rates
- Replay evidence: observability alert/metrics tests in [backend/tests/test_phase8_observability.py](../backend/tests/test_phase8_observability.py)
- Rollback plan: disable alert synthesis and middleware/task instrumentation hooks
- Approver: admin operator

### Release ID: phase9-testing-release-discipline-v1

- Date (UTC): 2026-04-08
- Scope: release discipline and automated quality gates
- Prompt/version changes: none
- Risk-rule changes: none
- Execution-behavior changes: added replay-regression worker task for deterministic release checks
- Threshold/config changes: none
- Replay evidence: replay E2E and worker replay tests in [backend/tests/test_phase9_replay_e2e.py](../backend/tests/test_phase9_replay_e2e.py) and [backend/tests/test_phase9_worker_tasks.py](../backend/tests/test_phase9_worker_tasks.py)
- Rollback plan: keep existing runtime behavior and disable CI replay/schema checks if emergency rollback is required
- Approver: admin operator
