# Risk Profile & Guardrails

## Hard Limits
- **Max Open Trades**: 3 (Configurable in `config.delta.*.json`)
- **Max Leverage**: 2x (Recommended start, can be increased)
- **Margin Mode**: Isolated (Never Cross)
- **Stoploss**: Required by all strategies. Default -10% if not specified.

## Daily Loss Limit
- **Limit**: -5% of daily starting balance (default).
- **Action**: Stop entering new trades for the rest of the UTC day.
- **Implementation**: `AuditedStrategyMixin` checks realized PnL of closed trades today.

## Market Validation
- **Min Markets**: 20
- **Max Drift**: 25% removal allowed per day.
- **Strict Volume**: Optional check for > $1000 volume.

## Execution Safety
- **Order Types**: Limit orders preferred.
- **Timeouts**: Entries expire after 5 minutes if not filled.
- **Drift Check**: Whitelist updates blocked if too many pairs removed.

## How to Tune
1. **Leverage**: Edit `stake_amount` and strategy leverage callbacks.
2. **Daily Limit**: Set `DAILY_LOSS_LIMIT_PCT` in `.env` (e.g. -0.10 for 10%).
3. **Whitelist**: Adjust `FILTER_MODE` in `.env`.
