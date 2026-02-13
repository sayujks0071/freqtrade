# Delta Exchange Freqtrade Stack

A production-ready Freqtrade setup for Delta Exchange (India & Global), featuring:
- Automated daily market refresh & whitelist generation.
- Strict schema validation & drift detection.
- Risk guardrails (Daily Loss Limit, Max Drawdown).
- Strategy auditing & safety enforcement.
- CI/CD workflows.

## Quick Start

1. **Bootstrap**:
   ```bash
   ./scripts/bootstrap.sh
   ```
   This creates necessary directories and copies `.env.example` to `.env`.

2. **Configure Environment**:
   Edit `.env` and set your credentials:
   - `DELTA_ENV`: `india_prod` or `global_prod`.
   - `DELTA_API_KEY`, `DELTA_API_SECRET`.
   - Risk settings (`DAILY_LOSS_LIMIT`).

3. **Fetch Markets & Validate**:
   ```bash
   ./scripts/update_markets_and_whitelist.sh
   ```
   This fetches the latest markets from Delta, validates the schema, and generates `user_data/pairlists/whitelist.delta.json`.

4. **Run Dry-Run**:
   ```bash
   ./scripts/run_dryrun.sh
   ```
   Starts the bot in dry-run mode. Check logs with `docker compose logs -f`.

5. **Run Live**:
   ```bash
   ./scripts/run_live.sh
   ```
   Starts the bot in live trading mode. **Use with caution!**

## Project Structure

- `docker-compose.yml`: Main container orchestration.
- `user_data/configs/`: Configuration files for dry-run and live modes.
- `user_data/strategies/`: Strategies (must inherit `AuditedStrategyMixin`).
- `user_data/reports/`: Generated reports (markets, daily summary, strategy scout).
- `scripts/`: Operational scripts.
- `tools/`: Python tools for validation, reporting, and strategy scouting.

## Key Features

### Market Refresh & Drift Detection
The `scripts/update_markets_and_whitelist.sh` script runs daily (via GitHub Actions) to:
1. Fetch latest markets from Delta.
2. Validate strict futures schema (symbol format, required fields).
3. Check for "drift" (ratio of removed pairs). If > 25% are removed, the update fails to prevent trading on a broken market structure.
4. Update the whitelist based on `FILTER_MODE` (default: `perps_usdt`).

### Risk Guardrails
See [Risk Profile](user_data/reports/risk_profile.md) for details.
- **Daily Loss Limit**: Stops trading if daily loss exceeds 5% (configurable).
- **Max Drawdown**: Stops trading a pair if drawdown exceeds 20%.
- **Cooldown**: 5 candles after exit.

### Strategy Safety
All strategies must inherit from `AuditedStrategyMixin` (`user_data/strategies/_base/AuditedStrategyMixin.py`). This enforces:
- Audit logging of all entry/exit signals.
- `process_only_new_candles = True` check.
- CI checks via `tools/strategy_auditor.py` reject strategies with unsafe imports or unclear logic.

### Strategy Scout
Run `python3 tools/strategy_scout.py` to discover top open-source Freqtrade strategies on GitHub.

## Monitoring
- **Logs**: `user_data/logs/freqtrade.log` (JSON format supported via config).
- **Daily Report**: Run `python3 tools/daily_report.py` to generate a Markdown summary of the last 24h trading performance.

## CI/CD
- `.github/workflows/delta-markets-refresh.yml`: Daily market update.
- `.github/workflows/strategy-ci.yml`: Validates strategy code on PRs.
