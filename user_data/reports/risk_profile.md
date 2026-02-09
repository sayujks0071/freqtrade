# Risk Profile and Guardrails

This document outlines the risk management settings and safety mechanisms configured for the Delta Exchange Freqtrade bot.

## 1. Trading Limits
* **Max Open Trades:** 5 (Configurable in `config.delta.*.json`)
* **Stake Amount:** 100 USDT (Configurable)
* **Leverage:** Implicitly 1x unless strategy overrides (Futures usually default to 1x isolated if not specified, but strategy handles leverage calls). *Note: DeltaSafeStrategy enforces 1x or 2x max.*
* **Margin Mode:** Isolated (Strictly enforced in config)

## 2. Pricing & Execution
* **Entry:** Limit orders only.
* **Exit:** Limit orders only.
* **Stoploss:** Market orders (on exchange disabled for safety against wicks, managed by bot).
* **Time In Force:** GTC (Good Till Cancelled) default.

## 3. Protections (Circuit Breakers)
Enabled in `config.delta.live.json`:

### CooldownPeriod
* **Trigger:** After a trade closes.
* **Action:** Stops entering *that specific pair* for 3 candles (e.g. 15 mins on 5m timeframe).
* **Purpose:** Prevent revenge trading or entering a choppy market immediately after exit.

### MaxDrawdown
* **Trigger:** If the bot realizes a drawdown > 20% within 48 candles (4 hours).
* **Action:** Stops **ALL** trading for 12 candles (1 hour).
* **Purpose:** catastrophic failure prevention.

### StoplossGuard
* **Trigger:** If 4 stoplosses are hit within 24 candles (2 hours) for a specific pair.
* **Action:** Locks that pair for 4 candles.
* **Purpose:** Avoid repeatedly buying a crashing asset.

### Daily Loss Limit (Custom)
* **Trigger:** If realized daily PnL drops below -5% (configurable in strategy).
* **Action:** Strategy `check_daily_loss_limit` returns True, preventing new entries for the rest of the UTC day.
* **Implementation:** `AuditedStrategyMixin.check_daily_loss_limit()`.

## 4. Market Data Safety
* **Whitelist Source:** Automatically generated from Delta API daily.
* **Drift Check:** If > 25% of pairs are removed/delisted, the update fails and alerts.
* **Volume Filter:** Low volume pairs are excluded (if `STRICT_VOLUME=true`).
* **Schema Validation:** Strict checks on symbol format (`BASE/QUOTE:SETTLE`) to prevent ordering on invalid pairs.

## 5. Strategy Code Safety
* **Audit:** All strategies must pass `tools/strategy_auditor.py` checks.
* **Requirements:**
    * Must inherit `AuditedStrategyMixin`.
    * Must log signals via `log_signal()`.
    * No `datetime.now()` (must use UTC).
    * No network calls or unsafe imports.
    * Must explicitly handle "closed candle" logic.

## How to Change Limits
1. Edit `user_data/configs/config.delta.live.json`.
2. Restart the container: `docker compose restart freqtrade`.
3. Verify logs: `docker compose logs -f freqtrade`.
