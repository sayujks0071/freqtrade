# Risk Profile & Guardrails

This document outlines the risk management settings and guardrails enforced by the trading stack.

## 1. Hard Limits (Configuration)

These settings are defined in `user_data/configs/config.delta.live.json` and enforce strict boundaries on position sizing and exposure.

*   **Max Open Trades**: `5`
    *   Maximum number of concurrent positions.
*   **Stake Amount**: `20 USDT`
    *   Fixed amount per trade.
*   **Leverage**: `1.0` (implied or set in strategy)
    *   Default is 1x. Strategies can request higher leverage but should be capped.
*   **Tradable Balance Ratio**: `0.99`
    *   Only 99% of wallet balance is used, keeping 1% for fees/buffer.

## 2. Protections (Plugins)

The bot uses Freqtrade's protection mechanisms to stop trading during adverse conditions.

*   **CooldownPeriod**: `5 candles`
    *   After a trade closes, the pair is locked for 5 candles to prevent wash trading or rapid re-entry.
*   **MaxDrawdown**:
    *   Stops trading for `12 candles` if `20%` drawdown is hit within `48 candles`.
*   **LowProfitPairs**:
    *   Locks pairs that consistently yield low profit (< 2%) over `6 candles`.
*   **Daily Loss Limit**: (Strategy Level)
    *   Stops **new entries** for the day if realized daily loss exceeds `5%` (configurable).
    *   Implemented via `AuditedStrategyMixin`.

## 3. Market Validation & Whitelist

*   **Schema Check**:
    *   Markets are validated daily for schema compliance (symbol format, volume).
    *   Drift detection prevents trading if > 25% of markets are delisted.
*   **Whitelist Filter**:
    *   Only `USDT` margined perps are allowed by default (`FILTER_MODE=perps_usdt`).
    *   Volume checks (warn/fail) ensure liquidity.

## 4. Execution Guardrails

*   **Order Types**:
    *   Entry: `Limit` (with timeout to Market)
    *   Exit: `Limit` (with timeout to Market)
    *   Stoploss: `Market` (guaranteed exit)
*   **Time in Force**: `GTC` (Good Till Cancelled)

## 5. How to Tune Safely

To adjust these settings:

1.  **Edit Config**: Modify `user_data/configs/config.delta.live.json`.
2.  **Edit Env**: Adjust `MAX_REMOVAL_RATIO` or `MIN_MARKETS` in `.env`.
3.  **Restart**: Run `docker compose restart freqtrade`.

**WARNING**: Increasing `max_open_trades` or `stake_amount` increases risk exposure linearly. Always backtest changes.
