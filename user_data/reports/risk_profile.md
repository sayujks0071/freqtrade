# Risk Profile & Guardrails

## Overview
This trading stack is configured with strict risk controls to ensure capital preservation and safe execution on Delta Exchange.

## Core Config Guardrails
- **Max Open Trades**: Hard cap on simultaneous positions.
- **Stake Amount**: Fixed amount per trade (or % of balance).
- **Leverage**: Capped at 2x by default.
- **Stoploss**: Hard stoploss required for all strategies.
- **Order Types**: Limit orders preferred for entry/exit to avoid slippage.

## Protections
Active protections in `config.json` (must be enabled in `protections` list):
1. **CooldownPeriod**: Prevents re-entering a pair immediately after exit.
2. **StoplossGuard**: Stops trading a pair if it hits stoploss too frequently.
3. **MaxDrawdown**: Stops all trading if account drawdown exceeds threshold.
4. **DailyLossLimit** (Custom): Stops all trading for the day if realized daily loss exceeds X%.
   - **Note**: The percentage is calculated based on `available_capital` (if set in config) or `dry_run_wallet` (fallback). For live trading, ensure `available_capital` in `config.delta.live.json` reflects your deployed capital to make the percentage accurate, or use `max_daily_loss_abs` (absolute value) for precise control.

## Daily Limits
- **Max Removal Ratio**: {MAX_REMOVAL_RATIO} (fails market update if too many pairs removed).
- **Min Markets**: {MIN_MARKETS} (fails if exchange dump is too small).

## Execution Safety
- **Strict Whitelist**: Only trade pairs present in the validated daily dump.
- **Drift Detection**: Any change in market schema or large delisting triggers alerts (PR checks).
- **Dry Run First**: Always test changes in dry-run mode before live.

## How to Tune
To adjust risk parameters:
1. Edit `user_data/configs/config.delta.live.json` or `.dryrun.json`.
2. Update `protections` section.
3. Restart the bot.

**Warning**: Increasing leverage or stake amount increases risk of liquidation. Always keep `tradable_balance_ratio` < 1.0 to leave margin for fees and funding.
