# Risk Profile & Guardrails

This document outlines the risk management guardrails configured for the Delta Exchange Freqtrade bot.

## 1. Hard Limits (Config)

These are enforced by Freqtrade core.

*   **Max Open Trades**: `5` (Live), `5` (Dry-Run)
*   **Stake Amount**: `unlimited` (uses available balance ratio)
*   **Tradable Balance Ratio**: `0.99` (Leaves 1% buffer)
*   **Leverage**: `2.0` (Default, configured via .env or strategy)
*   **Order Types**: Limit entries/exits with Market fallback for emergencies.

## 2. Protections

Protections stop trading temporarily when risk conditions are met.

### Daily Loss Limit
*   **Mechanism**: Stops **all new entries** for the rest of the UTC day if realized loss exceeds threshold.
*   **Threshold**: 5% of reference capital (`max_daily_loss: 0.05`).
*   **Absolute Override**: Can be set via `max_daily_loss_abs`.
*   **Implementation**: `user_data/protections/daily_loss_limit.py`

### Cooldown Period
*   **Mechanism**: Prevents re-entry into a pair immediately after a trade.
*   **Duration**: 3-5 candles.

### Stoploss Guard (Live Only)
*   **Mechanism**: Stops trading if too many stoplosses are hit in a short period.
*   **Limit**: 3 stoplosses in 24 candles -> 12 candle timeout.

## 3. Market Safety

*   **Drift Detection**: Daily market refresh fails if >25% of pairs are removed.
*   **Schema Validation**: Symbols must match strict futures format `BASE/QUOTE:SETTLE`.
*   **Volume Filter**: Optional strict volume checks.

## 4. How to Tune

To adjust risk:
1.  Edit `user_data/configs/config.delta.live.json`.
2.  Update `protections` section.
3.  Restart bot: `docker compose restart`.

**Warning**: Increasing leverage or disabling protections significantly increases risk of liquidation.
