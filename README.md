# Freqtrade Delta Exchange Platform

A production-ready crypto trading stack using Freqtrade, tailored for Delta Exchange (India + Global).
This setup enforces strict safety, risk management, and audit trails.

## Features

- **Environments**: Supports `india_prod`, `global_prod`, `india_testnet`.
- **Market Data**: Automated daily refresh, schema validation, and drift detection.
- **Risk Guardrails**: Daily loss limits, whitelist validation, and strict execution settings.
- **Strategy Auditing**: AST-based static analysis to enforce code quality and safety rules.
- **Observability**: Structured audit logs and daily PnL reports.
- **CI/CD**: Automated workflows for market updates and strategy validation.

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local tools)

### 2. Setup
Run the bootstrap script to initialize directories and environment:
```bash
./scripts/bootstrap.sh
```

Edit the `.env` file with your credentials:
```bash
nano .env
```
Ensure `DELTA_API_KEY`, `DELTA_API_SECRET`, and `DELTA_ENV` are set.

### 3. Verify Connection
Validate your connection and market data:
```bash
./scripts/validate_exchange.sh
```
This fetches the latest markets and checks if your whitelist is valid.

### 4. Run Dry Run
Start the bot in Dry Run mode (safe, no real trades):
```bash
./scripts/run_dryrun.sh
```
View logs:
```bash
docker compose logs -f freqtrade
```

### 5. Run Live
**WARNING**: This uses real money. Ensure you have reviewed `user_data/reports/risk_profile.md`.
```bash
./scripts/run_live.sh
```

## Market Management

We do NOT use static whitelists. The whitelist is generated dynamically from exchange data.

### Manual Refresh
To update markets and regenerate the whitelist manually:
```bash
./scripts/update_markets_and_whitelist.sh
```
This script:
1. Fetches markets from Delta.
2. Generates a whitelist based on `FILTER_MODE` (default: `perps_usdt`).
3. Validates the schema and checks for dangerous drift (removal of active pairs).
4. Updates `user_data/pairlists/whitelist.delta.json`.

### CI/CD Refresh
The GitHub Workflow `Delta Markets Refresh` runs daily at 06:30 Asia/Kolkata to automate this process. It opens a PR if changes are detected.

## Strategy Development

Strategies must inherit from `AuditedStrategyMixin` and pass the `strategy_auditor.py` checks.

### Rules
- **Header**: Must include Strategy Name, Author, Version, etc.
- **Logging**: Use `self.log_signal(...)` for all trade decisions.
- **Safety**: No network calls, no system time (use UTC), no repainting.
- **Risk**: Respect `daily_loss_limit`.

### Example
See `user_data/strategies/DeltaSafeStrategy.py` for a compliant example.

### Validation
Run the auditor locally:
```bash
python tools/strategy_auditor.py user_data/strategies/MyStrategy.py
```

## Risk Profile

See [Risk Profile](user_data/reports/risk_profile.md) for detailed limits.
- **Max Open Trades**: 5
- **Stake Amount**: 20 USDT (Live default)
- **Daily Loss Limit**: -5% of account balance (stops new entries).

## Observability

- **Logs**: `user_data/logs/freqtrade.log` (JSON format recommended).
- **Daily Report**: Generate a PnL report:
  ```bash
  python tools/daily_report.py --days 1
  ```
  Output saved to `user_data/reports/`.

## Tools

- `tools/validate_markets_schema.py`: Gatekeeper for market dumps.
- `tools/strategy_scout.py`: Finds open-source strategies on GitHub.
- `tools/strategy_auditor.py`: Enforces strategy code standards.

## License
MIT
