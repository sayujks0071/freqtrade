# Freqtrade on Delta Exchange

This repository provides a production-ready Freqtrade setup for trading on Delta Exchange using Docker.
It supports both Delta Global and Delta India environments, with strict validation and safety checks.

## Prerequisites

- Docker and Docker Compose (v2+)
- A Delta Exchange account (Global or India)
- API Keys with "Read" and "Trade" permissions (disable "Withdraw")

## Quick Start

### 1. Bootstrap
Initialize the project structure and configuration files:
```bash
./scripts/bootstrap.sh
```

### 2. Configuration
Edit the generated `.env` file with your Delta API credentials:
```bash
nano .env
```
Set `DELTA_ENV` to `india_prod`, `global_prod`, or `india_testnet`.
Set `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Validation
Run the validation script to ensure connectivity, fetch markets, and verify your whitelist:
```bash
./scripts/validate_exchange.sh
```
This script performs:
- Time drift check against Google (must be < 5s)
- Connectivity check to Delta Exchange
- Market data fetch (saved to `user_data/reports/`)
- Whitelist validation (ensures all configured pairs exist)

### 4. Dry Run
Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
The bot will use `user_data/configs/config.delta.dryrun.json`.
Access the UI at http://localhost:8080.

### 5. Live Trading
**WARNING: This involves real financial risk.**
To switch to live trading:
1. Ensure your strategy and config are ready.
2. Run:
```bash
./scripts/run_live.sh
```
Confirm the prompt. The bot will use `user_data/configs/config.delta.live.json`.

## Configuration Files

- `user_data/configs/config.delta.dryrun.json`: Configuration for dry-run mode.
- `user_data/configs/config.delta.live.json`: Configuration for live mode.
- `user_data/pairlists/whitelist.delta.json`: The list of pairs to trade.

**Note:** The whitelist is validated against the market dump. If you want to change pairs, edit `whitelist.delta.json` and run `./scripts/validate_exchange.sh` to confirm validity.

## Troubleshooting

- **Time Drift Error:** Ensure your system clock is synchronized (use NTP).
- **Exchange Not Found:** Check `DELTA_ENV` in `.env`.
- **API Error / Auth Failure:** Verify API keys and permissions. Check if you are using the correct `DELTA_ENV` for your account.
- **Whitelist Validation Failed:** The pairs in `whitelist.delta.json` must exactly match the format returned by Delta (e.g., `BTC/USDT:USDT`). Check the latest market dump in `user_data/reports/` for correct symbols.

## Security

- API Keys are passed via environment variables and never stored in config files.
- The `.env` file is excluded from git (via `.gitignore` - ensure you add it).
- Run `docker compose down` to stop the bot.

## Disclaimer

This software is for educational purposes. Use at your own risk. The authors are not responsible for financial losses.
