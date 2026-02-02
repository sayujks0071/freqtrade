# Delta Exchange Trading Stack (Freqtrade)

This repository is configured as a production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade.

## ⚠️ Financial Risk Warning

**Trading cryptocurrencies involves significant risk.** You can lose all of your capital.
This software is for educational purposes. Use at your own risk.
**ALWAYS** test with `dry_run: true` before enabling live trading.

## Prerequisites

- Docker & Docker Compose
- A Delta Exchange Account (Global or India)
- API Keys (Trading permissions only, **NO** withdrawal permissions)

## Quick Start

1.  **Bootstrap**:
    Initialize directories and configuration:
    ```bash
    ./scripts/bootstrap.sh
    ```
    This creates necessary directories and copies `.env.example` to `.env`.

2.  **Configure**:
    Edit `.env` with your Delta Exchange credentials.
    ```bash
    nano .env
    ```
    - `DELTA_ENV`: `india_prod` (api.india.delta.exchange), `global_prod` (api.delta.exchange), or `india_testnet`.
    - `DELTA_API_KEY` / `DELTA_API_SECRET`.

3.  **Fetch Markets & Whitelist**:
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    This fetches active markets, validates schema, and generates `user_data/pairlists/whitelist.delta.json`.

    **Validation:** This script will verify that the pairs in your config exist and are active. If validation fails, check the logs in `user_data/reports/`.

4.  **Run Dry-Run**:
    Start the bot in Dry-Run mode (simulated trading with live data):
    ```bash
    ./scripts/run_dryrun.sh
    ```
    - The bot will launch in the background.
    - Logs can be viewed with: `docker compose logs -f`
    - Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `password` - Change this in config!)

5.  **Run Live**:
    **WARNING:** This uses real money. Ensure you have tested thoroughly.
    ```bash
    ./scripts/run_live.sh
    ```
    Confirm the prompt to start.

## Key Features

-   **Dockerized**: Safe, isolated execution.
-   **Strict Validation**: Markets are validated for schema correctness and drift.
-   **Risk Guardrails**:
    -   Daily Loss Limit (stops trading if PnL < -X%).
    -   Max Drawdown protection.
    -   Hard caps on open trades and leverage.
-   **Strategy CI**: GitHub Actions block unsafe strategies.
-   **Observability**: Daily reports and structured logging.
-   **Audit Logs**: Strategy signals are logged with `AUDIT_SIGNAL` prefix in the logs (`user_data/logs/freqtrade.log`).

## Tools

-   `tools/daily_report.py`: Generates daily trading summary.
-   `tools/strategy_scout.py`: Finds strategies on GitHub.
-   `tools/validate_markets_schema.py`: Validates market dumps.
-   `tools/strategy_auditor.py`: Audits strategy code for safety.

## Documentation

-   [Risk Profile](user_data/reports/risk_profile.md)
-   [Symbol Mapping](user_data/reports/symbol_mapping_2024.md)
-   [Freqtrade Documentation](https://www.freqtrade.io)

## How to choose pairs on Delta

**Always pick from the markets dump.** Never hand-type pairs blindly.

1. Run `./scripts/update_markets_and_whitelist.sh`.
2. Check `user_data/pairlists/whitelist.delta.txt` or the JSON report.
3. Copy the `Base/Quote:Settle` format (e.g., `BTC/USDT:USDT`) into your config.

## How to interpret logs

The **Strategy Audit Layer** ensures every trade decision is explainable.
Look for lines starting with `AUDIT_SIGNAL` in the logs (`user_data/logs/freqtrade.log` or docker logs).

**Format:**
`AUDIT_SIGNAL | TIMESTAMP (UTC) | PAIR | SIDE | REASON | INDICATORS`

**Example:**
`AUDIT_SIGNAL | 2024-01-01T12:00:00+00:00 | BTC/USDT:USDT | long | Signal Confirmed | {'rsi': 25.5, 'volume': 1500, 'close': 42000.0}`

This tells you exactly why the strategy entered/exited at that moment.

## Troubleshooting

- **Validation Fails:** Check if `DELTA_ENV` matches your account type. Ensure API keys have correct permissions.
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Check `user_data/reports/markets_*.json` for valid symbols.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in the config.
- **Time Drift:** Ensure your server time is synced (`ntp`).

---

# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[Original Freqtrade README follows...]
