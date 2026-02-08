# Freqtrade Delta Exchange Stack

This repository provides a production-ready Freqtrade setup for trading on **Delta Exchange** (Global or India) using Docker.

## ⚠️ Financial Risk Warning

**Trading cryptocurrencies involves significant risk.** You can lose all of your capital.
This software is for educational purposes. Use at your own risk.
**ALWAYS** test with `dry_run: true` before enabling live trading.

## Prerequisites

- Docker & Docker Compose
- A Delta Exchange Account (Global or India)
- API Keys (Trading permissions only, **NO** withdrawal permissions)

## Quick Start Guide

### 1. Bootstrap

Initialize the project directories and configuration files:
```bash
./scripts/bootstrap.sh
```

### 2. Configuration

Edit the generated `.env` file:
```bash
nano .env
```
- **DELTA_ENV**:
  - `india_prod` for Delta India (api.india.delta.exchange)
  - `global_prod` for Delta Global (api.delta.exchange)
  - `india_testnet` for Testnet
- **DELTA_API_KEY** / **DELTA_API_SECRET**: Enter your credentials.

### 3. Validate Connection & Markets

Before starting, verify your credentials and market data availability:
```bash
./scripts/validate_exchange.sh
```
This script will:
1.  Check for time drift between your machine and Delta servers.
2.  Fetch available markets from Delta.
3.  Save the market list to `user_data/reports/`.
4.  Verify that the pairs in your config's whitelist exist and are active.

If validation fails, update the whitelist in `user_data/configs/config.delta.dryrun.json` (or live config) and retry.

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs: `docker compose logs -f`
- UI: http://localhost:8080 (Default login: `freqtrader` / `password` - Change this in config!)

### 5. Go Live 🚀

**WARNING:** This will trade with REAL funds.

1.  Ensure you have tested thoroughly in Dry-Run.
2.  Stop the dry-run bot: `docker compose down`
3.  Run the live script:
    ```bash
    ./scripts/run_live.sh
    ```
4.  Confirm the prompt to start.

## Troubleshooting

- **Validation Fails:** Check if `DELTA_ENV` matches your account type. Ensure API keys have correct permissions.
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Check `user_data/reports/markets_*.json` for valid symbols.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in the config.
- **Time Drift:** Ensure your server time is synced (`ntp`).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (`dryrun` vs `live`).
- `scripts/`: Helper scripts for management.
- `.env`: Secrets (Git-ignored).
