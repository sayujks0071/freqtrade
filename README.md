# Delta Exchange Freqtrade Stack

A production-ready crypto trading stack using Freqtrade in Docker, tailored for Delta Exchange (India & Global).

## 🚀 Quick Start

1.  **Bootstrap**: Initialize directories and `.env`.
    ```bash
    ./scripts/bootstrap.sh
    ```
2.  **Configure**: Edit `.env` with your Delta API credentials.
    ```bash
    DELTA_ENV=india_prod  # or global_prod
    DELTA_API_KEY=...
    DELTA_API_SECRET=...
    ```
3.  **Validate**: Fetch markets and validate schema.
    ```bash
    ./scripts/validate_exchange.sh
    ```
    This generates `user_data/reports/markets_schema_report_*.md`.
4.  **Dry Run**: Start the bot in dry-run mode.
    ```bash
    ./scripts/run_dryrun.sh
    ```
    Logs are at `user_data/logs/freqtrade.log`. UI at `http://localhost:8080`.

## ⚠️ Live Trading

**WARNING**: This will place real orders. Ensure you have funded your wallet.

1.  **Switch Config**: The script uses `config.delta.live.json`.
2.  **Run**:
    ```bash
    ./scripts/run_live.sh
    ```
    (Includes a 5-second safety delay).

## 🛡️ Safety & Risk

See [Risk Profile](user_data/reports/risk_profile.md) for full details on limits and protections.

*   **Daily Loss Limit**: Stops new entries if realized loss > 5% for the day.
*   **Whitelist**: Only USDT-margined perps (`/USDT:USDT`).
*   **Schema Gatekeeper**: Prevents trading on invalid market data or excessive delistings (> 25% churn).

## 🔄 Daily Markets Refresh

Automated via GitHub Actions (`.github/workflows/delta-markets-refresh.yml`).
*   Runs daily at 06:30 Asia/Kolkata.
*   Fetches latest markets from Delta.
*   Validates schema & drift.
*   Generates new whitelist `user_data/pairlists/whitelist.delta.<env>.json`.
*   Opens PR if changes detected. **Never trades automatically.**

## 🧠 Strategy Management

*   **Sourcing**: Find strategies using `tools/strategy_scout.py`.
    ```bash
    python tools/strategy_scout.py --vendor
    ```
*   **Auditing**: Run local audit before pushing.
    ```bash
    python tools/strategy_auditor.py user_data/strategies/ --fix
    ```
*   **CI**: GitHub Actions will block merge if strategies fail audit (unsafe imports, missing headers, etc.).

## 📊 Observability

*   **Logs**: `user_data/logs/freqtrade.log` (structured JSON lines).
*   **Audit Logs**: Look for `AUDIT_SIGNAL` in logs for entry/exit reasons.
*   **Daily Report**:
    ```bash
    python tools/daily_report.py
    ```
    Generates `user_data/reports/daily_summary_<date>.md`.

## 🛠️ Development

*   **Requirements**: Python 3.11+
*   **Linting**: Uses `ruff`.
*   **Docker**: Official `freqtradeorg/freqtrade:stable` image.
