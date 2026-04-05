import type {
  ExecutionSupportStatus,
  InstrumentClass,
  MarketUniverse,
  RiskProfile,
  StrategyFamily,
  TradingPattern,
  TradingProfile
} from "@/lib/contracts";

export type ProfileOption<T extends string> = {
  value: T;
  label: string;
  description: string;
  supportedByCurrentExecutor?: boolean;
};

export const tradingPatternOptions: ProfileOption<TradingPattern>[] = [
  { value: "scalping", label: "Scalping", description: "Very short holding windows and tight entry confirmation.", supportedByCurrentExecutor: true },
  { value: "intraday", label: "Intraday", description: "Open and close trades within the same session.", supportedByCurrentExecutor: true },
  { value: "delivery", label: "Delivery", description: "Cash-equity delivery style with longer holding intent.", supportedByCurrentExecutor: true },
  { value: "swing", label: "Swing", description: "Multi-day trades driven by trend and continuation setups.", supportedByCurrentExecutor: true },
  { value: "positional", label: "Positional", description: "Longer holding windows with broader trend alignment.", supportedByCurrentExecutor: true },
  { value: "btst_stbt", label: "BTST / STBT", description: "Carry overnight with gap or continuation expectations.", supportedByCurrentExecutor: true },
  { value: "futures_directional", label: "Futures Directional", description: "Directional futures analysis and trade selection.", supportedByCurrentExecutor: false },
  { value: "futures_hedged", label: "Futures Hedged", description: "Hedged futures setups with spread or protection logic.", supportedByCurrentExecutor: false },
  { value: "options_buying", label: "Options Buying", description: "Directional options entries with premium paid.", supportedByCurrentExecutor: false },
  { value: "options_selling", label: "Options Selling", description: "Premium selling and decay-focused setups.", supportedByCurrentExecutor: false }
];

export const instrumentOptions: ProfileOption<InstrumentClass>[] = [
  { value: "cash_equity", label: "Cash Equity", description: "Stocks or ETFs in the cash market.", supportedByCurrentExecutor: true },
  { value: "futures", label: "Futures", description: "Futures contracts and leveraged directional exposure.", supportedByCurrentExecutor: false },
  { value: "options", label: "Options", description: "Calls, puts, or spread-style option structures.", supportedByCurrentExecutor: false },
  { value: "mixed", label: "Mixed", description: "Use multiple instrument classes in the research workflow.", supportedByCurrentExecutor: false }
];

export const strategyFamilyOptions: ProfileOption<StrategyFamily>[] = [
  { value: "momentum_breakout", label: "Momentum Breakout", description: "Exploit clean range breaks and follow-through." },
  { value: "trend_following", label: "Trend Following", description: "Stay aligned with higher-timeframe directional bias." },
  { value: "mean_reversion", label: "Mean Reversion", description: "Fade stretched moves back toward balance." },
  { value: "event_driven", label: "Event Driven", description: "Trade catalysts, news, and scheduled events." },
  { value: "price_action", label: "Price Action", description: "Prioritize structure, levels, and clean tape behavior." },
  { value: "option_premium_decay", label: "Option Decay", description: "Bias toward theta-driven setups and premium capture." },
  { value: "hedged_carry", label: "Hedged Carry", description: "Pair directional views with hedges or carry structures." },
  { value: "multi_factor", label: "Multi Factor", description: "Blend multiple signals instead of a single playbook." }
];

export const riskProfileOptions: ProfileOption<RiskProfile>[] = [
  { value: "conservative", label: "Conservative", description: "Tighter filters, lower aggression, fewer trades." },
  { value: "balanced", label: "Balanced", description: "Moderate selectivity with standard risk budgets." },
  { value: "aggressive", label: "Aggressive", description: "More setups, faster action, broader tolerance for variance." }
];

export const marketUniverseOptions: ProfileOption<MarketUniverse>[] = [
  { value: "large_cap", label: "Large Cap", description: "Focus on liquid large-cap names." },
  { value: "large_mid_cap", label: "Large + Mid Cap", description: "Include liquid mid-caps for broader opportunity." },
  { value: "index_only", label: "Index Focus", description: "Favor index-linked names or broad market leaders." },
  { value: "sector_focus", label: "Sector Focus", description: "Concentrate on selected sectors or themes." },
  { value: "custom_watchlist", label: "Custom Watchlist", description: "Use the watchlist you define in settings." }
];

export const executionSupportCopy: Record<
  ExecutionSupportStatus,
  {
    title: string;
    description: string;
  }
> = {
  complete_agent_intake_first: {
    title: "Agent intake required",
    description: "The agents will not run until you choose a trading pattern, instruments, strategy family, risk profile, and market universe."
  },
  analysis_only_for_selected_instrument: {
    title: "Analysis-only instrument selection",
    description: "The agents will adapt to your selected instrument class, but the current Alpaca executor only places cash-equity orders."
  },
  analysis_only_for_selected_pattern: {
    title: "Analysis-only pattern selection",
    description: "The agents will analyze the selected F&O pattern, but broker execution remains disabled for that pattern in the current build."
  },
  broker_execution_supported: {
    title: "Broker execution supported",
    description: "The selected pattern maps to the current Alpaca cash-equity executor."
  }
};

export function optionLabel<T extends string>(options: ProfileOption<T>[], value: T | null | undefined) {
  return options.find((option) => option.value === value)?.label ?? "Not selected";
}

export const emptyTradingProfile: TradingProfile = {
  trading_pattern: null,
  instrument_class: null,
  strategy_family: null,
  risk_profile: null,
  market_universe: null,
  profile_notes: ""
};

