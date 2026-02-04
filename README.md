# Delta Exchange Trading Stack (Freqtrade)

Production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade in Docker.

## Features

- **Safe Docker Setup**: Dry-run by default, distinct live config, no secrets in git.
- **Market Validation**: Daily refresh of markets with drift detection and schema validation.
- **Risk Guardrails**: Daily loss limits, strict volume checks, and strategy auditing.
- **Strategy Tools**: Scout for open-source strategies, audit them for safety, and run them with structured logging.
- **Observability**: Daily reports and audit logs.

## Setup

1. **Bootstrap**
   ```bash
   chmod +x scripts/*.sh
   ./scripts/bootstrap.sh
   cp .env.example .env
   ```

2. **Configuration**
   Edit `.env`:
   - `DELTA_ENV`: `india_prod` or `global_prod`
   - `DELTA_API_KEY`: Your API Key
   - `DELTA_API_SECRET`: Your API Secret

3. **Validate & Refresh Markets**
   ```bash
   ./scripts/update_markets_and_whitelist.sh
   ```
   This generates `user_data/pairlists/whitelist.delta.json`.

4. **Start Dry-Run**
   ```bash
   ./scripts/run_dryrun.sh
   ```
   Access UI at http://localhost:8080.

5. **Start Live**
   ```bash
   ./scripts/run_live.sh
   ```

## Development

- **Strategy Audit**:
  ```bash
  python3 tools/strategy_auditor.py --file user_data/strategies/MyStrategy.py
  ```

- **Daily Report**:
  ```bash
  python3 tools/daily_report.py
  ```

## CI/CD

- **Market Refresh**: Runs daily at 06:30 IST. Updates whitelist and checks for drift.
- **Strategy CI**: Audits PRs for unsafe code (network calls, local time).

## Risk Profile

See [Risk Profile](user_data/reports/risk_profile.md) for details on hard limits and protections.
