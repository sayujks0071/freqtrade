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

## Strategy Auditing & Safety

To ensure absolute clarity and correctness in strategies, we use `tools/strategy_auditor.py`.

### Auditing a Strategy
Run the auditor on your strategy file:
```bash
python tools/strategy_auditor.py user_data/strategies/MyStrategy.py
```
This checks for:
-   **Required Header**: Metadata, timezone rules, and entry/exit logic descriptions.
-   **Clear Logic**: No complex one-liners; sub-conditions must be named boolean variables.
-   **Safety**: Inheritance from `AuditedStrategyMixin`.

To automatically add a missing header block:
```bash
python tools/strategy_auditor.py user_data/strategies/MyStrategy.py --fix
```

### Symbol Selection
**How to choose pairs on Delta:**
-   **NEVER** hand-type symbols blindly.
-   **ALWAYS** pick from the markets dump generated by `list-markets`.
-   See `user_data/reports/symbol_mapping_*.md` for a mapping between Delta contract symbols (e.g., `BTCUSDT`) and Freqtrade pair formats (e.g., `BTC/USDT:USDT`).

To generate the mapping report (requires a markets dump JSON):
```bash
python tools/generate_symbol_mapping.py user_data/reports/markets_latest.json
```

### Interpreting Audit Logs
Every trade decision is logged with an `AUDIT_SIGNAL` prefix for explainability.
-   **Location**: `user_data/logs/freqtrade.log` (or console in docker logs).
-   **Format**: `AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | CANDLE_TS | INDICATORS`
-   **Example**:
    ```
    AUDIT_SIGNAL | 2024-01-01T12:00:00+00:00 | BTC/USDT:USDT | long | RSI < 30 and Volume > 0 | 2024-01-01T11:59:00 | rsi=25.5, volume=150.2
    ```
    This allows you to trace exactly *why* a trade was entered or exited and what the indicator values were at that moment.

## Documentation

-   [Risk Profile](user_data/reports/risk_profile.md)
-   [Freqtrade Documentation](https://www.freqtrade.io)

---

# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[Original Freqtrade README follows...]
