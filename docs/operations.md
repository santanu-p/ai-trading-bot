# Operations Runbook

## Safe Operating Defaults

- Keep the bot in `paper` mode first.
- Start with a very small watchlist.
- Watch risk events before trusting approvals.
- Treat live mode as unsafe until end-to-end broker behavior is validated.

## Daily Operator Flow

1. Log into the dashboard.
2. Confirm the bot is in the intended mode.
3. Confirm the kill switch is off.
4. Confirm watchlist and risk limits.
5. Start the bot.
6. Monitor decisions, orders, and risk events.
7. Stop the bot if event quality degrades or provider failures accumulate.

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

## Before Any Live Use

- validate paper trades thoroughly
- verify bracket order behavior on Alpaca
- verify buying power and position reconciliation
- verify market-hours gating
- verify cooldown logic
- verify dashboard state matches broker state
- add stronger auth/session handling

## Current Operational Gaps

- no manual approval queue
- no reconciliation worker
- no alerting integration
- no explicit exchange holiday calendar enforcement
- no persistent metrics/trace pipeline

