"""Phase 1 foundations schema

Revision ID: 20260408_0001
Revises:
Create Date: 2026-04-08 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0001"
down_revision = None
branch_labels = None
depends_on = None


bot_status = sa.Enum("running", "stopped", name="botstatus")
trading_mode = sa.Enum("paper", "live", name="tradingmode")
broker_slug = sa.Enum("alpaca", name="brokerslug")
trading_pattern = sa.Enum(
    "scalping",
    "intraday",
    "delivery",
    "swing",
    "positional",
    "btst_stbt",
    "futures_directional",
    "futures_hedged",
    "options_buying",
    "options_selling",
    name="tradingpattern",
)
instrument_class = sa.Enum("cash_equity", "futures", "options", "mixed", name="instrumentclass")
strategy_family = sa.Enum(
    "momentum_breakout",
    "trend_following",
    "mean_reversion",
    "event_driven",
    "price_action",
    "option_premium_decay",
    "hedged_carry",
    "multi_factor",
    name="strategyfamily",
)
risk_profile = sa.Enum("conservative", "balanced", "aggressive", name="riskprofile")
market_universe = sa.Enum("large_cap", "large_mid_cap", "index_only", "sector_focus", "custom_watchlist", name="marketuniverse")
operator_role = sa.Enum("reviewer", "operator", "admin", "system", name="operatorrole")
run_status = sa.Enum("queued", "running", "succeeded", "failed", name="runstatus")
order_intent = sa.Enum("buy", "sell", "hold", name="orderintent")
execution_intent_status = sa.Enum(
    "pending_approval",
    "approved",
    "executing",
    "executed",
    "rejected",
    "blocked",
    "failed",
    "canceled",
    name="executionintentstatus",
)
execution_intent_type = sa.Enum("trade", "flatten_all", "broker_kill", name="executionintenttype")
order_type = sa.Enum("market", "limit", "stop_market", "stop_limit", "bracket", "oco", "trailing_stop", name="ordertype")
time_in_force = sa.Enum("day", "gtc", "ioc", "fok", name="timeinforce")
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
)
option_right = sa.Enum("call", "put", name="optionright")


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        bot_status,
        trading_mode,
        broker_slug,
        trading_pattern,
        instrument_class,
        strategy_family,
        risk_profile,
        market_universe,
        operator_role,
        run_status,
        order_intent,
        execution_intent_status,
        execution_intent_type,
        order_type,
        time_in_force,
        order_status,
        option_right,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "bot_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", bot_status, nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
        sa.Column("live_enabled", sa.Boolean(), nullable=False),
        sa.Column("live_enable_code_hash", sa.Text(), nullable=True),
        sa.Column("live_enable_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("consensus_threshold", sa.Float(), nullable=False),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("max_daily_loss_pct", sa.Float(), nullable=False),
        sa.Column("max_position_risk_pct", sa.Float(), nullable=False),
        sa.Column("max_symbol_notional_pct", sa.Float(), nullable=False),
        sa.Column("symbol_cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("openai_model", sa.String(length=100), nullable=False),
        sa.Column("broker_slug", broker_slug, nullable=False),
        sa.Column("broker_account_type", sa.String(length=40), nullable=False),
        sa.Column("broker_venue", sa.String(length=80), nullable=False),
        sa.Column("broker_timezone", sa.String(length=80), nullable=False),
        sa.Column("broker_base_currency", sa.String(length=12), nullable=False),
        sa.Column("broker_permissions", sa.JSON(), nullable=False),
        sa.Column("trading_pattern", trading_pattern, nullable=True),
        sa.Column("instrument_class", instrument_class, nullable=True),
        sa.Column("strategy_family", strategy_family, nullable=True),
        sa.Column("risk_profile", risk_profile, nullable=True),
        sa.Column("market_universe", market_universe, nullable=True),
        sa.Column("profile_notes", sa.Text(), nullable=False),
        sa.Column("analysis_only_downgrade_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "watchlist_symbols",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlist_symbols_symbol", "watchlist_symbols", ["symbol"], unique=True)

    op.create_table(
        "operator_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("role", operator_role, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operator_sessions_email", "operator_sessions", ["email"], unique=False)
    op.create_index("ix_operator_sessions_expires_at", "operator_sessions", ["expires_at"], unique=False)

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("symbol", sa.String(length=12), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_runs_symbol", "agent_runs", ["symbol"], unique=False)

    op.create_table(
        "trade_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("symbol", sa.String(length=12), nullable=False),
        sa.Column("direction", order_intent, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("risk_notes", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_candidates_run_id", "trade_candidates", ["run_id"], unique=False)
    op.create_index("ix_trade_candidates_symbol", "trade_candidates", ["symbol"], unique=False)

    op.create_table(
        "execution_intents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("intent_type", execution_intent_type, nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("status", execution_intent_status, nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=True),
        sa.Column("direction", order_intent, nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("decision_payload", sa.JSON(), nullable=False),
        sa.Column("risk_payload", sa.JSON(), nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_run_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_execution_intents_source_run_id", "execution_intents", ["source_run_id"], unique=True)
    op.create_index("ix_execution_intents_status", "execution_intents", ["status"], unique=False)
    op.create_index("ix_execution_intents_symbol", "execution_intents", ["symbol"], unique=False)
    op.create_index("ix_execution_intents_idempotency_key", "execution_intents", ["idempotency_key"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("execution_intent_id", sa.String(length=36), sa.ForeignKey("execution_intents.id"), nullable=True),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("direction", order_intent, nullable=False),
        sa.Column("order_type", order_type, nullable=False),
        sa.Column("time_in_force", time_in_force, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), nullable=False),
        sa.Column("average_fill_price", sa.Float(), nullable=True),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("trailing_percent", sa.Float(), nullable=True),
        sa.Column("trailing_amount", sa.Float(), nullable=True),
        sa.Column("status", order_status, nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=False),
        sa.Column("broker_order_id", sa.String(length=100), nullable=True),
        sa.Column("parent_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("replaced_by_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_broker_update_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_order_id"),
    )
    op.create_index("ix_orders_execution_intent_id", "orders", ["execution_intent_id"], unique=False)
    op.create_index("ix_orders_symbol", "orders", ["symbol"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)
    op.create_index("ix_orders_client_order_id", "orders", ["client_order_id"], unique=True)
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"], unique=False)
    op.create_index("ix_orders_parent_order_id", "orders", ["parent_order_id"], unique=False)
    op.create_index("ix_orders_replaced_by_order_id", "orders", ["replaced_by_order_id"], unique=False)

    op.create_table(
        "order_state_transitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("from_status", order_status, nullable=True),
        sa.Column("to_status", order_status, nullable=False),
        sa.Column("transition_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("broker_event_id", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_order_state_transitions_order_id", "order_state_transitions", ["order_id"], unique=False)
    op.create_index("ix_order_state_transitions_symbol", "order_state_transitions", ["symbol"], unique=False)
    op.create_index("ix_order_state_transitions_to_status", "order_state_transitions", ["to_status"], unique=False)
    op.create_index("ix_order_state_transitions_transition_at", "order_state_transitions", ["transition_at"], unique=False)

    op.create_table(
        "order_fills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("broker_fill_id", sa.String(length=120), nullable=True),
        sa.Column("broker_order_id", sa.String(length=100), nullable=True),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("broker_fill_id"),
    )
    op.create_index("ix_order_fills_order_id", "order_fills", ["order_id"], unique=False)
    op.create_index("ix_order_fills_broker_order_id", "order_fills", ["broker_order_id"], unique=False)
    op.create_index("ix_order_fills_symbol", "order_fills", ["symbol"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_entry_price", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("unrealized_pl", sa.Float(), nullable=False),
        sa.Column("side", sa.String(length=12), nullable=False),
        sa.Column("broker_position_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_positions_symbol", "positions", ["symbol"], unique=True)
    op.create_index("ix_positions_broker_position_id", "positions", ["broker_position_id"], unique=False)

    op.create_table(
        "instrument_contracts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=48), nullable=False),
        sa.Column("instrument_class", instrument_class, nullable=False),
        sa.Column("underlying_symbol", sa.String(length=24), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("tick_size", sa.Float(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("contract_multiplier", sa.Float(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("strike_price", sa.Float(), nullable=True),
        sa.Column("option_right", option_right, nullable=True),
        sa.Column("shortable", sa.Boolean(), nullable=False),
        sa.Column("option_chain_available", sa.Boolean(), nullable=False),
        sa.Column("price_band_low", sa.Float(), nullable=True),
        sa.Column("price_band_high", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_instrument_contracts_symbol", "instrument_contracts", ["symbol"], unique=True)
    op.create_index("ix_instrument_contracts_instrument_class", "instrument_contracts", ["instrument_class"], unique=False)
    op.create_index("ix_instrument_contracts_underlying_symbol", "instrument_contracts", ["underlying_symbol"], unique=False)
    op.create_index("ix_instrument_contracts_expiry", "instrument_contracts", ["expiry"], unique=False)

    op.create_table(
        "reconciliation_mismatches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("broker_slug", broker_slug, nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=True),
        sa.Column("mismatch_type", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("local_reference", sa.String(length=120), nullable=True),
        sa.Column("broker_reference", sa.String(length=120), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reconciliation_mismatches_broker_slug", "reconciliation_mismatches", ["broker_slug"], unique=False)
    op.create_index("ix_reconciliation_mismatches_symbol", "reconciliation_mismatches", ["symbol"], unique=False)
    op.create_index("ix_reconciliation_mismatches_mismatch_type", "reconciliation_mismatches", ["mismatch_type"], unique=False)
    op.create_index("ix_reconciliation_mismatches_resolved", "reconciliation_mismatches", ["resolved"], unique=False)

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=12), nullable=True),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_events_symbol", "risk_events", ["symbol"], unique=False)
    op.create_index("ix_risk_events_code", "risk_events", ["code"], unique=False)

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("buying_power", sa.Float(), nullable=False),
        sa.Column("daily_pl", sa.Float(), nullable=False),
        sa.Column("exposure", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"], unique=False)


def downgrade() -> None:
    for table_name in (
        "audit_logs",
        "portfolio_snapshots",
        "risk_events",
        "reconciliation_mismatches",
        "instrument_contracts",
        "positions",
        "order_fills",
        "order_state_transitions",
        "orders",
        "execution_intents",
        "trade_candidates",
        "agent_runs",
        "operator_sessions",
        "watchlist_symbols",
        "bot_settings",
    ):
        op.drop_table(table_name)

    bind = op.get_bind()
    for enum_type in (
        option_right,
        order_status,
        time_in_force,
        order_type,
        execution_intent_type,
        execution_intent_status,
        order_intent,
        run_status,
        operator_role,
        market_universe,
        risk_profile,
        strategy_family,
        instrument_class,
        trading_pattern,
        broker_slug,
        trading_mode,
        bot_status,
    ):
        enum_type.drop(bind, checkfirst=True)
