# Delta Exchange Freqtrade Stack

This repository provides a production-ready Freqtrade setup for trading on **Delta Exchange** (Global or India) using Docker Compose.

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
- Set `FREQTRADE_UI_PASSWORD` to a secure password.

### 3. Validate Exchange Connection

Before starting, verify your credentials, market data availability, and time sync:
```bash
./scripts/validate_exchange.sh
```
This script will:
1. Verify `delta` exchange support.
2. Check for time drift between your machine and Delta servers.
3. Fetch available markets and update `user_data/pairlists/whitelist.delta.json`.
4. Validate market schema and drift (using containerized tools).

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f`
- Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `<your_configured_password>`)

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
- **Time Drift:** If you see "Time drift > 5000ms", ensure your system clock is synced (NTP).
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. The scripts handle this automatically via `update_markets_and_whitelist.sh`.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in `user_data/configs/config.delta.*.json`.

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (dryrun vs live).
- `scripts/`: Helper scripts for management.
- `.env`: Secrets (Git-ignored).
- `user_data/pairlists/whitelist.delta.json`: Automatically generated whitelist.
- `tools/`: Validation and generation scripts (mounted into container).

## License

MIT
