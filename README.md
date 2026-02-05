# Delta Exchange Freqtrade Stack

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
3. Generate or Validate `user_data/pairlists/whitelist.delta.json`.

If validation fails, check your API keys and internet connection.

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f`
- Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `SuperSecurePassword123!` - **Change this in config!**)

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
- **Authorization Error:** Double check your API Key and Secret, and ensuring you are using the correct endpoint (`india_prod` vs `global_prod`).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (dryrun vs live).
- `scripts/`: Helper scripts for management.
- `.env`: Secrets (Git-ignored).
