# Delta Exchange Freqtrade Stack

A production-ready Freqtrade setup for Delta Exchange (India + Global), featuring strict safety guardrails, daily market validation, and automated strategy auditing.

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Delta Exchange API Keys (India or Global)

### 2. Setup Environment
```bash
# Clone repository
git clone <repo_url>
cd <repo_name>

# Configure Environment
cp .env.example .env
nano .env
# Set DELTA_API_KEY, DELTA_API_SECRET, DELTA_ENV (india_prod/global_prod)
```

### 3. Initialize & Dry Run
```bash
# Initialize directories and dummy whitelist
./scripts/bootstrap.sh

# Validate Connection & Fetch Markets
./scripts/validate_exchange.sh

# Start Dry Run (Safe Mode)
./scripts/run_dryrun.sh
```

### 4. Switch to Live Trading
**Warning**: Only do this after thorough testing!
```bash
# Edit config.delta.live.json if needed
nano user_data/configs/config.delta.live.json

# Start Live Bot
./scripts/run_live.sh
```

## 🛡️ Safety & Risk Management

### Market Validation
- **Daily Refresh**: Markets are fetched daily at 01:00 UTC via GitHub Actions.
- **Schema Validation**: Ensures strict compliance (Symbol format, Volume, Active status).
- **Drift Protection**: Updates are blocked if >25% of pairs are delisted.
- **Whitelist**: Automatically generated based on `FILTER_MODE` (e.g., `perps_usdt`).

### Guardrails
See [Risk Profile](user_data/reports/risk_profile.md) for full details.
- **Hard Caps**: Max 5 open trades, 2x leverage.
- **Daily Loss Limit**: Stops trading for the day if realized loss > 5% (configurable).
- **Protections**: Cooldown, MaxDrawdown, StoplossGuard enabled.

## 📊 Observability

### Logging
- Structured JSON logs in `user_data/logs/freqtrade.log`.
- **Audit Logs**: Every trade signal is logged with a snapshot of indicators.

### Reports
- **Daily Report**: `tools/daily_report.py` generates performance summaries.
  ```bash
  python3 tools/daily_report.py --config user_data/configs/config.delta.dryrun.json
  ```
- **Strategy Auditing**: Strategies are checked for safety (no repainting, no network calls) via CI.

## 🧠 Strategy Development

### Adding Strategies
1. Place strategy in `user_data/strategies/`.
2. Ensure it inherits `AuditedStrategyMixin` and `IStrategy`.
3. Must pass `tools/strategy_auditor.py` checks.

```python
from _base.AuditedStrategyMixin import AuditedStrategyMixin
from freqtrade.strategy import IStrategy

class MyStrategy(AuditedStrategyMixin, IStrategy):
    process_only_new_candles = True
    ...
```

### Strategy Scout
Find open-source strategies:
```bash
python3 tools/strategy_scout.py --limit 10
```

## 🛠️ Maintenance

- **Update Markets Manually**:
  ```bash
  ./scripts/update_markets_and_whitelist.sh
  ```
- **Validate Schema**:
  ```bash
  python3 tools/validate_markets_schema.py user_data/reports/markets_latest.json
  ```
