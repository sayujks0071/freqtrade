# Freqtrade Delta Exchange Stack

A production-ready Freqtrade setup for Delta Exchange (India + Global).

## Quick Start

1.  **Bootstrap**:
    ```bash
    bash scripts/bootstrap.sh
    # Edit .env with your Delta credentials!
    ```

2.  **Validate Connectivity**:
    ```bash
    bash scripts/validate_exchange.sh
    ```

3.  **Run Dry-Run**:
    ```bash
    bash scripts/run_dryrun.sh
    ```
    Access UI at http://localhost:8080 (freqtrader/superuser).

4.  **Run Live**:
    ```bash
    bash scripts/run_live.sh
    # Follow prompts.
    ```

## Daily Operations

- **Market Refresh**: Automatically runs daily at 06:30 IST via GitHub Actions.
  - Updates whitelist based on liquidity and filters.
  - Checks for schema drift.
  - Generates drift report.
- **Reporting**:
  - Run `tools/daily_report.py` (or via docker) to get PnL summary.
  - Check `user_data/logs/` for structured logs.

## Strategy Development

- **Location**: `user_data/strategies/`
- **Requirements**:
  - Must inherit `AuditedStrategyMixin`.
  - Must set `process_only_new_candles = True`.
  - Must pass `tools/strategy_auditor.py`.
- **CI/CD**: Strategies are audited on every PR.

## Risk Management

See `user_data/reports/risk_profile.md` for details on configured limits.
