# Risk Profile: Delta Exchange

## Overview

This document defines the risk limits and guardrails for the Freqtrade deployment on Delta Exchange.
These settings are enforced via configuration and strategy logic.

## Hard Limits

| Limit | Value | Config Source | Notes |
|---|---|---|---|
| **Max Open Trades** | `5` | `config.delta.live.json` | Conservative limit to prevent overexposure. |
| **Stake Amount** | `20 USDT` | `config.delta.live.json` | Fixed stake per trade. |
| **Leverage** | `1x - 3x` | Strategy / Exchange | Default is 1x. Max allowed is 3x. |
| **Stoploss** | `-10%` | Strategy | Hard stoploss. |
| **Daily Loss Limit** | `-5%` | `AuditedStrategyMixin` | Stops new entries if realized PnL < -5% for the day. |

## Protections

- **CooldownPeriod**: 5 minutes after a trade exits.
- **StoplossGuard**: Enabled to prevent stoploss hunting (if configured).
- **MaxDrawdown**: Bot stops if drawdown exceeds 20%.

## Execution Safety

- **Order Types**: Limit orders for Entry/Exit. Market orders for Stoploss.
- **Time in Force**: GTC (Good Till Cancelled).
- **Slippage**: Strict tolerance.

## Monitoring

- **Audit Logs**: Every trade signal is logged with reason and indicators.
- **Daily Report**: Summary of PnL and exposure generated daily.
- **Drift Detection**: Market schema validation runs daily to detect removed pairs or format changes.

## Procedures

### Changing Risk Limits

1. Edit `user_data/configs/config.delta.live.json` for trade counts/stake.
2. Edit strategy file for stoploss/leverage.
3. Restart bot: `docker compose restart freqtrade`.

### Emergency Stop

Run: `docker compose stop freqtrade`
Then manually close positions on Delta Exchange UI.
