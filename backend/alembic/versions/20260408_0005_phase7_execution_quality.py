"""Phase 7 execution-quality and TCA analytics

Revision ID: 20260408_0005
Revises: 20260408_0004
Create Date: 2026-04-08 02:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0005"
down_revision = "20260408_0004"
branch_labels = None
depends_on = None


broker_slug = sa.Enum("alpaca", name="brokerslug", create_type=False)
order_intent = sa.Enum("buy", "sell", "hold", name="orderintent", create_type=False)
order_type = sa.Enum("market", "limit", "stop_market", "stop_limit", "bracket", "oco", "trailing_stop", name="ordertype", create_type=False)
order_status = sa.Enum(
    "new",
    "accepted",
    "pending_trigger",
    "partially_filled",
    "filled",
    "canceled",
    "expired",
    "replaced",
    "rejected",
    "suspended",
    name="orderstatus",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "execution_quality_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("broker_slug", broker_slug, nullable=False),
        sa.Column("venue", sa.String(length=80), nullable=False),
        sa.Column("order_type", order_type, nullable=False),
        sa.Column("side", order_intent, nullable=False),
        sa.Column("outcome_status", order_status, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), nullable=False),
        sa.Column("fill_ratio", sa.Float(), nullable=False),
        sa.Column("intended_price", sa.Float(), nullable=True),
        sa.Column("realized_price", sa.Float(), nullable=True),
        sa.Column("expected_slippage_bps", sa.Float(), nullable=True),
        sa.Column("realized_slippage_bps", sa.Float(), nullable=True),
        sa.Column("expected_spread_bps", sa.Float(), nullable=True),
        sa.Column("spread_cost", sa.Float(), nullable=False),
        sa.Column("notional", sa.Float(), nullable=False),
        sa.Column("time_to_fill_seconds", sa.Float(), nullable=True),
        sa.Column("aggressiveness", sa.String(length=24), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_execution_quality_samples_order_id", "execution_quality_samples", ["order_id"], unique=True)
    op.create_index("ix_execution_quality_samples_symbol", "execution_quality_samples", ["symbol"], unique=False)
    op.create_index("ix_execution_quality_samples_broker_slug", "execution_quality_samples", ["broker_slug"], unique=False)
    op.create_index("ix_execution_quality_samples_venue", "execution_quality_samples", ["venue"], unique=False)
    op.create_index("ix_execution_quality_samples_order_type", "execution_quality_samples", ["order_type"], unique=False)
    op.create_index("ix_execution_quality_samples_outcome_status", "execution_quality_samples", ["outcome_status"], unique=False)


def downgrade() -> None:
    op.drop_table("execution_quality_samples")
