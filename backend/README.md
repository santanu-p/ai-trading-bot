# Tradingbot Backend

FastAPI API, Celery worker, SQLAlchemy models, and service integrations for the AI trading bot.

## Current Market Profiles

- `us-alpaca`: default US profile for Alpaca paper/live cash-equity flows
- `india-paper`: India research, paper execution, and backtest profile backed by imported files

## India Data Import Root

- Configure `INDIA_IMPORT_ROOT` to point at the folder used by the India imported-data adapters
- Expected inputs include contract metadata plus optional `bars/` symbol files, `bars.json`, and `news.json`

## Verification

- Backend tests passed with `PYTHONPATH=src python -m pytest -p no:cacheprovider`
