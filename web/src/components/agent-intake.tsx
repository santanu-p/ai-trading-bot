"use client";

import type {
  BrokerCapability,
  BrokerSettings,
  BrokerSlug,
  InstrumentClass,
  MarketUniverse,
  RiskProfile,
  StrategyFamily,
  TradingPattern,
  TradingProfile
} from "@/lib/contracts";
import {
  brokerOptions,
  instrumentOptions,
  marketUniverseOptions,
  type ProfileOption,
  riskProfileOptions,
  strategyFamilyOptions,
  tradingPatternOptions
} from "@/lib/trading-profile";

type Props = {
  profile: TradingProfile;
  brokerSettings: BrokerSettings;
  brokerCapabilityMatrix: BrokerCapability[];
  onChange: <K extends keyof TradingProfile>(key: K, value: TradingProfile[K]) => void;
  onBrokerChange: <K extends keyof BrokerSettings>(key: K, value: BrokerSettings[K]) => void;
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

export function AgentIntake({
  profile,
  brokerSettings,
  brokerCapabilityMatrix,
  onChange,
  onBrokerChange,
  title,
  description
}: Props) {
  return (
    <section className="panel intake-panel">
      <div className="panel-heading">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      {renderChoiceGroup(
        "Which broker family should this bot align to?",
        brokerOptions,
        brokerSettings.broker,
        (value: BrokerSlug) => onBrokerChange("broker", value)
      )}

      <div className="settings-grid broker-grid">
        <label>
          Account type
          <input
            type="text"
            value={brokerSettings.account_type}
            onChange={(event) => onBrokerChange("account_type", event.target.value)}
          />
        </label>
        <label>
          Venue
          <input type="text" value={brokerSettings.venue} onChange={(event) => onBrokerChange("venue", event.target.value)} />
        </label>
        <label>
          Broker timezone
          <input
            type="text"
            value={brokerSettings.timezone}
            onChange={(event) => onBrokerChange("timezone", event.target.value)}
          />
        </label>
        <label>
          Base currency
          <input
            type="text"
            value={brokerSettings.base_currency}
            onChange={(event) => onBrokerChange("base_currency", event.target.value.toUpperCase())}
          />
        </label>
      </div>

      <label className="watchlist-field">
        Broker permissions
        <textarea
          value={brokerSettings.permissions.join(", ")}
          onChange={(event) =>
            onBrokerChange(
              "permissions",
              event.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
            )
          }
          placeholder="Example: paper, live, cash_equities"
        />
      </label>

      <div className="panel-heading compact">
        <h3>Broker capability matrix</h3>
      </div>
      <table className="data-table capability-table">
        <thead>
          <tr>
            <th>Capability</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {brokerCapabilityMatrix.map((capability) => (
            <tr key={capability.key}>
              <td className="capability-cell">
                <strong>{capability.label}</strong>
                <span>{capability.description}</span>
              </td>
              <td>
                <span className={capability.supported ? "tag-positive" : "tag-negative"}>
                  {capability.supported ? "Supported" : "Not supported"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

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
