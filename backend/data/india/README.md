# India paper-market fixtures

This directory is the default `INDIA_IMPORT_ROOT` for the `india-paper` profile.
It provides small synthetic NSE fixtures so local developers can place a paper
order against imported Indian market data without external credentials.

Expected layout:

- `bars/<SYMBOL>.json` or `bars/<SYMBOL>.csv` for per-symbol OHLCV bars.
- `bars.json` for an aggregate `{ "SYMBOL": [...] }` bar payload.
- `news.json` for optional imported news rows.

Symbols are normalized for filenames by replacing non-alphanumeric characters
with underscores, so `RELIANCE.NSE` maps to `bars/RELIANCE_NSE.json`.
