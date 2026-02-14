# Delta Exchange Freqtrade Stack

Production-ready crypto trading stack for Delta Exchange (India & Global), built on Freqtrade + Docker.

## Features

- **Safe Execution**: Dockerized setup with strict dry-run/live separation.
- **Market Integrity**: Automated schema validation, drift detection, and whitelist generation.
- **Risk Guardrails**:
  - Daily Loss Limit protection (stops trading if PnL < -X%).
  - Hard caps on trades, leverage, and drawdown.
  - Isolated margin mode forced.
- **Strategy Safety**:
  - CI pipeline blocks unsafe/unclear strategies.
  - Audit logging for every signal.
  - Mixin-based strategy structure.
- **Observability**: Structured logs, daily reports, and drift alerts.

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Delta Exchange Account (API Key/Secret)

### 2. Bootstrap
Initialize the environment:
```bash
./scripts/bootstrap.sh
```
This creates `user_data` structure and copies `.env.example` to `.env`.

### 3. Configure
Edit `.env`:
```bash
DELTA_ENV=india_testnet  # or india_prod, global_prod
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
DAILY_LOSS_LIMIT=-0.05   # Stop trading if daily loss > 5%
```

### 4. Fetch & Validate Markets
Fetch active markets and generate the whitelist:
```bash
./scripts/update_markets_and_whitelist.sh
```
This script:
1.  Fetches futures markets from Delta.
2.  Validates schema (must be valid futures).
3.  Checks for drift (max removal ratio).
4.  Updates `user_data/pairlists/whitelist.delta.<env>.json`.

### 5. Run Dry-Run
Start the bot in dry-run mode:
```bash
./scripts/run_dryrun.sh
```
- UI: http://localhost:8080 (Login: `freqtrader` / `password`)
- Logs: `docker compose logs -f`

### 6. Run Live
**WARNING**: Real money involved.
```bash
./scripts/run_live.sh
```

## Tools & Scripts

| Script | Description |
| :--- | :--- |
| `scripts/validate_exchange.sh` | Verifies connection and whitelist integrity. |
| `scripts/update_markets_and_whitelist.sh` | Fetches markets, validates schema, updates whitelist. |
| `tools/daily_report.py` | Generates PnL/Winrate summary (`user_data/reports/`). |
| `tools/strategy_scout.py` | Finds Freqtrade strategies on GitHub. |
| `tools/strategy_auditor.py` | Static analysis for strategy code safety. |

## Strategy Development

Strategies must:
1.  Inherit from `AuditedStrategyMixin` (in `user_data/strategies/_base/`).
2.  Use `self.log_signal()` for entry/exit logging.
3.  Pass the CI checks (no `datetime.now()`, no `requests`).

Example: `user_data/strategies/DeltaSafeStrategy.py`

Run auditor locally:
```bash
python3 tools/strategy_auditor.py user_data/strategies/MyStrategy.py
```

## Risk Management

See [Risk Profile](user_data/reports/risk_profile.md) for detailed limits.
- **Daily Loss Limit**: Configured via `.env` (`DAILY_LOSS_LIMIT`).
- **Max Drawdown**: Stops trading a pair if it draws down too much.
- **Cooldown**: Prevents re-entry immediately after exit.

## CI/CD

- **Delta Markets Refresh**: Runs daily to update whitelist and detect drift.
- **Strategy CI**: Runs on PRs to `user_data/strategies/` to enforce safety rules.

## License
MIT
