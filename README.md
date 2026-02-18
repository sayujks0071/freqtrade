# Freqtrade Delta Exchange Stack

Production-ready Freqtrade setup for Delta Exchange (India & Global), featuring automated market refresh, strict validation, risk guardrails, and strategy auditing.

## Setup

1. **Bootstrap Environment**
   ```bash
   ./scripts/bootstrap.sh
   ```
   This creates necessary directories and copies `.env.example` to `.env`.

2. **Configure `.env`**
   Edit `.env` with your API keys and environment settings:
   ```bash
   DELTA_ENV=india_prod  # or global_prod, india_testnet
   DELTA_API_KEY=...
   DELTA_API_SECRET=...
   ```

3. **Validate Connection & Markets**
   ```bash
   ./scripts/validate_exchange.sh
   ```
   This tests connection to Delta and validates market data schema.

4. **Update Whitelist**
   ```bash
   ./scripts/update_markets_and_whitelist.sh
   ```
   Fetches latest markets, validates them, and generates `user_data/pairlists/whitelist.delta.json`.

## Usage

### Dry Run (Testing)
```bash
./scripts/run_dryrun.sh
```
Uses `config.delta.dryrun.json`. Money is simulated.

### Live Trading
```bash
./scripts/run_live.sh
```
Uses `config.delta.live.json`. **Real money is at risk.**

### Stopping
```bash
docker compose down
```

## Strategy Development

### Strategy Scout
Find open-source strategies:
```bash
python3 tools/strategy_scout.py
```
Output: `user_data/reports/strategy_shortlist_<date>.md`

### Strategy Auditing
All strategies must pass the auditor check:
```bash
python3 tools/strategy_auditor.py user_data/strategies/
```
Key requirements:
- Inherit `AuditedStrategyMixin` (recommended)
- `process_only_new_candles = True`
- No `datetime.now()` (use `datetime.now(timezone.utc)`)
- No network calls

### Sample Strategy
See `user_data/strategies/DeltaSafeStrategy.py` for a compliant example.

## Risk Management

See `user_data/reports/risk_profile.md` for detailed limits.

- **Daily Loss Limit:** Bot stops entering trades if daily loss exceeds configured %.
- **Drift Protection:** Whitelist updates fail if too many pairs are removed.
- **Strict Schema:** Invalid market data prevents updates.

## Automation

- **Daily Market Refresh:** GitHub Action `.github/workflows/delta-markets-refresh.yml` runs daily to update whitelist and generate reports.
- **Strategy CI:** GitHub Action `.github/workflows/strategy-ci.yml` audits strategies on PRs.
