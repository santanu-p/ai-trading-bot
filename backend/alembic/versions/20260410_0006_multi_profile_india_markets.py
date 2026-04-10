"""Multi-profile market support and India paper-market foundation

Revision ID: 20260410_0006
Revises: 20260408_0005
Create Date: 2026-04-10 08:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0006"
down_revision = "20260408_0005"
branch_labels = None
depends_on = None


market_region = sa.Enum("US", "IN", name="marketregion")


def _create_market_region_enum() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        market_region.create(bind, checkfirst=True)


def _ensure_internal_paper_broker_enum() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE brokerslug ADD VALUE IF NOT EXISTS 'internal_paper'")


def _add_profile_id_column(table_name: str, *, nullable: bool = False) -> None:
    server_default = None if nullable else "1"
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("profile_id", sa.Integer(), nullable=nullable, server_default=server_default))
        batch_op.create_foreign_key(f"fk_{table_name}_profile_id_bot_settings", "bot_settings", ["profile_id"], ["id"])
        batch_op.create_index(f"ix_{table_name}_profile_id", ["profile_id"], unique=False)
    if not nullable:
        op.execute(f"UPDATE {table_name} SET profile_id = 1 WHERE profile_id IS NULL")


def upgrade() -> None:
    _create_market_region_enum()
    _ensure_internal_paper_broker_enum()

    with op.batch_alter_table("bot_settings") as batch_op:
        batch_op.add_column(sa.Column("profile_key", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("display_name", sa.String(length=120), nullable=False, server_default="Default profile"))
        batch_op.add_column(sa.Column("market_region", market_region, nullable=False, server_default="US"))
        batch_op.add_column(sa.Column("execution_provider_kind", sa.String(length=40), nullable=False, server_default="alpaca"))
        batch_op.add_column(sa.Column("data_provider_kind", sa.String(length=40), nullable=False, server_default="alpaca"))
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("enabled_exchanges", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("benchmark_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("news_optional", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index("ix_bot_settings_profile_key", ["profile_key"], unique=True)

    op.execute(
        """
        UPDATE bot_settings
        SET
            profile_key = COALESCE(profile_key, 'us-alpaca'),
            display_name = COALESCE(display_name, 'US Alpaca'),
            market_region = COALESCE(market_region, 'US'),
            execution_provider_kind = COALESCE(execution_provider_kind, 'alpaca'),
            data_provider_kind = COALESCE(data_provider_kind, 'alpaca'),
            enabled = COALESCE(enabled, 1),
            is_default = CASE WHEN id = (SELECT MIN(id) FROM bot_settings) THEN 1 ELSE COALESCE(is_default, 0) END,
            enabled_exchanges = CASE
                WHEN enabled_exchanges IS NULL OR enabled_exchanges = '[]' THEN '["NASDAQ","NYSE","ARCA"]'
                ELSE enabled_exchanges
            END,
            benchmark_symbols = CASE
                WHEN benchmark_symbols IS NULL OR benchmark_symbols = '[]' THEN '["SPY","QQQ"]'
                ELSE benchmark_symbols
            END,
            news_optional = COALESCE(news_optional, 0)
        """
    )

    _add_profile_id_column("watchlist_symbols")
    with op.batch_alter_table("watchlist_symbols") as batch_op:
        batch_op.drop_index("ix_watchlist_symbols_symbol")
        batch_op.create_index("ix_watchlist_symbols_symbol", ["symbol"], unique=False)
        batch_op.create_unique_constraint("uq_watchlist_profile_symbol", ["profile_id", "symbol"])

    _add_profile_id_column("agent_runs")
    _add_profile_id_column("trade_candidates")
    _add_profile_id_column("execution_intents")
    _add_profile_id_column("orders")
    _add_profile_id_column("order_state_transitions")
    _add_profile_id_column("order_fills")
    _add_profile_id_column("backtest_reports")
    _add_profile_id_column("backtest_trades")
    _add_profile_id_column("reconciliation_mismatches")
    _add_profile_id_column("portfolio_snapshots")
    _add_profile_id_column("trade_reviews")
    _add_profile_id_column("execution_quality_samples")

    _add_profile_id_column("positions")
    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_index("ix_positions_symbol")
        batch_op.create_index("ix_positions_symbol", ["symbol"], unique=False)
        batch_op.create_unique_constraint("uq_positions_profile_symbol", ["profile_id", "symbol"])

    _add_profile_id_column("symbol_cooldowns")
    with op.batch_alter_table("symbol_cooldowns") as batch_op:
        batch_op.drop_index("ix_symbol_cooldowns_symbol")
        batch_op.create_index("ix_symbol_cooldowns_symbol", ["symbol"], unique=False)
        batch_op.create_unique_constraint("uq_symbol_cooldowns_profile_symbol", ["profile_id", "symbol"])

    _add_profile_id_column("risk_events", nullable=True)
    _add_profile_id_column("audit_logs", nullable=True)

    with op.batch_alter_table("instrument_contracts") as batch_op:
        batch_op.add_column(sa.Column("market_region", market_region, nullable=False, server_default="US"))
        batch_op.add_column(sa.Column("segment", sa.String(length=40), nullable=False, server_default="cash"))
        batch_op.add_column(sa.Column("freeze_quantity", sa.Integer(), nullable=True))
        batch_op.drop_index("ix_instrument_contracts_symbol")
        batch_op.create_index("ix_instrument_contracts_symbol", ["symbol"], unique=False)
        batch_op.create_index("ix_instrument_contracts_market_region", ["market_region"], unique=False)
        batch_op.create_unique_constraint("uq_contract_market_symbol", ["market_region", "symbol"])

    op.execute(
        """
        INSERT INTO bot_settings (
            profile_key,
            display_name,
            market_region,
            execution_provider_kind,
            data_provider_kind,
            enabled,
            is_default,
            enabled_exchanges,
            benchmark_symbols,
            news_optional,
            status,
            mode,
            kill_switch_enabled,
            live_enabled,
            scan_interval_minutes,
            consensus_threshold,
            max_open_positions,
            max_daily_loss_pct,
            max_position_risk_pct,
            max_symbol_notional_pct,
            max_gross_exposure_pct,
            max_sector_exposure_pct,
            max_correlation_exposure_pct,
            max_event_cluster_positions,
            volatility_target_pct,
            atr_sizing_multiplier,
            equity_curve_throttle_start_pct,
            equity_curve_throttle_min_scale,
            intraday_drawdown_pause_pct,
            loss_streak_reduction_threshold,
            loss_streak_size_scale,
            execution_failure_review_threshold,
            severe_anomaly_kill_switch_threshold,
            symbol_cooldown_minutes,
            symbol_cooldown_profit_minutes,
            symbol_cooldown_stopout_minutes,
            symbol_cooldown_event_minutes,
            symbol_cooldown_whipsaw_minutes,
            openai_model,
            broker_slug,
            broker_account_type,
            broker_venue,
            broker_timezone,
            broker_base_currency,
            broker_permissions,
            profile_notes,
            created_at,
            updated_at
        )
        SELECT
            'india-paper',
            'India Paper',
            'IN',
            'internal_paper',
            'imported_files',
            1,
            0,
            '["NSE","BSE","MCX"]',
            '["NIFTY 50","BANKNIFTY","SENSEX"]',
            1,
            'STOPPED',
            'PAPER',
            0,
            0,
            5,
            0.64,
            6,
            0.025,
            0.005,
            0.16,
            0.9,
            0.35,
            0.45,
            3,
            1.2,
            1.0,
            0.015,
            0.4,
            0.03,
            3,
            0.6,
            3,
            4,
            45,
            20,
            90,
            180,
            120,
            'gpt-5-mini',
            'internal_paper',
            'paper',
            'India markets',
            'Asia/Kolkata',
            'INR',
            '["paper","cash_equity","futures","options","commodities"]',
            '',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM bot_settings WHERE profile_key = 'india-paper'
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("instrument_contracts") as batch_op:
        batch_op.drop_constraint("uq_contract_market_symbol", type_="unique")
        batch_op.drop_index("ix_instrument_contracts_market_region")
        batch_op.drop_column("freeze_quantity")
        batch_op.drop_column("segment")
        batch_op.drop_column("market_region")

    for table_name in (
        "execution_quality_samples",
        "trade_reviews",
        "portfolio_snapshots",
        "reconciliation_mismatches",
        "backtest_trades",
        "backtest_reports",
        "order_fills",
        "order_state_transitions",
        "orders",
        "execution_intents",
        "trade_candidates",
        "agent_runs",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_profile_id")
            batch_op.drop_constraint(f"fk_{table_name}_profile_id_bot_settings", type_="foreignkey")
            batch_op.drop_column("profile_id")

    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_constraint("uq_positions_profile_symbol", type_="unique")
        batch_op.drop_index("ix_positions_profile_id")
        batch_op.drop_constraint("fk_positions_profile_id_bot_settings", type_="foreignkey")
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("symbol_cooldowns") as batch_op:
        batch_op.drop_constraint("uq_symbol_cooldowns_profile_symbol", type_="unique")
        batch_op.drop_index("ix_symbol_cooldowns_profile_id")
        batch_op.drop_constraint("fk_symbol_cooldowns_profile_id_bot_settings", type_="foreignkey")
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("watchlist_symbols") as batch_op:
        batch_op.drop_constraint("uq_watchlist_profile_symbol", type_="unique")
        batch_op.drop_index("ix_watchlist_symbols_profile_id")
        batch_op.drop_constraint("fk_watchlist_symbols_profile_id_bot_settings", type_="foreignkey")
        batch_op.drop_column("profile_id")

    for table_name in ("risk_events", "audit_logs"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_profile_id")
            batch_op.drop_constraint(f"fk_{table_name}_profile_id_bot_settings", type_="foreignkey")
            batch_op.drop_column("profile_id")

    op.execute("DELETE FROM bot_settings WHERE profile_key = 'india-paper'")

    with op.batch_alter_table("bot_settings") as batch_op:
        batch_op.drop_index("ix_bot_settings_profile_key")
        batch_op.drop_column("news_optional")
        batch_op.drop_column("benchmark_symbols")
        batch_op.drop_column("enabled_exchanges")
        batch_op.drop_column("is_default")
        batch_op.drop_column("enabled")
        batch_op.drop_column("data_provider_kind")
        batch_op.drop_column("execution_provider_kind")
        batch_op.drop_column("market_region")
        batch_op.drop_column("display_name")
        batch_op.drop_column("profile_key")

