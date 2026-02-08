# Risk Profile & Guardrails

This document outlines the risk management parameters enforced by the Freqtrade Delta stack.

## Hard Constraints
These constraints are enforced by the configuration (`config.delta.*.json`) and environment variables.

| Parameter | Value | Description |
|---|---|---|
| **Max Open Trades** | `3` | Maximum number of concurrent open positions. |
| **Max Leverage** | `2x` | Default leverage cap (configured in strategy or exchange settings). |
| **Stake Amount** | `100 USDT` | Fixed stake per trade. Use `unlimited` with caution. |
| **Order Type** | `Limit` | Entry and Exit orders are Limit orders to avoid slippage. |
| **Stoploss** | Strategy Dependent | Hard stoploss enforced by bot. |

## Active Protections
The following protections are enabled in `config.delta.*.json`:

### 1. Cooldown Period
- **Duration:** 3 candles
- **Effect:** Prevents re-entering a pair immediately after a trade closes.

### 2. Stoploss Guard
- **Trigger:** 2 stoplosses within 24 candles.
- **Action:** Locks the pair for 12 candles.
- **Scope:** Global (stops trading on that pair).

### 3. Max Drawdown
- **Trigger:** 20% drawdown within 48 candles (5 trades).
- **Action:** Stops trading on that pair for 12 candles.

### 4. Low Profit Pairs
- **Trigger:** 2 trades with < 0% profit within 24 candles.
- **Action:** Locks the pair for 6 candles.

## Daily Loss Limit
- **Limit:** 5% of account balance (configurable via `MAX_DAILY_LOSS_PCT`).
- **Mechanism:** Implemented in `AuditedStrategyMixin.check_daily_loss_limit`.
- **Logic:** Queries realized PnL for the current day from the database. If loss exceeds the limit, new trade entries are blocked.

## Execution Safety
- **Order Time In Force:** `GTC` (Good Till Cancelled).
- **Entry Pricing:** Matches Order Book Top 1.
- **Market Refresh:** Daily validation ensures only active, liquid pairs are traded.
- **Drift Check:** Fails if >25% of pairs are removed in a single day (Flash Crash protection).

## Audit Logging
All trade signals are logged with a snapshot of indicators at the time of signal generation.
Check logs for `AUDIT_SIGNAL` entries.
