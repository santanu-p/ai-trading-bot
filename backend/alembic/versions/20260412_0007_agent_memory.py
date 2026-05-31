"""Agent memory rollups

Revision ID: 20260412_0007
Revises: 20260410_0006
Create Date: 2026-04-12 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_0007"
down_revision = "20260410_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("bot_settings.id"), nullable=False),
        sa.Column("symbol", sa.String(length=48), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("memory_key", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="system"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "symbol", "memory_type", "memory_key", name="uq_agent_memory_profile_symbol_type_key"),
    )
    op.create_index("ix_agent_memories_profile_id", "agent_memories", ["profile_id"], unique=False)
    op.create_index("ix_agent_memories_symbol", "agent_memories", ["symbol"], unique=False)
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"], unique=False)
    op.create_index("ix_agent_memories_memory_key", "agent_memories", ["memory_key"], unique=False)
    op.create_index("ix_agent_memories_last_seen_at", "agent_memories", ["last_seen_at"], unique=False)
    op.create_index("ix_agent_memories_expires_at", "agent_memories", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_memories_expires_at", table_name="agent_memories")
    op.drop_index("ix_agent_memories_last_seen_at", table_name="agent_memories")
    op.drop_index("ix_agent_memories_memory_key", table_name="agent_memories")
    op.drop_index("ix_agent_memories_memory_type", table_name="agent_memories")
    op.drop_index("ix_agent_memories_symbol", table_name="agent_memories")
    op.drop_index("ix_agent_memories_profile_id", table_name="agent_memories")
    op.drop_table("agent_memories")
