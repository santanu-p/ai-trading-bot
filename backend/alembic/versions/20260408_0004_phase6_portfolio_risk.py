"""Phase 6 portfolio-risk controls and cooldown state

Revision ID: 20260408_0004
Revises: 20260408_0003
Create Date: 2026-04-08 01:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0004"
down_revision = "20260408_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bot_settings", sa.Column("max_gross_exposure_pct", sa.Float(), nullable=False, server_default="0.9"))
    op.add_column("bot_settings", sa.Column("max_sector_exposure_pct", sa.Float(), nullable=False, server_default="0.35"))
    op.add_column(
        "bot_settings",
        sa.Column("max_correlation_exposure_pct", sa.Float(), nullable=False, server_default="0.45"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("max_event_cluster_positions", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("bot_settings", sa.Column("volatility_target_pct", sa.Float(), nullable=False, server_default="1.2"))
    op.add_column("bot_settings", sa.Column("atr_sizing_multiplier", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column(
        "bot_settings",
        sa.Column("equity_curve_throttle_start_pct", sa.Float(), nullable=False, server_default="0.015"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("equity_curve_throttle_min_scale", sa.Float(), nullable=False, server_default="0.4"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("intraday_drawdown_pause_pct", sa.Float(), nullable=False, server_default="0.03"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("loss_streak_reduction_threshold", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("bot_settings", sa.Column("loss_streak_size_scale", sa.Float(), nullable=False, server_default="0.6"))
    op.add_column(
        "bot_settings",
        sa.Column("execution_failure_review_threshold", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("severe_anomaly_kill_switch_threshold", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("symbol_cooldown_profit_minutes", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("symbol_cooldown_stopout_minutes", sa.Integer(), nullable=False, server_default="90"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("symbol_cooldown_event_minutes", sa.Integer(), nullable=False, server_default="180"),
    )
    op.add_column(
        "bot_settings",
        sa.Column("symbol_cooldown_whipsaw_minutes", sa.Integer(), nullable=False, server_default="120"),
    )

    op.create_table(
        "symbol_cooldowns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("cooldown_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_symbol_cooldowns_symbol", "symbol_cooldowns", ["symbol"], unique=True)
    op.create_index("ix_symbol_cooldowns_cooldown_type", "symbol_cooldowns", ["cooldown_type"], unique=False)
    op.create_index("ix_symbol_cooldowns_triggered_at", "symbol_cooldowns", ["triggered_at"], unique=False)
    op.create_index("ix_symbol_cooldowns_expires_at", "symbol_cooldowns", ["expires_at"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for column in (
            "max_gross_exposure_pct",
            "max_sector_exposure_pct",
            "max_correlation_exposure_pct",
            "max_event_cluster_positions",
            "volatility_target_pct",
            "atr_sizing_multiplier",
            "equity_curve_throttle_start_pct",
            "equity_curve_throttle_min_scale",
            "intraday_drawdown_pause_pct",
            "loss_streak_reduction_threshold",
            "loss_streak_size_scale",
            "execution_failure_review_threshold",
            "severe_anomaly_kill_switch_threshold",
            "symbol_cooldown_profit_minutes",
            "symbol_cooldown_stopout_minutes",
            "symbol_cooldown_event_minutes",
            "symbol_cooldown_whipsaw_minutes",
        ):
            op.alter_column("bot_settings", column, server_default=None)


def downgrade() -> None:
    op.drop_table("symbol_cooldowns")

    op.drop_column("bot_settings", "symbol_cooldown_whipsaw_minutes")
    op.drop_column("bot_settings", "symbol_cooldown_event_minutes")
    op.drop_column("bot_settings", "symbol_cooldown_stopout_minutes")
    op.drop_column("bot_settings", "symbol_cooldown_profit_minutes")
    op.drop_column("bot_settings", "severe_anomaly_kill_switch_threshold")
    op.drop_column("bot_settings", "execution_failure_review_threshold")
    op.drop_column("bot_settings", "loss_streak_size_scale")
    op.drop_column("bot_settings", "loss_streak_reduction_threshold")
    op.drop_column("bot_settings", "intraday_drawdown_pause_pct")
    op.drop_column("bot_settings", "equity_curve_throttle_min_scale")
    op.drop_column("bot_settings", "equity_curve_throttle_start_pct")
    op.drop_column("bot_settings", "atr_sizing_multiplier")
    op.drop_column("bot_settings", "volatility_target_pct")
    op.drop_column("bot_settings", "max_event_cluster_positions")
    op.drop_column("bot_settings", "max_correlation_exposure_pct")
    op.drop_column("bot_settings", "max_sector_exposure_pct")
    op.drop_column("bot_settings", "max_gross_exposure_pct")
