# Risk Profile & Guardrails

This document outlines the risk configuration for the Delta Exchange Freqtrade bot.

## Hard Constraints
These limits are enforced by the configuration and custom protections.

### 1. Daily Loss Limit
- **Mechanism:** `DailyLossLimit` Protection (Custom Plugin).
- **Trigger:** If Realized Daily PnL < `limit` (default -5%).
- **Action:** Stops entering new trades for the rest of the day.
- **Config:** `user_data/protections/daily_loss_limit.py`.

### 2. Position Limits
- **Max Open Trades:** 3 (Configurable in `config.json`).
- **Stake Amount:** Fixed amount (e.g., 100 USDT) or dynamic ratio.
- **Leverage:** Defaults to low leverage (e.g., 1x-3x).

### 3. Market Safety (Schema Gatekeeper)
- **Whitelist Updates:** Blocked if drift > 25% or schema validation fails.
- **Volume Filter:** `STRICT_VOLUME=true` (env) can enforce min volume.
- **Symbol Check:** Must be valid futures format (`BASE/QUOTE:SETTLE`).

### 4. Execution Safety
- **Order Types:** Limit orders for Entry/Exit to avoid slippage.
- **Timeouts:** Unfilled limit orders are cancelled or converted to market after timeout.
- **Dry Run:** Default mode to prevent accidental real trading.

## How to Tune
To adjust risk parameters, edit `user_data/configs/config.delta.live.json`:

```json
"max_open_trades": 5,
"stake_amount": "unlimited",
"tradable_balance_ratio": 0.99,
```

To adjust protections:
```json
"protections": [
    {
        "method": "DailyLossLimit",
        "limit": -0.05,
        "stop_duration_candles": 200
    },
    {
        "method": "CooldownPeriod",
        "stop_duration_candles": 2
    }
]
```
