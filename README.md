# Freqtrade Delta Exchange Stack

Production-ready crypto trading stack for Delta Exchange (India + Global) using Freqtrade in Docker.

## Features

- **Safe Docker Setup**: Deterministic environments for India (`india_prod`) and Global (`global_prod`).
- **Realtime Data**: No mock data; dry-run connects to live exchange.
- **Market Validation**: Strict schema checks and drift detection for whitelist updates.
- **Risk Guardrails**:
  - Daily Loss Limit (stops trading if PnL < -X%).
  - Whitelist drift protection.
  - Strategy Auditor (CI) prevents unsafe code.
- **Observability**: Structured audit logs and daily reports.

## Quick Start

### 1. Bootstrap
Initialize directories and configuration:
```bash
./scripts/bootstrap.sh
```

### 2. Configure
Edit `.env` with your credentials:
```bash
nano .env
```
- Set `DELTA_ENV` (`india_prod` or `global_prod`).
- Set `DELTA_API_KEY` and `DELTA_API_SECRET`.
- Adjust `DAILY_LOSS_LIMIT` (default 0.05 = 5%).

### 3. Fetch Markets & Whitelist
Fetch active markets and generate the whitelist:
```bash
./scripts/update_markets_and_whitelist.sh
```
This validates the market dump against strict schema rules and generates `user_data/pairlists/whitelist.delta.json`.

### 4. Run Dry-Run
Start the bot in dry-run mode:
```bash
./scripts/run_dryrun.sh
```
- Validates exchange connection.
- Starts Docker container with `config.delta.dryrun.json`.
- Access UI at http://localhost:8080.

### 5. Go Live
**WARNING**: Real money involved.
```bash
./scripts/run_live.sh
```

## Strategy Development

### Auditing
All strategies must pass the auditor:
```bash
python3 tools/strategy_auditor.py user_data/strategies/
```
Rules:
- Inherit from `AuditedStrategyMixin`.
- No `datetime.now()` (use UTC).
- No network calls.
- Clear metadata header.

### Sourcing
Find open-source strategies:
```bash
python3 tools/strategy_scout.py --out user_data/reports/strategies.md
```

## Reporting

Generate daily trading report:
```bash
python3 tools/daily_report.py
```

See [Risk Profile](user_data/reports/risk_profile.md) for detailed risk configuration.
