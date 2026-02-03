# Delta Exchange Freqtrade Stack

A production-ready crypto trading stack for Delta Exchange (India + Global) using Freqtrade.

## Quick Start

1. **Bootstrap**:
   ```bash
   ./scripts/bootstrap.sh
   ```
   Edit `.env` with your API credentials.

2. **Validate Connection**:
   ```bash
   ./scripts/validate_exchange.sh
   ```
   This checks your connection and validates the market schema.

3. **Refresh Markets & Whitelist**:
   ```bash
   ./scripts/update_markets_and_whitelist.sh
   ```
   This fetches the latest futures pairs, validates them, and updates `user_data/pairlists/whitelist.delta.json`.

4. **Run Dry-Run**:
   ```bash
   ./scripts/run_dryrun.sh
   ```
   Monitor logs via `docker compose logs -f`.

5. **Run Live (Caution!)**:
   ```bash
   ./scripts/run_live.sh
   ```

## Key Features

### 1. Market Refresh & Gatekeeper
The `update_markets_and_whitelist.sh` script runs daily (via GitHub Actions) to keep the whitelist fresh.
- **Schema Validation**: `tools/validate_markets_schema.py` ensures the exchange data is valid and hasn't drifted significantly (Drift < 25%).
- **Whitelist Generation**: `tools/generate_whitelist.py` filters for valid futures pairs (e.g., `*USDT:USDT`).

### 2. Risk Management
- **Daily Loss Limit**: Stops trading if daily PnL hits -5% (configurable).
- **Execution**: Uses Limit orders and isolated margin.
- **Documentation**: See `user_data/reports/risk_profile.md` for detailed guardrails.

### 3. Strategy Safety
- **Auditor**: `tools/strategy_auditor.py` checks strategies for banned imports and unsafe patterns.
- **Mixin**: Strategies should inherit from `AuditedStrategyMixin` to ensure audit logging.
- **CI**: GitHub Actions block unsafe strategies from merging.

### 4. Observability
- **Daily Reports**: `tools/daily_report.py` generates trade summaries.
- **Audit Logs**: Signals are logged with `AUDIT_LOG` prefix.

## Tools
- `tools/strategy_scout.py`: Find open-source strategies on GitHub.
- `tools/daily_report.py`: Generate PnL reports from the database.

## Directory Structure
- `scripts/`: Operational scripts.
- `tools/`: Python utilities.
- `user_data/configs/`: Freqtrade configurations.
- `user_data/strategies/`: Strategy files.
