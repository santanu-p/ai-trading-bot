"use client";

import type { InstrumentClass, MarketUniverse, RiskProfile, StrategyFamily, TradingPattern, TradingProfile } from "@/lib/contracts";
import {
  instrumentOptions,
  marketUniverseOptions,
  type ProfileOption,
  riskProfileOptions,
  strategyFamilyOptions,
  tradingPatternOptions
} from "@/lib/trading-profile";

type Props = {
  profile: TradingProfile;
  onChange: <K extends keyof TradingProfile>(key: K, value: TradingProfile[K]) => void;
  title: string;
  description: string;
};

function renderChoiceGroup<T extends string>(
  title: string,
  options: ProfileOption<T>[],
  selectedValue: T | null,
  onChange: (value: T) => void
) {
  return (
    <div className="intake-group">
      <div className="panel-heading compact">
        <h3>{title}</h3>
      </div>
      <div className="choice-grid">
        {options.map((option) => (
          <button
            key={option.value}
            className={selectedValue === option.value ? "choice-card active" : "choice-card"}
            type="button"
            onClick={() => onChange(option.value)}
          >
            <span className="choice-title-row">
              <strong>{option.label}</strong>
              {option.supportedByCurrentExecutor === false ? <em>Analysis only</em> : null}
            </span>
            <span>{option.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function AgentIntake({ profile, onChange, title, description }: Props) {
  return (
    <section className="panel intake-panel">
      <div className="panel-heading">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      {renderChoiceGroup(
        "Which trading pattern should the agents follow?",
        tradingPatternOptions,
        profile.trading_pattern,
        (value: TradingPattern) => onChange("trading_pattern", value)
      )}

      {renderChoiceGroup(
        "Which instruments should they prioritize?",
        instrumentOptions,
        profile.instrument_class,
        (value: InstrumentClass) => onChange("instrument_class", value)
      )}

      {renderChoiceGroup(
        "Which strategy family should lead the research?",
        strategyFamilyOptions,
        profile.strategy_family,
        (value: StrategyFamily) => onChange("strategy_family", value)
      )}

      {renderChoiceGroup(
        "How aggressive should the risk profile be?",
        riskProfileOptions,
        profile.risk_profile,
        (value: RiskProfile) => onChange("risk_profile", value)
      )}

      {renderChoiceGroup(
        "What market universe should they focus on?",
        marketUniverseOptions,
        profile.market_universe,
        (value: MarketUniverse) => onChange("market_universe", value)
      )}

      <label className="watchlist-field">
        Extra instructions for the agents
        <textarea
          value={profile.profile_notes}
          onChange={(event) => onChange("profile_notes", event.target.value)}
          placeholder="Example: focus on liquid names only, avoid trading near earnings, prefer opening-range continuation setups."
        />
      </label>
    </section>
  );
}
