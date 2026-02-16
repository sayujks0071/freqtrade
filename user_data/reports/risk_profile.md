# Risk Profile

## Configuration

| Parameter | Value | Description |
|---|---|---|
| **Max Open Trades** | 10 | Maximum number of concurrent positions. |
| **Stake Amount** | Unlimited | Uses all available capital allocated by `tradable_balance_ratio`. |
| **Tradable Balance** | 99% | Keeps 1% buffer in wallet. |
| **Leverage** | 1x (Default) | Strategies can override, but capped at exchange max. |
| **Margin Mode** | Isolated | Limits risk to the position margin. |

## Daily Loss Limit

- **Threshold**: 5% of total balance (Configurable via `DAILY_LOSS_LIMIT` env var).
- **Action**: Stops entering new trades until the next day (00:00 UTC).
- **Implementation**: `user_data/protections/DailyLossLimit.py`.

## Whitelist Safety

- **Filter Mode**: `perps_usdt` (Default). Only validates USDT-margined perpetuals.
- **Drift Protection**: Updates are rejected if > 25% of pairs are removed in one day.
- **Liquidity**: Pairs with low volume (if `STRICT_VOLUME=true`) are excluded.

## Strategy Constraints

All strategies must pass the `Strategy Auditor` check:
- No network calls.
- No local time usage (must use UTC).
- Must inherit `AuditedStrategyMixin` and log signals.
- Must handle `confirm_trade_entry` to check whitelist.

## Manual Intervention

In case of emergency:
1. **Stop Bot**: `docker compose down` or `docker stop freqtrade`.
2. **Close Positions**: Use Exchange UI or `freqtrade forceexit`.
3. **Blacklist**: Add pair to `pair_blacklist` in `config.delta.live.json` and reload (`docker compose restart freqtrade`).
