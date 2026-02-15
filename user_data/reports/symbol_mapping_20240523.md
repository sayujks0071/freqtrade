# Symbol Mapping Report - 20240523

## Delta Contract Symbology vs Freqtrade Futures Pair Format

Delta Exchange uses contract symbols like `BTCUSDT` for linear perpetuals.
Freqtrade and CCXT require a standardized format for futures: `BASE/QUOTE:SETTLE`.

### Format Rules
- **Base**: The asset being traded (e.g., BTC, ETH).
- **Quote**: The quote currency (e.g., USDT).
- **Settle**: The settlement currency (e.g., USDT for linear perps).

### Examples

Below is a mapping of common Delta futures contracts to their Freqtrade pair format.

| Delta Contract | Freqtrade Pair Format | Description |
| :--- | :--- | :--- |
| `BTCUSDT` | `BTC/USDT:USDT` | Bitcoin Linear Perpetual settled in USDT |
| `ETHUSDT` | `ETH/USDT:USDT` | Ethereum Linear Perpetual settled in USDT |
| `SOLUSDT` | `SOL/USDT:USDT` | Solana Linear Perpetual settled in USDT |
| `XRPUSDT` | `XRP/USDT:USDT` | Ripple Linear Perpetual settled in USDT |
| `LTCUSDT` | `LTC/USDT:USDT` | Litecoin Linear Perpetual settled in USDT |

### How to Find Correct Symbols
1. Run `docker compose run --rm freqtrade list-markets --config user_data/configs/config.delta.dryrun.json --print-json > markets.json`
2. Inspect the output JSON or use `tools/generate_symbol_mapping.py` (if available) to generate this report.
3. Ensure you select pairs ending in `:USDT` for linear perpetuals.

### Why This Matters
Using the incorrect format (e.g., `BTC/USDT`) will cause Freqtrade to look for Spot markets or fail to place orders on Delta Futures. The `:USDT` suffix is mandatory for linear futures.
