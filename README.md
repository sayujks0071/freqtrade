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

3.  **Fetch Markets & Whitelist**:
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    This fetches active markets, validates schema, and generates `user_data/pairlists/whitelist.delta.json`.

4.  **Run Dry-Run**:
    ```bash
    ./scripts/run_dryrun.sh
    ```
    Starts Freqtrade in Docker with `config.delta.dryrun.json`.

5.  **Run Live**:
    ```bash
    ./scripts/run_live.sh
    ```
    **WARNING**: This uses real money. Ensure you have tested thoroughly.

## Key Features

-   **Dockerized**: Safe, isolated execution.
-   **Strict Validation**: Markets are validated for schema correctness and drift.
-   **Risk Guardrails**:
    -   Daily Loss Limit (stops trading if PnL < -X%).
    -   Max Drawdown protection.
    -   Hard caps on open trades and leverage.
-   **Strategy CI**: GitHub Actions block unsafe strategies.
-   **Observability**: Daily reports and structured logging.

## Tools

-   `tools/daily_report.py`: Generates daily trading summary.
-   `tools/strategy_scout.py`: Finds strategies on GitHub.
-   `tools/validate_markets_schema.py`: Validates market dumps.
-   `tools/strategy_auditor.py`: Audits strategy code for safety.

## Documentation

-   [Risk Profile](user_data/reports/risk_profile.md)
-   [Freqtrade Documentation](https://www.freqtrade.io)

---

# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[Original Freqtrade README follows...]
