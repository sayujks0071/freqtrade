# Delta Exchange Freqtrade Stack

A production-ready crypto trading stack using Freqtrade in Docker connected to Delta Exchange (India + Global).

## Features

- **Safe Docker Setup**: Pre-configured `docker-compose.yml` for dry-run and live modes.
- **Automated Market Refresh**: Daily GitHub Actions workflow to fetch markets, validate schemas, and regenerate whitelists.
- **Strict Schema Gatekeeper**: Blocks updates if market data drifts significantly or format changes.
- **Risk Guardrails**: Hard limits on open trades, stake amount, and daily loss (5%).
- **Strategy Auditing**: CI checks for safe coding practices (AST analysis) and audit logging.
- **Observability**: Structured logs, daily PnL reports, and drift reports.

## Setup

### 1. Bootstrap

Run the bootstrap script to create necessary directories and copy the environment file:

```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment

Edit `.env` with your Delta Exchange credentials:

```bash
DELTA_ENV=india_prod  # or global_prod, india_testnet
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
```

### 3. Validate Connection & Markets

Before starting, ensure you can connect and the market data is valid:

```bash
./scripts/validate_exchange.sh
```
This will generate `user_data/reports/markets_<timestamp>.json` and validate the whitelist.

### 4. Start Dry-Run

Start the bot in dry-run mode (safe, no real money):

```bash
./scripts/run_dryrun.sh
```
Check logs: `docker compose logs -f`

### 5. Switch to Live Trading

**WARNING**: This involves real financial risk.

```bash
./scripts/run_live.sh
```

## Pair Selection & Whitelists

**NEVER** hand-type pairs blindly into the config. The stack uses an automated process to generate safe whitelists.

### Daily Market Refresh
The GitHub Workflow `.github/workflows/delta-markets-refresh.yml` runs daily at 06:30 Indian Standard Time.
1. Fetches latest markets from Delta.
2. Validates schema (detects drift, format changes).
3. Generates `user_data/pairlists/whitelist.delta.json`.
4. Opens a PR if changes are detected.

**Note**: This workflow *never* places trades. It only updates configuration artifacts.

To run manually:
```bash
./scripts/update_markets_and_whitelist.sh
```

## Risk Profile

See [Risk Profile Report](user_data/reports/risk_profile.md) for detailed limits.

- **Max Open Trades**: 5
- **Leverage**: 2x (Enforced by strategy)
- **Daily Loss Limit**: 5% (Stops new entries for the day)
- **Max Drawdown**: 20% (Stops trading for 12 candles)

## Observability

### Logs
Logs are stored in `user_data/logs/freqtrade.log` (JSON structured).

### Audit Logs
Strategies implementing `AuditedStrategyMixin` log every signal:
`AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE`

### Daily Report
Generate a summary of daily performance:
```bash
python3 tools/daily_report.py
```
Output: `user_data/reports/daily_summary_<date>.md`

## Strategy Development & CI

All strategies must pass strict CI checks.

### Requirements
1. Inherit from `AuditedStrategyMixin`.
2. Implement `populate_indicators`, `populate_entry_trend`, `populate_exit_trend`.
3. Use `check_daily_loss_limit` in `confirm_trade_entry`.
4. **No** `datetime.now()` (use provided candle dates).
5. **No** network calls or file I/O inside strategy logic.

To audit your strategy locally:
```bash
python3 tools/strategy_auditor.py user_data/strategies/
```

### Strategy Sourcing
Find open-source strategies:
```bash
python3 tools/strategy_scout.py --vendor
```
This searches GitHub for Freqtrade strategies and vendors them to `user_data/strategies_vendor/`.
