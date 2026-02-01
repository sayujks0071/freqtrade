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

## Strategy Audit & Pair Selection

### How to choose pairs on Delta
Always choose pairs from the generated markets dump or the whitelist file. **Never hand-type pairs blindly.**

1.  Run `./scripts/update_markets_and_whitelist.sh` to fetch latest markets.
2.  Check `user_data/reports/symbol_mapping_<date>.md` (if generated) or `user_data/pairlists/whitelist.delta.txt` for valid symbols.
3.  Delta Futures symbols must be in the format `BASE/QUOTE:SETTLE` (e.g., `BTC/USDT:USDT`).
    -   Raw Delta Symbol: `BTCUSDT` -> Freqtrade: `BTC/USDT:USDT`

### How to interpret logs
Strategies in this repo use an audit mixin to log detailed signals.

-   **Location**: Logs are found in `user_data/logs/freqtrade.log` (or standard output).
-   **Format**: Look for lines starting with `AUDIT_SIGNAL`.
    ```
    AUDIT_SIGNAL | 2023-10-27T10:00:01+00:00 | BTC/USDT:USDT | long | RSI < 30 | 2023-10-27T10:00:00+00:00 | {'rsi': 28.5}
    ```
-   **Fields**:
    -   `AUDIT_SIGNAL`: Log prefix.
    -   `EVENT_TS`: Timestamp when the log was written (UTC).
    -   `PAIR`: The symbol traded.
    -   `SIDE/REASON`: Direction and the specific condition that triggered (e.g., "long | RSI < 30").
    -   `CANDLE_TS`: The timestamp of the candle that triggered the signal.
    -   `INDICATORS`: Snapshot of key indicator values at that moment.

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
