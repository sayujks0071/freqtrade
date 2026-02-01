# Freqtrade Delta Exchange Setup

This repository contains a production-ready Freqtrade setup for Delta Exchange (Global and India).

## Prerequisites

- Docker & Docker Compose

## Setup

1.  **Initialize the Environment**
    ```bash
    bash scripts/bootstrap.sh
    ```

2.  **Configure Credentials**
    Edit `.env` and set your API keys and `DELTA_ENV`.
    - `DELTA_ENV=india_prod` for Delta India.
    - `DELTA_ENV=global_prod` for Delta Global.
    - `DELTA_ENV=india_testnet` for Testnet.

3.  **Validate Connection**
    Verify that your API keys work, the exchange is reachable, and your whitelist pairs exist.
    ```bash
    bash scripts/validate_exchange.sh
    ```
    This script generates a market report in `user_data/reports/` and performs checks for:
    - Delta Exchange availability
    - Market data fetch
    - Whitelist validation
    - System time synchronization (NTP)

    **Whitelist Generation**: If your whitelist is empty or invalid, you can auto-generate a valid one based on active Delta Futures markets:
    ```bash
    python3 scripts/generate_whitelist.py user_data/reports/markets_TIMESTAMP.json user_data/configs/config.delta.dryrun.json
    ```

## Running the Bot

### Dry Run (Recommended First Step)
Start the bot in Dry-Run mode (simulation on live data).
```bash
bash scripts/run_dryrun.sh
```
This script runs the validation checks automatically before starting.
The UI will be available at http://localhost:8080.

### Live Trading
**WARNING: REAL FUNDS WILL BE USED.**

To switch to live trading:
1.  Ensure you have tested your strategy and setup in Dry-Run.
2.  Run:
    ```bash
    bash scripts/run_live.sh
    ```

## Troubleshooting

-   **Symbol Not Found**: Check `user_data/reports/markets_TIMESTAMP.json` to see available symbols. Delta Futures symbols usually look like `BTC/USDT:USDT`. Use `scripts/generate_whitelist.py` to fix your config.
-   **Auth Error**: Verify API Key and Secret in `.env`. Ensure permissions (Trading enabled, Withdraw disabled).
-   **Rate Limits**: If you hit rate limits, adjust `rateLimit` in `user_data/configs/config.delta.*.json`.
-   **Time Drift**: If the startup script fails with a time drift error, ensure your system clock is synchronized (use NTP).

## Safety & Disclaimer

This software is for educational purposes. Trading cryptocurrencies involves significant risk. The authors are not responsible for financial losses.
**NEVER COMMIT YOUR `.env` FILE OR API KEYS.**
