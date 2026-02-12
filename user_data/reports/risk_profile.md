# Delta Exchange Risk Profile

This document outlines the risk management parameters configured for the Freqtrade bot on Delta Exchange.

## Hard Limits

| Parameter | Value | Description |
|---|---|---|
| **Max Open Trades** | 3 | Maximum number of simultaneous positions. |
| **Stake Amount** | 100 USDT | Fixed amount per trade. |
| **Leverage** | 2x | Default leverage (enforced via strategy or exchange config). |
| **Stoploss** | -10% | Default hard stoploss per trade. |
| **Daily Loss Limit** | -5% | Total daily PnL limit. Trading stops if hit. |

## Protections

The following protections are enabled in `config.delta.live.json`:

1.  **CooldownPeriod**: Stops trading for 5 candles after a trade closes.
2.  **MaxDrawdown**: Stops trading for 12 candles if drawdown exceeds 15% over 48 candles (max 20 trades).
3.  **StoplossGuard**: Stops trading for 2 candles if 3 stoplosses are hit within 24 candles.
4.  **LowProfitPairs**: Blacklists a pair for 60 candles if 2 trades yield < 2% profit over 6 candles.

## Strategy Controls

- **Audit Logging**: Every trade entry and exit is logged with reasons and metadata.
- **Closed Candle Logic**: Strategies only process on closed candles to avoid repainting.
- **Whitelist Enforcement**: Strategies verify the pair is in the current whitelist before generating signals.

## Tuning

To adjust these limits:
1.  Edit `user_data/configs/config.delta.live.json` for Freqtrade protections.
2.  Edit `.env` or `AuditedStrategyMixin.py` for Daily Loss Limit (`DAILY_LOSS_LIMIT`).
3.  Restart the bot to apply changes.
