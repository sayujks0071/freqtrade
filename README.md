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

### 3. Fetch Markets & Generate Whitelist

Run the update script to fetch active markets and generate a compliant whitelist:
```bash
./scripts/update_markets_and_whitelist.sh
```
This will:
1. Fetch markets from Delta.
2. Validate the schema.
3. Generate `user_data/pairlists/whitelist.delta.json` with active USDT-perp pairs.

### 4. Validate Exchange Connection

Verify everything is consistent before starting:
```bash
./scripts/validate_exchange.sh
```
This script performs a pre-flight check:
- Verifies connection to Delta API.
- Checks if `whitelist.delta.json` pairs exist in the current market dump.
- Checks time drift.

### 5. Start Dry-Run

Start the bot in Dry-Run mode:
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f`
- Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `SuperSecurePassword123!` - **Change this in config!**)

### 6. Go Live 🚀

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
- **Empty Whitelist:** Run `./scripts/update_markets_and_whitelist.sh`.
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Check `user_data/reports/markets_*.json` for valid symbols.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in the config.
- **Time Drift:** Ensure your server time is synced (`ntp`).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (`config.delta.dryrun.json`, `config.delta.live.json`).
- `user_data/pairlists/`: Generated whitelist (`whitelist.delta.json`).
- `scripts/`: Helper scripts.
- `.env`: Secrets (Git-ignored).
