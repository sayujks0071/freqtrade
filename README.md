# Delta Exchange Freqtrade Stack

A production-ready crypto trading stack for Delta Exchange (India + Global) using Freqtrade in Docker.

## Features

*   **Safe Docker Setup**: Dry-run by default, distinct live/dry configs.
*   **Daily Markets Refresh**: Automated fetching, validation, and whitelist generation with drift detection.
*   **Strict Schema Gatekeeper**: Blocks invalid market data or unsafe symbol formats (`BASE/QUOTE:SETTLE`).
*   **Risk Guardrails**:
    *   Hard caps on leverage (2x default) and open trades.
    *   **Daily Loss Limit**: Stops trading for the day if PnL < -X%.
    *   Cooldowns and Stoploss Guards.
*   **Observability**: Daily reports, structured audit logs, and healthchecks.
*   **Strategy CI**: Blocks risky or broken strategies from merging.
*   **Strategy Scout**: Tool to find open-source strategies.

## Setup

1.  **Bootstrap**:
    ```bash
    ./scripts/bootstrap.sh
    ```
    This creates directories and copies `.env.example` to `.env`.

2.  **Configure**:
    Edit `.env`:
    *   `DELTA_ENV`: `india_prod` or `global_prod`.
    *   `DELTA_API_KEY` / `DELTA_API_SECRET`: Your API keys.
    *   Risk settings (`MAX_LEVERAGE`, `DAILY_LOSS_LIMIT`).

3.  **Fetch Markets**:
    ```bash
    ./scripts/update_markets_and_whitelist.sh
    ```
    This fetches markets, validates schema, and generates `user_data/pairlists/whitelist.delta.json`.

4.  **Start Dry-Run**:
    ```bash
    ./scripts/run_dryrun.sh
    ```
    View logs: `docker compose logs -f`

5.  **Go Live**:
    *   Stop dry-run: `docker compose down`
    *   Run: `./scripts/run_live.sh` (Prompts for confirmation)

## Tools

*   **Market Validation**: `tools/validate_markets_schema.py` ensures market data integrity.
*   **Daily Report**: `tools/daily_report.py` generates markdown summaries from trade history.
*   **Strategy Auditor**: `tools/strategy_auditor.py` checks strategy code for safety (used in CI).
*   **Strategy Scout**: `tools/strategy_scout.py` finds strategies on GitHub.

## Risk Management

See [Risk Profile](user_data/reports/risk_profile.md) for details on configured limits and protections.

## Development

*   **Add Strategy**: Place in `user_data/strategies/`. Must inherit `AuditedStrategyMixin`.
*   **CI Checks**:
    *   Syntax check (`compileall`).
    *   Auditor check (Metadata, Unsafe imports).

## License

MIT
