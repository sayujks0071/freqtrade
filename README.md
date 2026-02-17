# Freqtrade on Delta Exchange

This repository contains the configuration and scripts to run Freqtrade on Delta Exchange (India & Global) using Docker.

## Prerequisites

- Docker and Docker Compose installed.
- Delta Exchange API Keys (with appropriate permissions).

## Quick Start

### 1. Bootstrap

Initialize the project structure and configuration files.

```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment

Edit the `.env` file with your Delta Exchange credentials.

```bash
nano .env
```

Set `DELTA_ENV` to:
- `india_prod`: For Delta India (api.india.delta.exchange)
- `global_prod`: For Delta Global (api.delta.exchange)
- `india_testnet`: For Testnet

### 3. Start Dry-Run

Validate the connection and start the bot in Dry-Run mode.

```bash
./scripts/run_dryrun.sh
```

Access the UI at http://localhost:8080.

### 4. Go Live

**WARNING: Real funds are at risk.**

To switch to live trading:

1. Ensure your strategy is tested.
2. Run the live startup script:

```bash
./scripts/run_live.sh
```

## Whitelist Management

The bot uses a static whitelist defined in `user_data/configs/config.delta.*.json` and `user_data/pairlists/whitelist.delta.json`.
The `validate_exchange.sh` script checks if your configured pairs exist on the exchange before starting.

## Troubleshooting

- **API Errors**: Check your `DELTA_ENV` and API keys in `.env`.
- **Market Data**: If markets are missing, check `user_data/reports/markets_*.json` generated during startup.
- **Permission Denied**: Ensure scripts are executable (`chmod +x scripts/*.sh`).

## Risk Warning

Trading cryptocurrencies involves significant risk and can result in the loss of your capital. Use at your own risk.
