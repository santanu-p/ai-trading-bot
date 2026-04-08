"""Phase 3 backtest research tables

Revision ID: 20260408_0002
Revises: 20260408_0001
Create Date: 2026-04-08 00:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0002"
down_revision = "20260408_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("initial_equity", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("commission_per_share", sa.Float(), nullable=False),
        sa.Column("fill_delay_bars", sa.Integer(), nullable=False),
        sa.Column("reject_probability", sa.Float(), nullable=False),
        sa.Column("max_holding_bars", sa.Integer(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("rejected_orders", sa.Integer(), nullable=False),
        sa.Column("final_equity", sa.Float(), nullable=False),
        sa.Column("total_return_pct", sa.Float(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("expectancy", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=False),
        sa.Column("turnover", sa.Float(), nullable=False),
        sa.Column("avg_exposure_pct", sa.Float(), nullable=False),
        sa.Column("max_exposure_pct", sa.Float(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("walk_forward_json", sa.JSON(), nullable=False),
        sa.Column("regime_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("equity_curve_json", sa.JSON(), nullable=False),
        sa.Column("symbol_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backtest_reports_task_id", "backtest_reports", ["task_id"], unique=False)
    op.create_index("ix_backtest_reports_status", "backtest_reports", ["status"], unique=False)
    op.create_index("ix_backtest_reports_start_at", "backtest_reports", ["start_at"], unique=False)
    op.create_index("ix_backtest_reports_end_at", "backtest_reports", ["end_at"], unique=False)

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(length=36), sa.ForeignKey("backtest_reports.id"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("regime", sa.String(length=24), nullable=False),
        sa.Column("signal_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("holding_bars", sa.Integer(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("gross_pnl", sa.Float(), nullable=False),
        sa.Column("net_pnl", sa.Float(), nullable=False),
        sa.Column("return_pct", sa.Float(), nullable=False),
        sa.Column("commission_paid", sa.Float(), nullable=False),
        sa.Column("slippage_paid", sa.Float(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
    )
    op.create_index("ix_backtest_trades_report_id", "backtest_trades", ["report_id"], unique=False)
    op.create_index("ix_backtest_trades_symbol", "backtest_trades", ["symbol"], unique=False)
    op.create_index("ix_backtest_trades_status", "backtest_trades", ["status"], unique=False)
    op.create_index("ix_backtest_trades_regime", "backtest_trades", ["regime"], unique=False)
    op.create_index("ix_backtest_trades_signal_at", "backtest_trades", ["signal_at"], unique=False)


def downgrade() -> None:
    op.drop_table("backtest_trades")
    op.drop_table("backtest_reports")
