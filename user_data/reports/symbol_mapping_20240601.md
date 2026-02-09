# Delta Exchange Symbol Mapping (2024-06-01)

## Overview

This report clarifies the mapping between Delta Exchange contract symbols (used in API calls and Delta's UI) and Freqtrade/CCXT pair formats (used in configuration and strategies).

## Naming Convention

### Delta Exchange (API/UI)
- **Linear Perpetual:** `BTCUSDT`, `ETHUSDT`
- **Inverse Perpetual:** `BTCUSD`, `ETHUSD`
- **Dated Futures:** `BTC-29SEP23`
- **Options:** `BTC-29SEP23-30000-C`

### Freqtrade / CCXT
Freqtrade uses the CCXT unified naming convention `BASE/QUOTE:SETTLE`.

- **Linear Perpetual:** `BTC/USDT:USDT` (Base: BTC, Quote: USDT, Settle: USDT)
- **Inverse Perpetual:** `BTC/USD:BTC` (Base: BTC, Quote: USD, Settle: BTC)
- **Dated Futures:** `BTC/USDT:USDT-230929` (Suffix denotes expiry YYMMDD)

## Examples

| Delta Symbol | Freqtrade Pair | Type |
|---|---|---|
| `BTCUSDT` | `BTC/USDT:USDT` | Linear Perpetual |
| `ETHUSDT` | `ETH/USDT:USDT` | Linear Perpetual |
| `SOLUSDT` | `SOL/USDT:USDT` | Linear Perpetual |
| `BTCUSD` | `BTC/USD:BTC` | Inverse Perpetual |
| `BTC-28JUN24` | `BTC/USDT:USDT-240628` | Dated Future |

## How to Verify

1. Run `freqtrade list-markets --config user_data/configs/config.delta.dryrun.json --print-json > markets.json` inside the container.
2. Inspect `markets.json` to see the `symbol` field (Freqtrade format) and `id` field (Delta format).
3. Check `user_data/reports/markets_*.json` if the update script was run.

## Strategy Configuration

Ensure your `pair_whitelist` in `config.delta.*.json` uses the Freqtrade format:

```json
"pair_whitelist": [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT"
]
```

## Troubleshooting

- **"Pair not found":** Ensure you are using the correct `BASE/QUOTE:SETTLE` format.
- **"Invalid symbol":** Check if the contract has expired or if you are using a dated future.
- **Drift:** Run `scripts/update_markets_and_whitelist.sh` to refresh the whitelist and detect drift.
