# Freqtrade Delta Exchange Stack

This repository contains a production-ready Freqtrade setup for **Delta Exchange** (Global and India).

## ⚠️ Financial Risk Warning
Trading cryptocurrencies involves significant risk. **You can lose all your funds.**
This software is for educational purposes. Use at your own risk.
Never share your API keys or secrets.

## Prerequisites
- Docker & Docker Compose
- API Keys from [Delta Exchange](https://www.delta.exchange) or [Delta India](https://india.delta.exchange)
- System clock synchronized via NTP (Critical for API connectivity)

## Setup

1. **Bootstrap**
   Initialize the directory structure and configuration:
   ```bash
   ./scripts/bootstrap.sh
   ```

2. **Configure Environment**
   Edit `.env` file with your credentials:
   ```bash
   nano .env
   ```
   - Set `DELTA_ENV` to `india_prod` or `global_prod`.
   - Set `DELTA_API_KEY` and `DELTA_API_SECRET`.

3. **Validate Connection**
   Verify your API keys, market data availability, and time synchronization:
   ```bash
   ./scripts/validate_exchange.sh
   ```
   This script acts as a **Preflight Check** and will:
   - Check system time synchronization.
   - Confirm Freqtrade supports 'delta'.
   - Fetch active futures markets.
   - Verify that your whitelist pairs exist on the exchange.

## Running the Bot

Both startup scripts automatically run the preflight checks. If validation fails, the bot will **refuse to start**.

### Dry-Run Mode (Safe)
Starts the bot with `dry_run: true`. It simulates trading using live market data but NO real money.
```bash
./scripts/run_dryrun.sh
```
- UI available at: http://localhost:8080
- Default login: `freqtrader` / `SuperSecurePassword123!` (Change in `config.delta.dryrun.json`)

### Live Trading Mode (Real Money)
Starts the bot with `dry_run: false`.
**Ensure you have funded your futures wallet.**
```bash
./scripts/run_live.sh
```
You will be prompted to confirm.

## Configuration
- **Main Configs**: `user_data/configs/config.delta.dryrun.json` / `live.json`
- **Whitelist**: `user_data/pairlists/whitelist.delta.json`
  - Update this file with the pairs you want to trade (e.g., `BTC/USDT:USDT`).
  - Run `./scripts/validate_exchange.sh` after updating to verify validity.

## Troubleshooting

- **Preflight Failed**: Read the output. Common causes:
  - **System Time**: Ensure your server clock is synced (`timedatectl`).
  - **Market Fetch Error**: Check your `DELTA_ENV` and API keys in `.env`.
  - **Whitelist Validation Failed**: Ensure the pairs in `whitelist.delta.json` are formatted correctly.
- **Port Conflict**: If port 8080 is in use, edit `docker-compose.yml` to map a different port.

## Switching Environments
To switch between Delta Global and Delta India:
1. Stop the bot: `docker compose down`
2. Edit `.env` and change `DELTA_ENV`.
3. Run `./scripts/validate_exchange.sh` to refresh markets.
4. Restart the bot.
