# Freqtrade Delta Exchange Stack

This repository contains a production-ready setup for trading on Delta Exchange (Global or India) using Freqtrade.

## ⚠️ Financial Risk Warning

**Trading cryptocurrencies involves significant risk.** You can lose all of your capital.
This software is for educational purposes. Use at your own risk.
**ALWAYS** test with `dry_run: true` before enabling live trading.

## Prerequisites

- Docker & Docker Compose
- A Delta Exchange Account (Global or India)
- API Keys (Trading permissions only, **NO** withdrawal permissions)

## Setup Guide

### 1. Bootstrap

Run the bootstrap script to initialize directories and configuration:
```bash
./scripts/bootstrap.sh
```

### 2. Configuration

Edit the generated `.env` file:
```bash
nano .env
```
- Set `DELTA_ENV`:
  - `india_prod` for Delta India (api.india.delta.exchange)
  - `global_prod` for Delta Global (api.delta.exchange)
  - `india_testnet` for Testnet
- Enter your `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Validate Exchange Connection

Before starting, verify your credentials and market data availability:
```bash
./scripts/validate_exchange.sh
```
This script will:
1. Fetch available markets from Delta.
2. Save the market list to `user_data/reports/`.
3. Verify that the pairs in `user_data/configs/config.delta.dryrun.json` exist and are active.

If validation fails, update the whitelist in `user_data/configs/config.delta.dryrun.json` and retry.

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f`
- Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `password` - Change this in config!)

### 5. Go Live 🚀

**WARNING:** This will trade with REAL funds.

1. Ensure you have tested thoroughly in Dry-Run.
2. Stop the dry-run bot:
   ```bash
   docker compose down
   ```
3. Run the live script:
   ```bash
   ./scripts/run_live.sh
   ```
   Confirm the prompt to start.

## Troubleshooting

- **Validation Fails:** Check if `DELTA_ENV` matches your account type. Ensure API keys have correct permissions.
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Check `user_data/reports/markets_*.json` for valid symbols.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in the config.
- **Time Drift:** Ensure your server time is synced (`ntp`).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (dryrun vs live).
- `scripts/`: Helper scripts for management.
- `.env`: Secrets (Git-ignored).
# Delta Exchange Trading Stack (Freqtrade)

This repository is configured as a production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade.

## Quick Start

1.  **Bootstrap**:
    ```bash
    ./scripts/bootstrap.sh
    ```
    This creates necessary directories and copies `.env.example` to `.env`.

2.  **Configure**:
    Edit `.env` with your Delta Exchange credentials.
    - `DELTA_ENV`: `india_prod`, `global_prod`, or `india_testnet`.
    - `DELTA_API_KEY` / `SECRET`.

3.  **Fetch Markets & Whitelist**:
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    This fetches active markets, validates schema, and generates `user_data/pairlists/whitelist.delta.json`.

4.  **Run Dry-Run**:
    ```bash
    ./scripts/run_dryrun.sh
    ```
    Starts Freqtrade in Docker with `config.delta.dryrun.json`.

5.  **Run Live**:
    ```bash
    ./scripts/run_live.sh
    ```
    **WARNING**: This uses real money. Ensure you have tested thoroughly.

## Key Features

-   **Dockerized**: Safe, isolated execution.
-   **Strict Validation**: Markets are validated for schema correctness and drift.
-   **Risk Guardrails**:
    -   Daily Loss Limit (stops trading if PnL < -X%).
    -   Max Drawdown protection.
    -   Hard caps on open trades and leverage.
-   **Strategy CI**: GitHub Actions block unsafe strategies.
-   **Observability**: Daily reports and structured logging.
-   **Audit Logs**: Strategy signals are logged with `AUDIT_SIGNAL` prefix in the logs (`user_data/logs/freqtrade.log`).

## Tools

-   `tools/daily_report.py`: Generates daily trading summary.
-   `tools/strategy_scout.py`: Finds strategies on GitHub.
-   `tools/validate_markets_schema.py`: Validates market dumps.
-   `tools/strategy_auditor.py`: Audits strategy code for safety.

## Documentation

-   [Risk Profile](user_data/reports/risk_profile.md)
-   [Symbol Mapping](user_data/reports/symbol_mapping.md)
-   [Freqtrade Documentation](https://www.freqtrade.io)

## How to Choose Pairs on Delta

**Crucial:** Never hand-type pairs blindly.
Always refer to the generated market dump or the symbol mapping report.

1. Run `./scripts/update_markets_and_whitelist.sh` (or `validate_exchange.sh`) to fetch the latest markets.
2. Check `user_data/reports/markets_*.json` for the list of active pairs.
3. Consult `user_data/reports/symbol_mapping.md` to understand the difference between Delta contract symbols (e.g., `BTCUSDT`) and Freqtrade pairs (`BTC/USDT:USDT`).
4. Update your `pair_whitelist` in `user_data/configs/config.delta.*.json` using the **Freqtrade format** (`BASE/QUOTE:SETTLE`).

## How to Interpret Logs

This stack includes an "Audit Layer" for strategy transparency.
Every trade decision is logged with a structured format in the main log file.

**Search for `AUDIT_SIGNAL` in your logs:**

```text
AUDIT_SIGNAL | 2023-10-27T10:00:00+00:00 | BTC/USDT:USDT | long | Signal Confirmed (Tag: entry_tag) | {'rsi': 25.5, 'volume': 1500}
```

- **Timestamp**: UTC ISO-8601 time of the signal/candle.
- **Pair**: The pair being traded.
- **Side**: `long` or `short`.
- **Reason**: The specific condition or tag that triggered the signal.
- **Indicators**: A snapshot of key indicator values at the time of the signal.

Use these logs to trace back why a trade was entered or exited.

---

# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[Original Freqtrade README follows...]
