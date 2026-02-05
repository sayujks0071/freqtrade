# Risk Profile & Guardrails

This document outlines the risk management controls configured for this trading stack.

## Hard Limits (Config)

These are enforced by Freqtrade core and the configuration file (`user_data/configs/config.delta.live.json`).

| Parameter | Value | Description |
|---|---|---|
| `max_open_trades` | **5** | Maximum concurrent open trades. |
| `stake_amount` | **20 USDT** | Fixed stake per trade. |
| `tradable_balance_ratio` | **0.99** | Use 99% of wallet balance max (safety buffer). |
| `stoploss` | **Strategy Defined** | Usually -10% or dynamic. |
| `leverage` | **2x (Implied)** | Strategies should set leverage roughly 2x-3x max. |

## Protections (Circuit Breakers)

These stop trading temporarily when triggered.

### 1. Daily Loss Limit
- **Trigger:** Realized daily profit < **-5%**
- **Action:** Stops all NEW entries for the rest of the UTC day.
- **Reset:** Automatically resets at 00:00 UTC.

### 2. Max Drawdown
- **Trigger:** Drawdown > **20%** over **48 candles**.
- **Action:** Stops trading for **12 candles**.

### 3. Cooldown Period
- **Trigger:** Any trade exit.
- **Action:** Waits **5 candles** before re-entering the SAME pair.

## Whitelist Safety

- **Market Drift:** Whitelist updates fail if >25% of pairs are removed (likely bad data).
- **Volume Filter:** Low volume pairs are warned/excluded.
- **Schema Validation:** Bad API dumps are rejected.

## How to Change

1. **Edit Config:** Modify `user_data/configs/config.delta.live.json`.
2. **Restart:** `docker compose restart freqtrade`.

**⚠️ WARNING:** Increasing limits increases risk of ruin. Test changes in Dry-Run first.
