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
- `reconciliation_unresolved`

## Before Any Live Use

- validate paper trades thoroughly
- verify bracket order behavior on Alpaca
- verify buying power and position reconciliation
- verify market-hours gating
- verify cooldown logic
- verify dashboard state matches broker state
- add stronger auth/session handling

## Current Operational Gaps

- no alerting integration
- no persistent metrics/trace pipeline
- no websocket event stream from the broker into the dashboard
