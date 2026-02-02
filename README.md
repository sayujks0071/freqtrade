# Freqtrade Delta Exchange Stack

This repository contains a production-ready Freqtrade setup for trading on Delta Exchange (India & Global).

## Features
- **Dockerized**: Easy deployment.
- **Environment Aware**: Supports `india_prod`, `global_prod`, and `india_testnet`.
- **Pre-flight Checks**: Validates markets, whitelist, and time synchronization before starting.
- **Secure**: API keys are managed via `.env` (not committed).

## Prerequisites
- Docker & Docker Compose
- Delta Exchange Account & API Keys

## Setup

### 1. Initialize
Run the bootstrap script to create necessary directories and configuration files:
```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment
Edit the `.env` file with your credentials:
```bash
nano .env
```
- Set `DELTA_ENV` to `india_prod` or `global_prod` (or `india_testnet`).
- Set `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Validate Connection & Markets
Run the validation script to check connectivity, fetch active markets, and verify your whitelist:
```bash
./scripts/validate_exchange.sh
```
*Note: This script will fetch the latest markets from Delta and ensure your configured whitelist pairs exist.*

## Running the Bot

### Dry Run (Paper Trading)
To start the bot in Dry-Run mode (using live market data but simulated wallet):
```bash
./scripts/run_dryrun.sh
```
- Access UI at: http://localhost:8080/

### Live Trading (REAL MONEY)
**WARNING: TRADING CRYPTO FUTURES INVOLVES SIGNIFICANT FINANCIAL RISK. YOU CAN LOSE YOUR ENTIRE CAPITAL.**

To start the bot in Live Trading mode:
```bash
./scripts/run_live.sh
```

## Whitelist Management
The bot uses `user_data/pairlists/whitelist.delta.json`.
To update the whitelist, you can edit this file manually or use the market dump generated in `user_data/reports/` as a reference.

## Troubleshooting
- **API Errors**: Ensure `DELTA_ENV` is correct and your API keys match the environment (India vs Global).
- **Time Drift**: If you see timestamp errors, ensure your system time is synced (use NTP).
- **Market Data**: If validation fails, check if the pairs in your whitelist are currently active on Delta Futures.

## Architecture
- `docker-compose.yml`: Defines the Freqtrade service.
- `scripts/`: Helper scripts for management.
- `user_data/configs/`: Configuration files for different modes.
- `user_data/pairlists/`: Whitelist storage.
