# Delta Exchange Freqtrade Stack (Production Ready)

This repository provides a robust, Dockerized trading stack for Delta Exchange (India + Global) using Freqtrade. It includes strict validation, risk guardrails, automated market refreshes, and strategy safety checks.

## 🚀 Quick Start

### 1. Bootstrap
Initialize the environment and directories:
```bash
./scripts/bootstrap.sh
```

### 2. Configure Environment
Edit `.env` with your credentials and preferences:
```bash
cp .env.example .env
nano .env
```
Key variables:
- `DELTA_ENV`: `india_prod` (India), `global_prod` (Global), or `india_testnet`.
- `DELTA_API_KEY` / `DELTA_API_SECRET`: Your API keys.
- `FILTER_MODE`: `perps_usdt` (default), `all_futures`, or `allowlist_regex`.

### 3. Fetch Markets & Generate Whitelist
Fetch active markets from Delta and generate a validated whitelist:
```bash
./scripts/update_markets_and_whitelist.sh
```
This script:
1.  Fetches full market data from Delta.
2.  Validates the schema (fields, symbols, volume).
3.  Checks for dangerous "drift" (mass delistings).
4.  Generates `user_data/pairlists/whitelist.delta.json`.

### 4. Run Dry-Run
Start the bot in simulated mode (safe for testing):
```bash
./scripts/run_dryrun.sh
```
-   **Config**: `user_data/configs/config.delta.dryrun.json`
-   **UI**: http://localhost:8080 (Login: `freqtrader` / `SuperSecurePassword123!`)

### 5. Run Live
**⚠️ WARNING: Real Money Trading**
```bash
./scripts/run_live.sh
```
-   **Config**: `user_data/configs/config.delta.live.json`
-   Performs strict pre-flight checks (whitelist validity, connectivity).

---

## 🛡️ Safety & Guardrails

### Risk Controls
-   **Daily Loss Limit**: Stops trading for the day if realized PnL drops below limit (default 5%).
-   **Max Open Trades**: Hard cap (default 3).
-   **Leverage**: Controlled via config (default capped).
-   **Schema Gatekeeper**: Whitelist updates fail if market data is invalid or drifts too much (>25% removals).

### Strategy Safety
-   **CI/CD**: Strategies are audited on every push.
    -   Must define clear entry/exit logic.
    -   Must not use unsafe imports (`requests`, `socket`).
    -   Must not use naive `datetime.now()`.
-   **Audit Logs**: Every signal is logged with `AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | INDICATORS`.

## 🛠️ Tools

| Tool | Description |
| :--- | :--- |
| `scripts/update_markets_and_whitelist.sh` | periodic market refresh & validation |
| `tools/validate_markets_schema.py` | Strict schema validation for market dumps |
| `tools/strategy_scout.py` | Finds open-source Freqtrade strategies on GitHub |
| `tools/strategy_auditor.py` | Static analysis (AST) for strategy code safety |
| `tools/daily_report.py` | Generates markdown summary of last 24h trades |

## 📦 Directory Structure

-   `user_data/configs/`: Configuration files (dryrun, live, testnet).
-   `user_data/pairlists/`: Generated whitelists.
-   `user_data/protections/`: Custom protections (DailyLossLimit).
-   `user_data/strategies/_base/`: Base classes and mixins (`AuditedStrategyMixin`).
-   `user_data/reports/`: Market dumps, schema reports, daily summaries.
-   `scripts/`: Operational scripts.

## 🤖 GitHub Workflows

-   **Delta Markets Refresh**: Daily (01:00 UTC) fetch of markets. Commits changes to `chore/delta-markets-update` PR.
-   **Strategy CI**: Validates strategy code on push.

---
*Disclaimer: This software is for educational purposes. Trading cryptocurrencies involves significant risk.*
