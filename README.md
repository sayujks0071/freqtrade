# Freqtrade Delta Exchange Stack

This repository contains a production-ready Freqtrade setup for trading on Delta Exchange (Global and India) using Docker.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed.
- [Docker Compose](https://docs.docker.com/compose/install/) installed.
- Delta Exchange API Keys (with Read/Trade permissions, NO Withdraw permissions).

## Quick Start

### 1. Initialize

Run the bootstrap script to create the necessary directories and copy the `.env` file:

```bash
chmod +x scripts/*.sh
./scripts/bootstrap.sh
```

### 2. Configure Environment

Edit `.env` with your API credentials and environment choice:

```bash
nano .env
```

Set `DELTA_ENV` to `india_prod` (for api.india.delta.exchange) or `global_prod` (for api.delta.exchange).
Set `DELTA_API_KEY` and `DELTA_API_SECRET`.

### 3. Validate Setup

Run the validation script to check connectivity, time sync, and fetch markets:

```bash
./scripts/validate_exchange.sh
```

This will:
- Check system time sync (essential for API requests).
- Verify Delta exchange availability.
- Fetch the latest futures markets from Delta.
- Generate a `user_data/pairlists/whitelist.delta.json` containing all active USDT futures pairs.
- Validate that the whitelist pairs exist.

### 4. Start Dry-Run

Start the bot in Dry-Run mode (simulated trading on live data):

```bash
./scripts/run_dryrun.sh
```

- **UI**: http://localhost:8080 (Login: `freqtrader` / `SuperSecurePassword123!`)
- **Logs**: `docker compose logs -f`

Verify in the logs that the bot connects to Delta and subscribes to tickers.

## How to Go Live

**WARNING: TRADING WITH REAL MONEY INVOLVES SIGNIFICANT RISK.**

To switch to live trading with real funds:

1. Ensure you have tested your strategy in dry-run mode.
2. Stop the dry-run container:
   ```bash
   docker compose down
   ```
3. Run the live script:
   ```bash
   ./scripts/run_live.sh
   ```
   You will be asked to confirm twice.

This will use `user_data/configs/config.delta.live.json` which has `dry_run: false`.

## Troubleshooting

### Rate Limits
If you see rate limit errors (429), ensure `enableRateLimit` is true in `config.delta.*.json` (default: true).

### Auth Failures
- Double-check your API Key and Secret in `.env`.
- Ensure you selected the correct `DELTA_ENV`. Keys for Global do not work on India and vice-versa.
- Verify IP whitelisting settings on Delta Exchange website.

### Symbol Mismatch
- Use `./scripts/validate_exchange.sh` to refresh the market dump.
- Check `user_data/pairlists/whitelist.delta.json` for generated pairs.
- Delta futures usually follow `BASE/QUOTE:SETTLE` format (e.g., `BTC/USDT:USDT`).

### Time Sync
If `validate_exchange.sh` fails on time sync:
- Install `ntp` or `chrony` on your host machine.
- Run `sudo ntpdate pool.ntp.org` (or equivalent).

## Configuration

- **Dry Run Config**: `user_data/configs/config.delta.dryrun.json`
- **Live Config**: `user_data/configs/config.delta.live.json`
- **Whitelist**: Automatically generated at `user_data/pairlists/whitelist.delta.json` by `validate_exchange.sh`.

To customize the whitelist, edit `whitelist.delta.json` manually (note: it might be overwritten if you re-run generation logic, so consider using a separate `whitelist.custom.json` and adding it to `docker-compose.yml` command if needed).

## Risk Warning

This software is for educational purposes. Use at your own risk. The authors are not responsible for financial losses.
Always start with `dry_run: true` and small `stake_amount`.
