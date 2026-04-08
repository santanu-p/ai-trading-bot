"""Phase 5 agent intelligence metadata and trade reviews

Revision ID: 20260408_0003
Revises: 20260408_0002
Create Date: 2026-04-08 00:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0003"
down_revision = "20260408_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_name", sa.String(length=100), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_versions_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("agent_runs", sa.Column("input_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    op.create_table(
        "trade_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_versions_json", sa.JSON(), nullable=False),
        sa.Column("review_score", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("return_pct", sa.Float(), nullable=False),
        sa.Column("loss_cause", sa.String(length=40), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recurring_pattern_key", sa.String(length=80), nullable=True),
        sa.Column("review_payload", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_trade_reviews_source_run_id", "trade_reviews", ["source_run_id"], unique=False)
    op.create_index("ix_trade_reviews_symbol", "trade_reviews", ["symbol"], unique=False)
    op.create_index("ix_trade_reviews_status", "trade_reviews", ["status"], unique=False)
    op.create_index("ix_trade_reviews_model_name", "trade_reviews", ["model_name"], unique=False)
    op.create_index("ix_trade_reviews_loss_cause", "trade_reviews", ["loss_cause"], unique=False)
    op.create_index("ix_trade_reviews_recurring_pattern_key", "trade_reviews", ["recurring_pattern_key"], unique=False)

    op.alter_column("agent_runs", "prompt_versions_json", server_default=None)
    op.alter_column("agent_runs", "input_snapshot_json", server_default=None)


def downgrade() -> None:
    op.drop_table("trade_reviews")
    op.drop_column("agent_runs", "input_snapshot_json")
    op.drop_column("agent_runs", "prompt_versions_json")
    op.drop_column("agent_runs", "model_name")
