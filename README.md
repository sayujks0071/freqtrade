# Freqtrade Delta Exchange Setup

This repository contains a production-ready configuration for running Freqtrade on Delta Exchange (Global and India).

## Prerequisites

- Docker & Docker Compose
- API Keys for Delta Exchange (with Trading permissions, NO Withdrawal permissions)

## Setup

1.  **Initialize Environment**
    Run the bootstrap script to create necessary directories and copy the environment template.
    ```bash
    ./scripts/bootstrap.sh
    ```

2.  **Configure `.env`**
    Edit the `.env` file with your API credentials and environment choice.
    ```bash
    nano .env
    ```
    - `DELTA_ENV`: Set to `india_prod` for Delta India, `global_prod` for Global, or `india_testnet`.
    - `DELTA_API_KEY`: Your API Key.
    - `DELTA_API_SECRET`: Your API Secret.

3.  **Validate Connection & Whitelist**
    Run the validation script to fetch markets and verify your configuration. This will also generate a default whitelist if one is missing.
    ```bash
    ./scripts/validate_exchange.sh
    ```
    This script saves the market dump to `user_data/reports/` and updates `user_data/configs/whitelist.json`.

## Running Freqtrade

### Dry Run (Recommended First Step)
Start the bot in Dry-Run mode (live data, simulated trading).
```bash
./scripts/run_dryrun.sh
```
- Access the UI at: http://localhost:8080
- View logs: `docker compose logs -f`

### Live Trading
**WARNING: Real money at risk.**
To switch to live trading:
1.  Ensure you have tested your strategy in dry-run.
2.  Run the live script:
    ```bash
    ./scripts/run_live.sh
    ```
    This script includes a 5-second safety delay.

## Configuration Details

- **Docker Compose**: The `docker-compose.yml` mounts `user_data` and injects secrets via environment variables.
- **Configs**:
    - `user_data/configs/config.delta.dryrun.json`: Dry-run settings.
    - `user_data/configs/config.delta.live.json`: Live trading settings.
    - `user_data/configs/whitelist.json`: Generated whitelist (included in bot config).
- **Scripts**:
    - `common.sh`: Handles environment variables and Delta URL logic.
    - `validate_exchange.sh`: Fetches markets and validates/generates whitelist.

## Troubleshooting

- **Rate Limits**: If you see rate limit errors, check `config.delta.*.json` `ccxt_async_config` settings.
- **Auth Failures**: Double-check your `.env` file and ensure the API key permissions are correct.
- **Symbol Mismatch**: If the bot complains about invalid pairs, run `./scripts/validate_exchange.sh` to regenerate the whitelist based on fresh market data.
- **Missing Whitelist**: If `whitelist.json` is missing, `validate_exchange.sh` will create a default one with top 5 USDT perps.

## Financial Warning

Trading cryptocurrencies involves significant risk. This software is for educational purposes only. Do not trade with money you cannot afford to lose.
