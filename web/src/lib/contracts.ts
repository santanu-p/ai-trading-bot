export type TradingMode = "paper" | "live";
export type BotStatus = "running" | "stopped";
export type RiskDecision = "approved" | "rejected";
export type OrderIntent = "buy" | "sell" | "hold";
export type OrderType = "market" | "limit" | "stop_market" | "stop_limit" | "bracket" | "oco" | "trailing_stop";
export type TimeInForce = "day" | "gtc" | "ioc" | "fok";
export type OrderStatus =
  | "new"
  | "accepted"
  | "pending_trigger"
  | "partially_filled"
  | "filled"
  | "canceled"
  | "expired"
  | "replaced"
  | "rejected"
  | "suspended";
export type BrokerSlug = "alpaca";
export type TradingPattern =
  | "scalping"
  | "intraday"
  | "delivery"
  | "swing"
  | "positional"
  | "btst_stbt"
  | "futures_directional"
  | "futures_hedged"
  | "options_buying"
  | "options_selling";
export type InstrumentClass = "cash_equity" | "futures" | "options" | "mixed";
export type StrategyFamily =
  | "momentum_breakout"
  | "trend_following"
  | "mean_reversion"
  | "event_driven"
  | "price_action"
  | "option_premium_decay"
  | "hedged_carry"
  | "multi_factor";
export type RiskProfile = "conservative" | "balanced" | "aggressive";
export type MarketUniverse = "large_cap" | "large_mid_cap" | "index_only" | "sector_focus" | "custom_watchlist";
export type ExecutionSupportStatus =
  | "complete_agent_intake_first"
  | "analysis_only_for_selected_broker"
  | "broker_execution_supported";
export type OperatorRole = "reviewer" | "operator" | "admin" | "system";
export type ExecutionIntentStatus =
  | "pending_approval"
  | "approved"
  | "executing"
  | "executed"
  | "rejected"
  | "blocked"
  | "failed"
  | "canceled";
export type ExecutionIntentType = "trade" | "flatten_all" | "broker_kill";

export interface TradingProfile {
  trading_pattern: TradingPattern | null;
  instrument_class: InstrumentClass | null;
  strategy_family: StrategyFamily | null;
  risk_profile: RiskProfile | null;
  market_universe: MarketUniverse | null;
  profile_notes: string;
}

export interface BrokerSettings {
  broker: BrokerSlug;
  account_type: string;
  venue: string;
  timezone: string;
  base_currency: string;
  permissions: string[];
}

export interface BrokerCapability {
  key: string;
  label: string;
  description: string;
  supported: boolean;
}

export interface MarketSessionResponse {
  venue: string;
  timezone: string;
  status: string;
  reason?: string | null;
  is_half_day: boolean;
  can_scan: boolean;
  can_submit_orders: boolean;
  should_flatten_positions: boolean;
  session_opens_at?: string | null;
  session_closes_at?: string | null;
  next_session_opens_at?: string | null;
}

export interface BotSettingsResponse {
  status: BotStatus;
  mode: TradingMode;
  kill_switch_enabled: boolean;
  live_enabled: boolean;
  live_trading_env_allowed: boolean;
  scan_interval_minutes: number;
  consensus_threshold: number;
  max_open_positions: number;
  max_daily_loss_pct: number;
  max_position_risk_pct: number;
  max_symbol_notional_pct: number;
  max_gross_exposure_pct: number;
  max_sector_exposure_pct: number;
  max_correlation_exposure_pct: number;
  max_event_cluster_positions: number;
  volatility_target_pct: number;
  atr_sizing_multiplier: number;
  equity_curve_throttle_start_pct: number;
  equity_curve_throttle_min_scale: number;
  intraday_drawdown_pause_pct: number;
  loss_streak_reduction_threshold: number;
  loss_streak_size_scale: number;
  execution_failure_review_threshold: number;
  severe_anomaly_kill_switch_threshold: number;
  symbol_cooldown_minutes: number;
  symbol_cooldown_profit_minutes: number;
  symbol_cooldown_stopout_minutes: number;
  symbol_cooldown_event_minutes: number;
  symbol_cooldown_whipsaw_minutes: number;
  openai_model: string;
  watchlist: string[];
  broker_settings: BrokerSettings;
  broker_capability_matrix: BrokerCapability[];
  selected_for_analysis: TradingProfile;
  supported_for_execution: TradingProfile | null;
  strategy_profile_completed: boolean;
  execution_support_status: ExecutionSupportStatus;
  live_start_allowed: boolean;
  analysis_only_downgrade_reason?: string | null;
  market_session: MarketSessionResponse;
}

export interface BotSettingsUpdatePayload {
  scan_interval_minutes: number;
  consensus_threshold: number;
  max_open_positions: number;
  max_daily_loss_pct: number;
  max_position_risk_pct: number;
  max_symbol_notional_pct: number;
  max_gross_exposure_pct: number;
  max_sector_exposure_pct: number;
  max_correlation_exposure_pct: number;
  max_event_cluster_positions: number;
  volatility_target_pct: number;
  atr_sizing_multiplier: number;
  equity_curve_throttle_start_pct: number;
  equity_curve_throttle_min_scale: number;
  intraday_drawdown_pause_pct: number;
  loss_streak_reduction_threshold: number;
  loss_streak_size_scale: number;
  execution_failure_review_threshold: number;
  severe_anomaly_kill_switch_threshold: number;
  symbol_cooldown_minutes: number;
  symbol_cooldown_profit_minutes: number;
  symbol_cooldown_stopout_minutes: number;
  symbol_cooldown_event_minutes: number;
  symbol_cooldown_whipsaw_minutes: number;
  openai_model: string;
  watchlist: string[];
  broker_settings: BrokerSettings;
  selected_for_analysis: TradingProfile;
}

export interface LoginResponse {
  authenticated: boolean;
  email: string;
  role: OperatorRole;
  expires_at: string;
  session_id: string;
}

export interface SessionResponse {
  session_id: string;
  email: string;
  role: OperatorRole;
  expires_at: string;
  current: boolean;
  user_agent?: string | null;
  ip_address?: string | null;
  last_seen_at?: string | null;
  revoked_at?: string | null;
}

export interface CommitteeDecision {
  symbol: string;
  direction: OrderIntent;
  confidence: number;
  entry: number;
  stop_loss: number;
  take_profit: number;
  time_horizon: string;
  status: RiskDecision;
  thesis: string;
  reject_reason?: string | null;
  market_vote?: string | null;
  news_vote?: string | null;
  risk_notes: string[];
}

export interface RunResponse {
  id: string;
  symbol: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  decision_payload?: Record<string, unknown> | null;
}

export interface ExecutionIntentResponse {
  id: string;
  source_run_id?: string | null;
  intent_type: ExecutionIntentType;
  mode: TradingMode;
  status: ExecutionIntentStatus;
  symbol?: string | null;
  direction?: OrderIntent | null;
  quantity?: number | null;
  limit_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  requires_human_approval: boolean;
  block_reason?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  executed_at?: string | null;
  failed_at?: string | null;
  last_error?: string | null;
  created_at: string;
}

export interface OrderResponse {
  id: number;
  symbol: string;
  mode: TradingMode;
  direction: OrderIntent;
  order_type: OrderType;
  time_in_force: TimeInForce;
  quantity: number;
  filled_quantity: number;
  average_fill_price?: number | null;
  limit_price?: number | null;
  stop_loss?: number | null;
  stop_price?: number | null;
  take_profit?: number | null;
  trailing_percent?: number | null;
  trailing_amount?: number | null;
  status: OrderStatus;
  status_reason?: string | null;
  client_order_id: string;
  broker_order_id?: string | null;
  parent_order_id?: number | null;
  replaced_by_order_id?: number | null;
  submitted_at?: string | null;
  last_broker_update_at?: string | null;
}

export interface OrderTransitionResponse {
  id: number;
  order_id: number;
  symbol: string;
  from_status?: OrderStatus | null;
  to_status: OrderStatus;
  transition_at: string;
  source: string;
  broker_event_id?: string | null;
  message: string;
  payload: Record<string, unknown>;
}

export interface OrderFillResponse {
  id: number;
  order_id: number;
  broker_fill_id?: string | null;
  broker_order_id?: string | null;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  fee: number;
  filled_at: string;
  payload: Record<string, unknown>;
}

export interface PositionResponse {
  id: number;
  symbol: string;
  quantity: number;
  average_entry_price: number;
  market_value: number;
  unrealized_pl: number;
  side: string;
}

export interface RiskEventResponse {
  id: number;
  symbol?: string | null;
  severity: string;
  code: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface MetricCounterResponse {
  name: string;
  value: number;
  tags: Record<string, string>;
}

export interface MetricLatencyResponse {
  name: string;
  samples: number;
  avg_ms: number;
  p95_ms: number;
  max_ms: number;
  tags: Record<string, string>;
}

export interface PerformanceSummaryResponse {
  window_minutes: number;
  total_trade_candidates: number;
  rejected_trade_candidates: number;
  rejection_rate: number;
  malformed_events: number;
  scan_failures: number;
  kill_switch_enabled: boolean;
  live_enabled: boolean;
  mode: TradingMode;
  counters: MetricCounterResponse[];
  latencies: MetricLatencyResponse[];
}

export interface ExecutionQualitySampleResponse {
  id: number;
  order_id: number;
  symbol: string;
  broker_slug: BrokerSlug;
  venue: string;
  order_type: OrderType;
  side: OrderIntent;
  outcome_status: OrderStatus;
  quantity: number;
  filled_quantity: number;
  fill_ratio: number;
  intended_price?: number | null;
  realized_price?: number | null;
  expected_slippage_bps?: number | null;
  realized_slippage_bps?: number | null;
  expected_spread_bps?: number | null;
  spread_cost: number;
  notional: number;
  time_to_fill_seconds?: number | null;
  aggressiveness?: string | null;
  quality_score: number;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ExecutionQualitySummaryResponse {
  dimension: string;
  key: string;
  sample_count: number;
  filled_count: number;
  cancel_rate: number;
  reject_rate: number;
  avg_expected_slippage_bps: number;
  avg_realized_slippage_bps: number;
  avg_spread_cost: number;
  avg_time_to_fill_seconds: number;
  avg_fill_ratio: number;
  avg_quality_score: number;
}

export interface AuditLogResponse {
  id: number;
  action: string;
  actor: string;
  actor_role: string;
  session_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ReconciliationMismatchResponse {
  id: number;
  broker_slug: BrokerSlug;
  symbol?: string | null;
  mismatch_type: string;
  severity: string;
  local_reference?: string | null;
  broker_reference?: string | null;
  details: Record<string, unknown>;
  resolved: boolean;
  resolved_at?: string | null;
  created_at: string;
}

export interface LiveEnablePrepareResponse {
  approval_code: string;
  expires_at: string;
  live_trading_env_allowed: boolean;
}

export interface ActionResponse {
  accepted: boolean;
  detail: string;
}

export interface BacktestRequestPayload {
  symbols: string[];
  start: string;
  end: string;
  interval_minutes: number;
  initial_equity: number;
  slippage_bps: number;
  commission_per_share: number;
  fill_delay_bars: number;
  reject_probability: number;
  max_holding_bars: number;
  random_seed: number;
}

export interface BacktestResponse {
  accepted: boolean;
  task_id: string;
  report_id: string;
}

export interface BacktestSummaryResponse {
  id: string;
  task_id?: string | null;
  status: string;
  symbols: string[];
  start_at: string;
  end_at: string;
  interval_minutes: number;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  total_trades: number;
  rejected_orders: number;
  final_equity: number;
  total_return_pct: number;
  win_rate: number;
  expectancy: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  turnover: number;
  avg_exposure_pct: number;
  max_exposure_pct: number;
  error_message?: string | null;
}

export interface BacktestTradeResponse {
  id: number;
  symbol: string;
  status: string;
  regime: string;
  signal_at: string;
  entry_at?: string | null;
  exit_at?: string | null;
  quantity: number;
  holding_bars: number;
  entry_price?: number | null;
  exit_price?: number | null;
  gross_pnl: number;
  net_pnl: number;
  return_pct: number;
  commission_paid: number;
  slippage_paid: number;
  notes: string[];
}

export interface BacktestDetailResponse extends BacktestSummaryResponse {
  metrics: Record<string, unknown>;
  walk_forward: Record<string, unknown>[];
  regime_breakdown: Record<string, unknown>[];
  equity_curve: Record<string, unknown>[];
  symbol_breakdown: Record<string, unknown>[];
  trades: BacktestTradeResponse[];
}
