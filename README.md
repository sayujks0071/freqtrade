# Freqtrade on Delta Exchange

This repository contains a production-ready setup for trading on Delta Exchange using Freqtrade. It supports both dry-run and live trading, with configurations for Delta India and Global.

## Prerequisites

*   Docker
*   Docker Compose

## Setup

1.  **Clone the repository.**
2.  **Initialize the environment:**

    ```bash
    ./scripts/bootstrap.sh
    ```

    This will create the necessary directories and copy `.env.example` to `.env`.

3.  **Configure `.env`:**

    Edit `.env` and set your Delta Exchange API credentials and environment.

    ```bash
    DELTA_ENV=india_prod  # or global_prod, india_testnet
    DELTA_API_KEY=your_api_key
    DELTA_API_SECRET=your_api_secret
    ```

4.  **Validate the setup:**

    Run the validation script to check your connection and market data.

    ```bash
    ./scripts/validate_exchange.sh
    ```

    This script will:
    *   Check for time drift between your machine and Delta servers.
    *   Fetch the latest market data and save it to `user_data/reports/`.
    *   Verify that the pairs in your whitelist exist on the exchange.

## Running the Bot

### Dry Run (Paper Trading)

To start the bot in dry-run mode (using live market data but simulating trades):

```bash
./scripts/run_dryrun.sh
```

You can access the Freqtrade UI at `http://localhost:8080`. Default login: `freqtrader` / `superuser`.

### Live Trading

**WARNING: profound financial risk.** Ensure you have tested your strategy thoroughly in dry-run mode before switching to live trading.

To start the bot in live trading mode:

```bash
./scripts/run_live.sh
```

### Switching from Dry Run to Live

1.  Stop the dry-run container:
    ```bash
    docker compose down
    ```
2.  Run the live script:
    ```bash
    ./scripts/run_live.sh
    ```

## Troubleshooting

*   **Time Drift:** If `validate_exchange.sh` fails due to time drift, synchronize your system clock using NTP.
*   **API Errors:** Check your `DELTA_API_KEY` and `DELTA_API_SECRET` in `.env`. Ensure the permissions are correct (Trading allowed, Withdrawal disabled recommended).
*   **Symbol Mismatch:** If validation fails for a pair, check the `user_data/reports/markets_*.json` file for the correct symbol format (e.g., `BTC/USDT:USDT`).
*   **Connection Refused:** Ensure port 8080 is not in use.

## Configuration

*   **Whitelist:** Edit `user_data/configs/config.delta.dryrun.json` (or `live.json`) to modify the `pair_whitelist`.
*   **Strategy:** Place your strategy file in `user_data/strategies/` and update the config `strategy` field or pass `--strategy YourStrategy` to the command.

## Data

Market data dumps are saved in `user_data/reports/`.
Trades and logs are stored in `user_data/`.
