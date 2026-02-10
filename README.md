# Freqtrade on Delta Exchange

This repository contains a production-ready Freqtrade setup for trading on Delta Exchange (India & Global).

## Prerequisites

- Docker & Docker Compose
- A Delta Exchange account (India or Global)
- API Keys with "Trading" permissions (NO Withdrawals!)

## Setup Guide

### 1. Bootstrap
Initialize the project structure:
```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment
Edit `.env` file with your credentials:
```bash
DELTA_ENV=india_prod       # or global_prod / india_testnet
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
```

### 3. Validate Exchange & Markets
Verify connectivity and generate the market whitelist:
```bash
./scripts/validate_exchange.sh
```
This will:
- Check API connection.
- Fetch available futures markets.
- Validate market schema.
- Generate `user_data/pairlists/whitelist.delta.json`.

### 4. Run Dry-Run
Start the bot in Dry-Run mode (simulation on live data):
```bash
./scripts/run_dryrun.sh
```
- Access UI at `http://localhost:8080`.
- Verify trades are opening/closing in simulation.

### 5. Go Live
**WARNING: REAL MONEY TRADING**
To switch to live trading:
```bash
./scripts/run_live.sh
```
You will be prompted to confirm.

## Troubleshooting

- **Market Fetch Errors**: Check `DELTA_ENV` matches your account type.
- **Whitelist Empty**: Run `validate_exchange.sh` again. Ensure `tools/generate_whitelist.py` logic matches Delta symbol format.
- **Rate Limits**: Check `user_data/logs/freqtrade.log` for 429 errors.
- **Connectivity**: Ensure your server IP is whitelisted if you enabled IP restrictions on Delta.

## Safety

- **Stoploss**: Configured to NOT set stoploss on exchange (`stoploss_on_exchange: false`) to avoid liquidation hunting/slippage issues, managed internally by bot.
- **API Permissions**: NEVER enable "Withdraw" permission on your API keys.
