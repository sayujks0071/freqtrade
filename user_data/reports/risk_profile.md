# Risk Profile & Guardrails

This document outlines the risk management configuration for the Delta Exchange bot.

## Hard Limits (Config Level)

These limits are enforced by the bot core and cannot be overridden by strategies.

- **Max Open Trades**: `5` (Configurable via `MAX_OPEN_TRADES` env)
- **Stake Amount**: `20` USDT (Configurable via `STAKE_AMOUNT` env)
- **Leverage**: `2x` (Configurable via `LEVERAGE` env)
- **Trading Mode**: `Futures Isolated`
- **Margin Mode**: `Isolated` (Risk is limited to allocated margin per position)

## Protections (Circuit Breakers)

The bot implements several layers of protections to stop trading during adverse conditions.

### 1. Daily Loss Limit
**Stops trading for the rest of the day (UTC)** if realized losses exceed a threshold.
- **Threshold**: `5%` of capital (default).
- **Behavior**: Locks all pairs until 00:00 UTC next day.
- **Configuration**: `max_daily_loss` in `config.delta.*.json`.

### 2. Max Drawdown Protection
**Stops trading temporarily** if a drawdown occurs within a short period.
- **Limit**: `20%` drawdown within 48 candles.
- **Action**: Stop trading for 12 candles.
- **Purpose**: Prevent rapid account depletion during market crashes.

### 3. Cooldown Period
**Enforces a pause** after a trade exits.
- **Duration**: `5` candles.
- **Purpose**: Prevent revenge trading or re-entering too quickly.

### 4. Stoploss Guard
**Stops trading a specific pair** if it hits stoploss too frequently.
- **Limit**: `4` stoplosses within 24 candles.
- **Action**: Lock pair for 12 candles.

## Execution Guardrails

### Entry & Exit Logic
- **Order Type**: `Limit` orders for entries and exits.
- **Time in Force**: `GTC` (Good Till Cancelled) or strategy defined.
- **Timeout**: If a limit order is not filled within `entry_pricing.check_depth_of_market` logic or timeout, it is cancelled (or replaced with market if configured).
- **Price Check**: `entry_pricing.check_depth_of_market` checks if the order book has liquidity.

### Slippage Control
- **Market Orders**: Only used for `stoploss` and `emergency_exit`.
- **Limit Orders**: Placed at `same` side or `other` side depending on `entry_pricing`.

## How to Tune

### Environment Variables (.env)
- `MAX_OPEN_TRADES`: Increase/decrease concurrency.
- `STAKE_AMOUNT`: Position size.
- `LEVERAGE`: Risk multiplier.

### Configuration Files
- `user_data/configs/config.delta.live.json`: Live settings.
- `user_data/protections/daily_loss_limit.py`: Custom logic for daily loss.

## Drift Detection
- The `update_markets_and_whitelist.sh` script runs daily to check for delisted pairs.
- If >25% of pairs are removed, the update is blocked to prevent accidents.
