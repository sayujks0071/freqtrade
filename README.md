# Freqtrade Delta Exchange Stack

A production-ready Freqtrade setup for trading on Delta Exchange (India & Global) using Docker.

## ⚠️ Risk Warning

**Trading futures involves significant financial risk.** You can lose more than your initial investment.
This software is provided for educational purposes. Use at your own risk.
**ALWAYS** test thoroughly with `dry_run: true` before enabling live trading.

## Prerequisites

- Docker & Docker Compose
- Delta Exchange Account (Global or India)
- API Keys with **Trading** permissions (Disable Withdrawal permissions for security)

## Setup Guide

### 1. Bootstrap

Initialize the project structure and configuration:

```bash
./scripts/bootstrap.sh
```

### 2. Configuration

Edit the created `.env` file to set your environment and credentials:

```bash
nano .env
```

- **DELTA_ENV**:
  - `india_prod`: For Delta India (`api.india.delta.exchange`)
  - `global_prod`: For Delta Global (`api.delta.exchange`)
  - `india_testnet`: For Testnet
- **DELTA_API_KEY / DELTA_API_SECRET**: Your API credentials.

### 3. Validate & Generate Whitelist

Before starting, fetch the latest markets and generate a valid whitelist:

```bash
./scripts/validate_exchange.sh
```

This script will:
- Check connection to Delta Exchange.
- Fetch active Futures markets.
- Generate `user_data/pairlists/whitelist.delta.json` containing valid pairs.
- Verify that the whitelist is valid.

### 4. Run Dry-Run (Paper Trading)

Start the bot in Dry-Run mode. This simulates trading with live market data but uses fake currency.

```bash
./scripts/run_dryrun.sh
```

- UI: [http://localhost:8080](http://localhost:8080)
- Logs: `docker compose logs -f`

### 5. Go Live (Real Money)

**WARNING:** This mode uses REAL funds.

1. Stop the dry-run bot: `docker compose down`
2. Run the live script:

```bash
./scripts/run_live.sh
```

You will be prompted to confirm your decision.

## Configuration Details

- **Docker Compose**: `docker-compose.yml` manages the service, mounts `user_data`, and injects credentials from `.env`.
- **Configs**:
  - `user_data/configs/config.delta.dryrun.json`: Dry-run settings.
  - `user_data/configs/config.delta.live.json`: Live settings.
  - `user_data/pairlists/whitelist.delta.json`: Auto-generated whitelist.

## Troubleshooting

- **"delta exchange not found"**: Ensure you are using the official Freqtrade image and it includes `ccxt` support for Delta (standard in stable).
- **Rate Limits (429)**: The config sets `process_throttle_secs: 5`. Increase this if you encounter rate limits.
- **Symbol Mismatch**: Delta futures symbols format is `BTC/USDT:USDT`. The validation script handles this mapping.
- **Docker Mount Errors**: Ensure your user has permissions to read/write `user_data`.
- **Time Sync**: Ensure your host clock is synchronized (`ntp`). Crypto exchanges are sensitive to clock drift.
