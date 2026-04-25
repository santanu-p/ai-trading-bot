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

### Release ID: phase11-market-efficiency-ops-v1

- Date (UTC): 2026-04-25
- Scope: broker stream ingestion hooks, market-efficiency reporting, AI decision audit scoring, and stream-failure injection coverage
- Prompt/version changes: none
- Risk-rule changes: no threshold changes; added risk calibration reporting over approvals, rejects, execution quality, and post-trade review pressure
- Execution-behavior changes: Alpaca trade-update payloads can now be mapped into broker stream events, and stream events update local orders/fills through the existing execution service while unmatched broker events emit critical risk events
- Threshold/config changes: none
- Replay evidence: focused phase 11 coverage in [backend/tests/test_phase11_market_efficiency.py](../backend/tests/test_phase11_market_efficiency.py); full backend verification passed with `55 passed, 4 skipped`
- Rollback plan: remove the broker stream event mapper/ingestion method, disable the `/risk/calibration` and `/ai/decision-audit` endpoints, and revert the phase 11 tests if the reporting or stream-ingestion path interferes with operator workflows
- Approver: admin operator

### Release ID: phase10-control-plane-ops-v1

- Date (UTC): 2026-04-09
- Scope: control-plane hardening, operator streaming, and release-governance guardrails
- Prompt/version changes: none
- Risk-rule changes: none to trade selection logic; control-plane mutations now require synchronized CSRF tokens and are rate-limited
- Execution-behavior changes: operator surface now consumes a backend SSE operations stream and alert webhook dispatch can forward operational alerts externally
- Threshold/config changes: added request-size, rate-limit, SSE poll interval, and alert-webhook configuration surface
- Replay evidence: not a strategy replay release; regression coverage was added in [backend/tests/test_phase10_control_plane.py](../backend/tests/test_phase10_control_plane.py) and backend Python source was syntax-checked in-memory in this task, with full pytest/type-check deferred to CI because local dependencies were intentionally not installed
- Rollback plan: remove the control-plane middleware hardening paths, disable the release-guard workflow, and revert the dashboard SSE/trade-review/operator-surface additions if they block operator workflows
- Approver: admin operator

### Release ID: phase7-execution-quality-v1

- Date (UTC): 2026-04-08
- Scope: execution quality modeling and TCA persistence
- Prompt/version changes: committee payload now includes execution-quality context for downstream decisioning
- Risk-rule changes: symbol-level execution feedback can throttle size or block new entries
- Execution-behavior changes: pre-submit spread/slippage/liquidity gating and adaptive aggressiveness
- Threshold/config changes: execution-quality policy defaults for spread/slippage/liquidity feedback
- Replay evidence: execution-quality coverage in [backend/tests/test_phase7_execution_quality.py](../backend/tests/test_phase7_execution_quality.py)
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
