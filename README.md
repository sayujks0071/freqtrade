# Delta Exchange Freqtrade Stack

A production-ready crypto trading stack for Delta Exchange (India + Global), built on Freqtrade in Docker.
Designed for **Safety, Observability, and Strict Risk Management**.

## 🚀 Quick Start

1.  **Bootstrap**:
    Initialize the environment and directories.
    ```bash
    ./scripts/bootstrap.sh
    ```

2.  **Configure**:
    Edit `.env` with your Delta Exchange credentials.
    ```bash
    cp .env.example .env
    nano .env
    ```
    - `DELTA_ENV`: `india_prod` (India), `global_prod` (Global), or `india_testnet`.
    - `DELTA_API_KEY` / `DELTA_API_SECRET`: Your trading keys.

3.  **Fetch & Validate Markets**:
    Fetch active markets, validate schema, and generate the whitelist.
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    *Output:* `user_data/pairlists/whitelist.delta.json`

4.  **Run Dry-Run**:
    Start the bot in Dry-Run mode (simulated trading with live data).
    ```bash
    ./scripts/run_dryrun.sh
    ```
    *Logs:* `docker compose logs -f freqtrade`
    *UI:* http://localhost:8080 (Default: `freqtrader` / `SuperSecurePassword123!`)

5.  **Go Live**:
    **WARNING:** Real money trading.
    ```bash
    ./scripts/run_live.sh
    ```

## 🛡️ Safety & Risk Management

This stack enforces strict guardrails. See [Risk Profile](user_data/reports/risk_profile.md) for details.

-   **Market Validation**: Markets are validated for schema correctness (futures format `BASE/QUOTE:SETTLE`) and drift (max 25% removal).
-   **Daily Loss Limit**: Strategies adhering to `AuditedStrategyMixin` stop trading if daily PnL < -5%.
-   **Protection**: Max Drawdown, Cooldown, and StoplossGuard are enabled by default.
-   **Audit Logs**: Every signal is logged with `AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT`.

## 🛠️ Tools

The following tools are available to assist with strategy development and reporting.
**Note:** It is recommended to run these tools inside the Docker container to ensure all dependencies are met.

**Run a tool:**
```bash
docker compose run --rm freqtrade python3 tools/<tool_name>.py [args]
```

-   `tools/strategy_scout.py`: Finds and scores open-source strategies on GitHub.
    ```bash
    docker compose run --rm freqtrade python3 tools/strategy_scout.py
    ```
-   `tools/daily_report.py`: Generates daily PnL summaries from the database.
    ```bash
    docker compose run --rm freqtrade python3 tools/daily_report.py
    ```
-   `tools/strategy_auditor.py`: Audits strategy code for safety.
    ```bash
    docker compose run --rm freqtrade python3 tools/strategy_auditor.py user_data/strategies/
    ```
-   `tools/validate_markets_schema.py`: Validates market data dumps (used internally by update script).

## 🧩 Strategy Development

Strategies **MUST**:
1.  Inherit from `AuditedStrategyMixin`.
2.  Use `self.log_signal()` for entry/exit.
3.  Use `self.check_daily_loss_limit()` in `confirm_trade_entry`.
4.  Pass `tools/strategy_auditor.py` checks (CI enforced).

**Sample Strategy:** `user_data/strategies/DeltaSafeStrategy.py` implements all safety features.

Example:
```python
from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin
class MyStrategy(IStrategy, AuditedStrategyMixin):
    def confirm_trade_entry(self, pair, ...):
        if self.check_daily_loss_limit(0.05):
            return False
        self.log_signal(pair, "entry", "signal_tag")
        return True
```

## 🤖 CI/CD

-   **Delta Markets Refresh**: Runs daily at 06:30 IST (01:00 UTC) to update the whitelist and drift report.
-   **Strategy CI**: Runs on every push to validate strategy code safety.

## 📂 Directory Structure

-   `docker-compose.yml`: Main service definition.
-   `user_data/configs/`: Configuration files (`dryrun`, `live`).
-   `user_data/pairlists/`: Generated whitelists.
-   `user_data/reports/`: Market dumps, drift reports, risk profile.
-   `user_data/strategies/_base/`: Mixins and base classes.
-   `scripts/`: Management scripts.
-   `tools/`: Python utilities.

---
**Disclaimer:** Trading cryptocurrencies involves significant risk. This software is provided for educational purposes. Use at your own risk.
