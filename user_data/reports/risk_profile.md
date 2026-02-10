# Risk Profile & Guardrails

This document outlines the risk management configuration for the Delta Exchange Freqtrade stack.

## Hard Limits (Config)

These limits are enforced by the bot engine and cannot be overridden by strategies easily.

| Parameter | Value | Description |
|---|---|---|
| **Max Open Trades** | `5` | Maximum number of concurrent positions. |
| **Stake Amount** | `20 USDT` | Fixed stake per trade. |
| **Tradable Balance**| `0.99` | 99% of wallet balance is available for trading. |
| **Margin Mode** | `isolated` | Isolated margin to prevent cross-contamination. |
| **Trading Mode** | `futures` | Derivatives trading. |

## Strategy Protections (Config)

These protections stop trading or manage exits based on risk metrics.

| Protection | Setting | Description |
|---|---|---|
| **Daily Loss Limit** | `5%` | Stops entering new trades if daily realized loss exceeds 5% of balance. |
| **Max Drawdown** | `20%` | Stops trading for 12 candles if drawdown hits 20% (lookback 48 candles). |
| **Cooldown** | `5 candles` | Waits 5 candles after a trade exit before re-entering the same pair. |

## Strategy-Level Guardrails (Code)

These are enforced by `AuditedStrategyMixin` and `DeltaSafeStrategy`.

- **Leverage Cap**: Default `2x` (Must be implemented in strategy `leverage` method).
- **Audit Logging**: Every signal is logged with timestamp and reason.
- **Whitelist Check**: Strategies only trade pairs in the authorized whitelist.
- **Daily Loss Check (Redundant)**: Strategy explicitly checks daily PnL before confirming entry, adding a second layer of safety.

## How to Tune Safely

1. **Edit Config**: Modify `user_data/configs/config.delta.live.json` to change hard limits.
   - *Warning*: Increasing `max_open_trades` or `stake_amount` increases risk exposure.
2. **Edit Strategy**: Modify `DeltaSafeStrategy.py` to change `stoploss` or `leverage`.
   - *Warning*: Leverage > 3x is high risk for crypto.
3. **Environment**:
   - `MAX_REMOVAL_RATIO`: Controls how much the market structure can change before halting updates. Default `0.25`.
   - `STRICT_VOLUME`: Enable to reject low-volume pairs.

## Emergency Procedures

- **Stop Bot**: `docker compose down`
- **Force Exit**: `docker compose run --rm freqtrade forceexit --config user_data/configs/config.delta.live.json`
