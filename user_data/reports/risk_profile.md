# Risk Profile & Guardrails

This document outlines the risk management settings for the Delta Exchange Freqtrade bot.

## Hard Limits (Config)

These are defined in `user_data/configs/config.delta.*.json`.

| Setting | Value | Description |
| :--- | :--- | :--- |
| `max_open_trades` | 3 | Maximum concurrent open positions. |
| `stake_amount` | 100 USDT | Capital allocated per trade. |
| `tradable_balance_ratio` | 0.99 | Ratio of wallet balance available for trading. |
| `dry_run_wallet` | 1000 | Simulated wallet balance for dry-run/backtesting. |
| `margin_mode` | isolated | Margin mode (isolated prevents cross-contamination). |
| `leverage` | Strategy | Leverage is usually set by strategy (default 2x recommended). |

## Protections

Protections are enabled in the `protections` block of the config.

### 1. Cooldown Period
- **Duration**: 5 candles
- **Description**: Prevents re-entering a trade on the same pair immediately after exit.

### 2. Max Drawdown
- **Max Drawdown**: 20% (0.2)
- **Trade Limit**: 5 trades
- **Stop Duration**: 60 candles
- **Description**: Stops trading for a specific pair if it incurs too much drawdown within a short period.

### 3. Daily Loss Limit (Custom)
- **Limit**: -5% (Default)
- **Description**: Stops **ALL** new entries for the rest of the day (UTC) if realized PnL drops below the limit.
- **Configuration**:
  - Set `DAILY_LOSS_LIMIT` in `.env` (e.g., `DAILY_LOSS_LIMIT=-0.05` for -5%).
  - Calculations are based on `dry_run_wallet` (dry-run) or actual balance (live - depends on implementation). Currently uses `dry_run_wallet` as reference capital in `DailyLossLimit.py`.

## Market Validation Guardrails

Enforced by `scripts/update_markets_and_whitelist.sh` and `tools/validate_markets_schema.py`.

- **MIN_MARKETS**: 20 (Minimum eligible markets required to proceed)
- **MAX_REMOVAL_RATIO**: 0.25 (Max 25% of whitelist can be removed at once to prevent mass delisting drift)
- **FILTER_MODE**: `perps_usdt` (Only USDT perpetuals allowed)
- **Schema Checks**:
  - Must have `BASE/QUOTE:SETTLE` format (Futures).
  - Must be active.
  - Must have valid symbol structure.

## How to Change Limits

1. **Edit `.env`**: Update `DAILY_LOSS_LIMIT`, `STAKE_AMOUNT`, etc. (Note: Config json takes precedence for some values unless using env var substitution in config, which is supported by some docker setups but safer to edit json).
2. **Edit Config**: Modify `user_data/configs/config.delta.live.json`.
3. **Restart**: Run `docker compose restart freqtrade`.

## Safety Checklist Before Going Live

- [ ] Validated markets using `scripts/validate_exchange.sh`.
- [ ] Checked `DAILY_LOSS_LIMIT` in `.env`.
- [ ] Verified `stake_amount` is appropriate for account size.
- [ ] Confirmed `dry_run: false` in live config.
