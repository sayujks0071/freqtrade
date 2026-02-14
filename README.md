# Delta Exchange Trading Stack (Freqtrade)

This repository is configured as a production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade.

## Quick Start

1.  **Bootstrap**:
    ```bash
    ./scripts/bootstrap.sh
    ```
    This creates necessary directories and copies `.env.example` to `.env`.

2.  **Configure**:
    Edit `.env` with your Delta Exchange credentials.
    - `DELTA_ENV`: `india_prod`, `global_prod`, or `india_testnet`.
    - `DELTA_API_KEY` / `SECRET`.

3.  **Validate Exchange**:
    ```bash
    ./scripts/validate_exchange.sh
    ```
    This validates:
    - Time drift (critical for API).
    - Connectivity to Delta via CCXT.
    - Market availability.
    - Whitelist configuration.

4.  **Run Dry-Run**:
    ```bash
    ./scripts/run_dryrun.sh
    ```
    Starts Freqtrade in Docker with `config.delta.dryrun.json`.
    - Web UI: http://localhost:8080 (Login: `freqtrader` / `SuperSecurePassword123!`) - **Change this in config!**

5.  **Go Live**:
    ```bash
    ./scripts/run_live.sh
    ```
    **WARNING**: This uses real money. Ensure you have tested thoroughly.

## Configuration

### Environment (`.env`)
- `DELTA_ENV`: Controls which API endpoint is used.
- `DELTA_API_KEY`: Your trading key.
- `DELTA_API_SECRET`: Your trading secret.

### Config Files (`user_data/configs/`)
- `config.delta.dryrun.json`: Dry-run configuration (real data, fake money).
- `config.delta.live.json`: Live configuration (real money).
- Both are configured for `futures` trading with `isolated` margin.

### Whitelist
The bot uses a static whitelist.
- `scripts/bootstrap.sh` creates a dummy whitelist in `user_data/pairlists/whitelist.delta.json`.
- `scripts/validate_exchange.sh` fetches markets to `user_data/reports/`.
- You can manually update `whitelist.delta.json` or use `scripts/update_markets_and_whitelist.sh` (if available/configured) to generate it.

## Troubleshooting

- **Validation Fails (Time Drift):** Ensure your system time is synced (`sudo ntpdate pool.ntp.org` or similar).
- **Validation Fails (Whitelist):** Check if your pairs exist in `user_data/reports/markets_*.json`. Delta futures usually look like `BTC/USDT:USDT`.
- **429 Errors:** Delta has strict rate limits. If you see this, increase `process_throttle_secs` in config or `rateLimit` in `ccxt_async_config`.
- **Docker Errors:** Run `docker compose logs -f` to see details.

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files.
- `scripts/`: Helper scripts.
- `.env`: Secrets (Git-ignored).

## Financial Risk Warning

**Trading cryptocurrencies involves significant risk.** You can lose all of your capital.
This software is for educational purposes. Use at your own risk.
**ALWAYS** test with `dry_run: true` before enabling live trading.
