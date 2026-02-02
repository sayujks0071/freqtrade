# Risk Profile & Guardrails

This document outlines the risk management configuration for the Delta Exchange Freqtrade stack.

## Hard Constraints
These settings are defined in `config.delta.live.json` and `.env` and serve as hard stops.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_open_trades` | 5 | Maximum concurrent positions. |
| `stake_amount` | "unlimited" | Uses `tradable_balance_ratio`. |
| `tradable_balance_ratio` | 0.99 | Percentage of wallet to use. |
| `leverage` | Strategy-defined (Default 2x) | Leverage used for futures. |

## Protections
Protections are plugins that stop trading under adverse conditions.

### Daily Loss Limit
- **File**: `user_data/protections/daily_loss_limit.py`
- **Trigger**: Realized Daily PnL < `DAILY_LOSS_LIMIT` (Default: -5%)
- **Action**: Stops **new entries** for the remainder of the UTC day.

### CooldownPeriod
- **Trigger**: After a trade exit.
- **Action**: Enforces a wait time before re-entering the same pair.

### StoplossGuard
- **Trigger**: If `stoploss_on_exchange` fails or is not supported.
- **Action**: Freqtrade manages stoploss via API.

## Market Data Safety
- **Schema Validation**: Markets dump is validated daily.
- **Drift Detection**: Updates rejected if >25% of pairs are delisted (`MAX_REMOVAL_RATIO`).
- **Volume Filter**: `STRICT_VOLUME` (optional) filters low liquidity pairs.

## How to Change Limits
1. Edit `.env` for simple numeric limits.
2. Edit `user_data/configs/config.delta.live.json` for structural changes.
3. Restart the bot (`docker compose restart`).

## Emergency Procedures
1. **Stop Bot**: `docker compose down`
2. **Close Positions**: Log in to Delta Exchange manually to manage open positions.
