# Risk Profile

This document outlines the risk management parameters configured for the Delta Exchange trading bot.

## Core Protections

The bot uses the following protections:

### 1. Cooldown Period
Prevents re-entry into a pair immediately after a trade closes.
- **Duration:** 5 minutes (default)

### 2. Stoploss Guard
Prevents entering trades if the market is moving too fast against the position (slippage protection).
- **Threshold:** 5% price movement within 1 minute (configurable)

### 3. Max Drawdown Protection
Stops trading completely if the account equity drops below a certain percentage within a timeframe.
- **Max Drawdown:** 20% (configurable)
- **Timeframe:** 1 day

### 4. Low Profit Pairs
Avoids trading pairs that consistently produce low profit or losses.
- **Lookback:** 6 trades
- **Min Profit:** 0.0%

### 5. Daily Loss Limit (Custom Protection)
A custom protection module located at `user_data/protections/daily_loss_limit.py` stops ALL trading for the rest of the day (UTC) if the realized loss exceeds a specific percentage of the account balance.

- **Trigger:** Realized PnL < -5% (default) of `dry_run_wallet` (dry-run) or `capital` (live).
- **Action:** Locks trading until 00:00 UTC next day.
- **Configuration:** Set `max_daily_loss` (e.g., 0.05 for 5%) in `config.delta.*.json`.

## Exchange Limits (Delta)

- **Leverage:** Max 2x (hard cap in config).
- **Margin Mode:** Isolated (prevents cross-contamination of margin).
- **Order Types:** Limit orders preferred for entry/exit to avoid slippage. Market orders only used for stoploss/emergency exit.
- **Pricing:** `last` price used for entry/exit signals.

## Operational Safety

- **Dry Run:** Always start with `dry_run=true` to verify strategy behavior.
- **Whitelist:** Only trade pairs from the validated `whitelist.delta.*.json`.
- **Drift Check:** Daily market validation ensures delisted pairs are removed automatically.
