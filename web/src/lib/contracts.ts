export type TradingMode = "paper" | "live";
export type BotStatus = "running" | "stopped";
export type RiskDecision = "approved" | "rejected";
export type OrderIntent = "buy" | "sell" | "hold";
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

export interface BotSettingsResponse {
  status: BotStatus;
  mode: TradingMode;
  kill_switch_enabled: boolean;
  scan_interval_minutes: number;
  consensus_threshold: number;
  max_open_positions: number;
  max_daily_loss_pct: number;
  max_position_risk_pct: number;
  max_symbol_notional_pct: number;
  symbol_cooldown_minutes: number;
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
}

export interface BotSettingsUpdatePayload {
  scan_interval_minutes: number;
  consensus_threshold: number;
  max_open_positions: number;
  max_daily_loss_pct: number;
  max_position_risk_pct: number;
  max_symbol_notional_pct: number;
  symbol_cooldown_minutes: number;
  openai_model: string;
  watchlist: string[];
  broker_settings: BrokerSettings;
  selected_for_analysis: TradingProfile;
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

export interface OrderResponse {
  id: number;
  symbol: string;
  mode: TradingMode;
  direction: OrderIntent;
  quantity: number;
  limit_price: number;
  stop_loss: number;
  take_profit: number;
  status: string;
  client_order_id: string;
  broker_order_id?: string | null;
  submitted_at?: string | null;
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
