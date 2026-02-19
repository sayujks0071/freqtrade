# Delta Exchange Freqtrade Bot

This repository contains a production-ready Freqtrade setup for trading on Delta Exchange (Futures).

## Prerequisites

- Docker & Docker Compose
- Delta Exchange API Keys (with Read & Trade permissions, NO Withdrawal)

## Setup Guide

### 1. Bootstrap
Run the bootstrap script to create directories and the initial `.env` file:
```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment
Edit `.env` with your API credentials and environment choice:
```bash
nano .env
```
- `DELTA_ENV`: `india_prod` (default), `global_prod`, or `india_testnet`.
- `DELTA_API_KEY` & `DELTA_API_SECRET`: Your API keys.
- `FREQTRADE_API_PASSWORD`: Password for the web UI.

### 3. Validate Connection & Markets
Run the validation script to check connectivity, fetch markets, and verify your whitelist:
```bash
./scripts/validate_exchange.sh
```
This will:
- Check if Delta exchange is available.
- Fetch active futures markets.
- Save a report to `user_data/reports/markets_<timestamp>.json`.
- Warn if any whitelisted pairs are invalid.

### 4. Start in Dry-Run Mode
Start the bot with virtual money to test your strategy and connection:
```bash
./scripts/run_dryrun.sh
```
- Access the UI at: http://localhost:8080
- Login with `freqtrader` / `<your_password>`

## Going Live

**WARNING: Real money will be used!**

To switch to live trading:
1. Ensure your strategy is tested and you have sufficient balance in your Delta Futures wallet (USDT).
2. Stop the dry-run bot: `docker compose down`
3. Run the live script:
```bash
./scripts/run_live.sh
```

## Troubleshooting

- **"Exchange 'delta' not available"**: Ensure you are using the latest Freqtrade image.
- **"Validation Failed"**: Check if your API keys are correct and if the pairs in `user_data/configs/config.delta.*.json` exist in the market report.
- **"Time sync error"**: Ensure your system clock is synchronized (use NTP). Delta requires precise timing.
- **"Invalid API Key"**: Verify permissions. Withdrawal permission should strictly be disabled.

## Risk Warning
Trading futures involves significant risk and can result in the loss of your invested capital. Use at your own risk. This software is provided "as is".
