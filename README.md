# Freqtrade Delta Stack

A production-ready crypto trading stack for Delta Exchange (India + Global) using Freqtrade.

## Features
- **Safe Docker Setup**: Dry-run by default, separate live config.
- **Market Data Pipeline**: Daily refresh, schema validation, drift detection.
- **Risk Guardrails**: Hard caps, protections, daily loss limits.
- **Strategy CI**: AST-based auditing, safety checks, mixin enforcement.
- **Observability**: Structured logs, daily reports, audit trails.
- **Strategy Scout**: Tool to discover open-source strategies on GitHub.

## Quick Start

### 1. Bootstrap
Run the bootstrap script to set up directories and environment files.
```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment
Edit `.env` with your Delta Exchange API keys and settings.
```bash
cp .env.example .env
nano .env
```
Ensure `DELTA_ENV` is set correctly (`india_testnet`, `india_prod`, or `global_prod`).

### 3. Validate Connection & Markets
Verify that you can connect to Delta and fetch market data.
```bash
./scripts/validate_exchange.sh
```
This will generate `user_data/reports/markets_<timestamp>.json` and validate the schema.

### 4. Run Dry-Run (Safe Mode)
Start the bot in dry-run mode to test strategy logic and UI.
```bash
./scripts/run_dryrun.sh
```
Access the UI at `http://localhost:8080`.

### 5. Run Live Trading
**WARNING: Real money at risk.**
```bash
./scripts/run_live.sh
```
This script includes a mandatory confirmation prompt.

## Daily Market Refresh
The stack includes a tool to refresh markets daily and update the whitelist based on volume/filters.
```bash
./scripts/update_markets_and_whitelist.sh
```
This is automated via GitHub Actions (`.github/workflows/delta-markets-refresh.yml`).
It generates a drift report in `user_data/reports/whitelist_diff_*.md`.

## Strategy Management

### Adding Strategies
Place strategy files in `user_data/strategies/`.
All strategies must:
1. Inherit from `AuditedStrategyMixin` (in `_base`).
2. Include a standard metadata header.
3. Pass the `tools/strategy_auditor.py` check.

### Strategy Scout
Find new strategies on GitHub:
```bash
python3 tools/strategy_scout.py --vendor
```
This searches for high-quality Freqtrade strategies and can vendor them into `user_data/strategies_vendor/`.

### Strategy CI
The CI pipeline automatically audits strategies on every push/PR to ensure safety compliance.

## Monitoring & Reporting

- **Logs**: `user_data/logs/freqtrade.log` (structured logs).
- **Daily Report**: Run `python3 tools/daily_report.py` to generate a markdown summary.
- **Risk Profile**: See `user_data/reports/risk_profile.md` for detailed risk limits.

## Troubleshooting

- **Market Data Errors**: Run `validate_exchange.sh` to check connectivity.
- **Strategy Errors**: Run `tools/strategy_auditor.py <file>` to debug compliance issues.
- **Docker Issues**: Check logs with `docker compose logs -f`.

## License
MIT
