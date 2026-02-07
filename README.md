# Freqtrade for Delta Exchange (Production Setup)

This repository contains a production-ready Freqtrade configuration for Delta Exchange (India + Global).

## Setup

1.  **Bootstrap**:
    ```bash
    bash scripts/bootstrap.sh
    ```
    This creates necessary directories and copies `.env.example` to `.env`.

2.  **Configure Environment**:
    Edit `.env` with your Delta Exchange API credentials and settings.
    ```bash
    DELTA_ENV=india_testnet # or india_prod, global_prod
    DELTA_API_KEY=your_key
    DELTA_API_SECRET=your_secret
    ```

3.  **Validate Connection & Markets**:
    Run the validation script to fetch markets and verify your whitelist.
    ```bash
    bash scripts/validate_exchange.sh
    ```
    If successful, it will generate `user_data/reports/markets_*.json`.

4.  **Start (Dry-Run)**:
    Start the bot in dry-run mode.
    ```bash
    docker compose up -d
    ```
    Access UI at http://localhost:8080 (Login: freqtrader / superuser).

## Daily Workflow

### Market Refresh
The workflow `.github/workflows/delta-markets-refresh.yml` runs daily at 06:30 IST.
It:
1. Fetches latest markets from Delta.
2. Validates schema and drifts (prevents delisted pairs).
3. Updates `user_data/pairlists/whitelist.delta.json`.
4. Generates a report and opens a PR if changes are detected.

You can also run it manually:
```bash
bash scripts/update_markets_and_whitelist.sh
```

### Reporting
Generate a daily trading report:
```bash
python3 tools/daily_report.py --days 1 --out user_data/reports/daily_summary.md
```

## Strategy Development

### Sourcing
Find open-source strategies:
```bash
python3 tools/strategy_scout.py --query "freqtrade strategy" --limit 5
```

### Auditing
All strategies must pass the auditor before merging.
```bash
python3 tools/strategy_auditor.py user_data/strategies/MyStrategy.py
```
Key requirements:
- Metadata header (Strategy, Author, etc.).
- No unsafe imports (`os`, `sys`).
- UTC timestamps (`datetime.now(timezone.utc)`).
- `AuditedStrategyMixin` for audit logs.

## Risk Management
See `user_data/reports/risk_profile.md` for detailed risk settings.
- **Daily Loss Limit**: Stops trading if PnL < -5% (default).
- **Protections**: Cooldown, StoplossGuard, MaxDrawdown.
- **Safety**: Market validation prevents trading on delisted pairs.

## Docker
- `docker-compose.yml`: Main service configuration.
- `user_data/configs/`: Configuration files for dry-run and live modes.

**Note**: To switch to LIVE trading:
1.  Set `DELTA_ENV` to `india_prod` or `global_prod`.
2.  Set `FREQTRADE_CONFIG_FILE=config.delta.live.json` in `.env`.
3.  Restart: `docker compose up -d`.
