# Risk Profile & Guardrails

## Configuration Limits
- **Max Open Trades:** 10
- **Stake Amount:** 20 USDT (Live), Unlimited (Dry Run)
- **Leverage:** 2x (Default, verify in strategy)
- **Margin Mode:** Isolated

## Protections
- **CooldownPeriod:** 5 candles after exit.
- **MaxDrawdown:** Stop trading for 12 candles if 20% drawdown in 48 candles.
- **StoplossGuard:** Stop trading pair for 2 candles if 4 stoplosses in 24 candles.
- **LowProfitPairs:** Stop trading pair for 60 candles if 2 trades < 2% profit in 6 candles.

## Daily Loss Limit
- **Limit:** 5% of balance (Configurable via DAILY_LOSS_LIMIT_PCT env var).
- **Action:** Bot stops entering new trades for the day.

## Strategy Rules
- **Process Only New Candles:** Enforced (Anti-Repainting).
- **Entry/Exit Signals:** Audit logged.
- **Whitelist:** Strictly validated against exchange markets.
