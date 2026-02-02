# Freqtrade Delta Exchange Stack

A production-ready crypto trading stack for Delta Exchange (India + Global) using Freqtrade.

## Features

- **Dockerized Setup**: Safe, isolated environment with dry-run and live modes.
- **Market Data Pipeline**: Daily refresh, drift detection, and strict schema validation.
- **Risk Guardrails**: Daily loss limit, structural validation, and configurable limits.
- **Strategy Tooling**: CI checks, strategy scout, and auditing mixin.
- **Observability**: Structured logging and daily reports.

## Setup

1.  **Bootstrap**:
    ```bash
    ./scripts/bootstrap.sh
    ```
    This creates necessary directories and copies `.env.example` to `.env`.

2.  **Configuration**:
    Edit `.env` with your Delta Exchange API credentials:
    ```bash
    DELTA_ENV=india_testnet # or india_prod, global_prod
    DELTA_API_KEY=your_key
    DELTA_API_SECRET=your_secret
    ```

3.  **Validate Connection**:
    ```bash
    ./scripts/validate_exchange.sh
    ```

4.  **Market Data Refresh**:
    Fetch the latest markets and generate a whitelist:
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    This runs strict validation. If the market dump is invalid or drift is too high (>25%), it will fail.

## Usage

### Dry Run
Start the bot in dry-run mode (safe, no real money):
```bash
./scripts/run_dryrun.sh
```
Access UI at `http://localhost:8080`.

### Live Trading
**WARNING**: This uses real money.
```bash
./scripts/run_live.sh
```

## Risk Management

See [Risk Profile](user_data/reports/risk_profile.md) for detailed configuration.

- **Daily Loss Limit**: Bot stops new entries if daily PnL < -5% (configurable in `.env`).
- **Drift Protection**: Whitelist updates are blocked if too many pairs are delisted.
- **Audited Strategies**: Strategies must pass `tools/strategy_auditor.py` checks.

## Development & CI

### Strategy Auditing
Run the auditor locally:
```bash
python3 tools/strategy_auditor.py user_data/strategies/
```

### Strategy Scout
Find open-source strategies on GitHub:
```bash
python3 tools/strategy_scout.py
```
Outputs report to `user_data/reports/strategy_shortlist_<date>.md`.

### Daily Reporting
Generate a daily summary:
```bash
python3 tools/daily_report.py
```

## Workflows

- **Delta Markets Refresh**: Runs daily at 06:30 India Standard Time (01:00 UTC) via GitHub Actions.
- **Strategy CI**: Runs on every PR to `user_data/strategies/`.
