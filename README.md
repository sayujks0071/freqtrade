# Freqtrade Delta Exchange Stack

This repository contains a production-ready setup for trading on Delta Exchange (Global or India) using Freqtrade and Docker.

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
  - `india_testnet` for Testnet (cdn-ind.testnet.deltaex.org)
- Enter your `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Update Markets and Whitelist

Fetch the latest market data and generate a whitelist:
```bash
./scripts/update_markets_and_whitelist.sh
```
This script will:
1. Fetch active futures markets from Delta Exchange.
2. Filter for valid pairs (e.g., USDT-margined).
3. Automatically update `user_data/pairlists/whitelist.delta.json` with available pairs.

### 4. Validate Exchange Connection

Verify your credentials and configuration before starting:
```bash
./scripts/validate_exchange.sh
```
This script will:
1. Check time drift between your host and Delta servers.
2. Fetch available markets from Delta (for validation context).
3. Validate that the pair whitelist in `user_data/pairlists/whitelist.delta.json` matches available markets.

### 5. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f freqtrade`
- Access the UI at: http://localhost:8080

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
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Run `./scripts/update_markets_and_whitelist.sh` to refresh your whitelist.
- **Rate Limits:** If you see 429 errors, CCXT rate limiting is enabled by default in the config.
- **Time Drift:** If validation fails with time drift, ensure your server time is synced (`sudo ntpdate pool.ntp.org` or similar).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files.
- `user_data/pairlists/`: Whitelist files.
- `scripts/`: Helper scripts for management.
- `tools/`: Python helper scripts.
- `.env`: Secrets (Git-ignored).
