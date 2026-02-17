# Delta Exchange Trading Stack (Freqtrade)

This repository contains a production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade.

## ⚠️ Financial Risk Warning

**Trading cryptocurrencies involves significant risk.** You can lose all of your capital.
This software is for educational purposes. Use at your own risk.
**ALWAYS** test with `dry_run: true` before enabling live trading.

## Prerequisites

- Docker & Docker Compose
- A Delta Exchange Account (Global or India)
- API Keys (Trading permissions only, **NO** withdrawal permissions)

## Quick Start

### 1. Bootstrap

Run the bootstrap script to initialize directories and configuration:
```bash
./scripts/bootstrap.sh
```

### 2. Configuration

Edit the generated `.env` file:
```bash
nano .env
```
- Set `DELTA_ENV`:
  - `india_prod` for Delta India (api.india.delta.exchange)
  - `global_prod` for Delta Global (api.delta.exchange)
  - `india_testnet` for Testnet
- Enter your `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Fetch Markets & Whitelist

```bash
./scripts/update_markets_and_whitelist.sh
```
This fetches active markets, validates schema, and generates `user_data/pairlists/whitelist.delta.json`.

**Validation Settings (in `.env`):**
- `MIN_MARKETS`: Minimum number of markets required (default 20).
- `MAX_REMOVAL_RATIO`: Max allowed ratio of removed pairs to prevent drift (default 0.25).
- `STRICT_VOLUME`: If `true`, fails validation on low volume markets (default `false`).
- `FILTER_MODE`: Selection mode (`perps_usdt`, `all_futures`, `allowlist_regex`).
- `ALLOWLIST_REGEX`: Regex pattern for `allowlist_regex` mode.

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading with live data):
```bash
./scripts/run_dryrun.sh
```
- The bot will launch in the background.
- Logs can be viewed with: `docker compose logs -f`
- Access the UI at: http://localhost:8080 (Default login: `freqtrader` / `password` - Change this in config!)

### 5. Go Live 🚀

**WARNING:** This will trade with REAL funds.

1. Ensure you have tested thoroughly in Dry-Run.
2. Stop the dry-run bot:
   ```bash
   docker compose down
   ```
3. Run the live script:
   ```bash
   ./scripts/run_live.sh
   ```

## Key Features

-   **Dockerized**: Safe, isolated execution.
-   **Strict Validation**: Markets are validated for schema correctness and drift.
-   **Risk Guardrails**:
    -   Daily Loss Limit (stops trading if PnL < -X%).
    -   Max Drawdown protection.
    -   Hard caps on open trades and leverage.
-   **Strategy CI**: GitHub Actions block unsafe strategies.
-   **Observability**: Daily reports and structured logging.
-   **Audit Logs**: Strategy signals are logged with `AUDIT_SIGNAL` prefix in the logs (`user_data/logs/freqtrade.log`).

## Tools

-   `tools/daily_report.py`: Generates daily trading summary.
-   `tools/strategy_scout.py`: Finds strategies on GitHub.
-   `tools/validate_markets_schema.py`: Validates market dumps.
-   `tools/strategy_auditor.py`: Audits strategy code for safety.

## Troubleshooting

- **Validation Fails:** Check if `DELTA_ENV` matches your account type. Ensure API keys have correct permissions.
- **Symbol Mismatch:** Delta Futures symbols usually look like `BTC/USDT:USDT`. Check `user_data/reports/markets_*.json` for valid symbols.
- **Rate Limits:** If you see 429 errors, increase `process_throttle_secs` in the config.
- **Time Drift:** Ensure your server time is synced (`ntp`).

## Directory Structure

- `docker-compose.yml`: Main service definition.
- `user_data/configs/`: Configuration files (dryrun vs live).
- `scripts/`: Helper scripts for management.
- `.env`: Secrets (Git-ignored).

---

# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[Original Freqtrade README follows...]
