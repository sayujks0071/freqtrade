# Delta Exchange Risk Profile

## Overview
This document outlines the risk guardrails configured for the Delta Exchange trading bot. These settings are enforced by the bot configuration and cannot be overridden by strategies.

## Execution Limits
| Parameter | Value | Description |
|---|---|---|
| **Max Open Trades** | 3 | Maximum number of concurrent open positions. |
| **Stake Amount** | Unlimited (99%) | Uses 99% of available balance, divided by max open trades. |
| **Leverage** | 2x | Maximum leverage allowed per trade. |
| **Order Type** | Limit | Strict limit orders for entry/exit. Market orders used only for emergency. |
| **Margin Mode** | Isolated | Risk is isolated to the position margin. |

## Protections
The following protections are active:

### 1. Cooldown Period
- **Duration**: 5 candles
- **Effect**: Prevents re-entry into the same pair immediately after a trade closes.

### 2. Max Drawdown
- **Max Drawdown**: 20%
- **Lookback**: 48 candles
- **Stop Duration**: 12 candles
- **Effect**: Stops trading a pair if it has drawn down > 20% in the last 48 candles.

### 3. Daily Loss Limit (Custom)
- **Max Daily Loss**: 5% (Sum of trade percentages)
- **Effect**: Stops **all trading** for the rest of the day (UTC) if the sum of closed trade returns exceeds -5%.
  - *Note*: This is calculated on trade ROI, not account balance. e.g., 5 trades with -1% ROI each triggers the stop. This is a conservative safety net.

## Strategy Constraints
- Strategies must inherit from `AuditedStrategyMixin`.
- Strategies must define `stoploss` and `minimal_roi`.
- Strategies cannot execute market orders directly (bot enforces limit).
- Strategies operate on closed candles only to prevent repainting.

## Monitoring
- **Logs**: All trade decisions are logged with `[AUDIT]` tags.
- **Reports**: A daily summary is generated at `user_data/reports/daily_summary_YYYY-MM-DD.md`.
- **Alerts**: Critical errors or protection triggers should be monitored via logs.

## Emergency Procedures
1. **Stop Bot**: `docker compose down`
2. **Close Positions**: Log in to Delta Exchange manually to close open positions if the bot fails.
3. **Review Logs**: Check `user_data/logs/freqtrade.log` for errors.
