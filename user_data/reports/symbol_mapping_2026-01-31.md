# Delta Contract vs Freqtrade Pair Format

**Date:** 2026-01-31
**Author:** Google Jules (Strategy QA)

## Explanation

When trading on Delta Exchange via Freqtrade (CCXT), it is crucial to understand the difference between the exchange's internal symbol format and Freqtrade's standardized futures format.

- **Delta Exchange**: Often uses symbols like `BTCUSDT` for perpetuals or `BTC-28JUN24` for dated futures.
- **Freqtrade**: Uses the format `Base/Quote:Settle`.
  - Example: `BTC/USDT:USDT` for a Bitcoin perpetual settled in USDT.

### Why this matters
Using the wrong format in your configuration or whitelist will result in Freqtrade failing to find the market or fetching incorrect data. Strategies must also handle these symbols correctly if they perform specific logic per pair.

## Symbol Mapping

Below is a mapping of common pairs found in the repo's test data to their expected Freqtrade Futures format.

| Delta Symbol (Approx) | Freqtrade Futures Pair |
| --------------------- | ---------------------- |
| BTCUSDT               | BTC/USDT:USDT          |
| ETHUSDT               | ETH/USDT:USDT          |
| LTCUSDT               | LTC/USDT:USDT          |
| XRPUSDT               | XRP/USDT:USDT          |
| ADAUSDT               | ADA/USDT:USDT          |

*Note: The Delta symbol column is for reference. Always use the Freqtrade format in your `config.json`.*

## Verification
You can verify available markets and their Freqtrade names by running:
```bash
freqtrade list-markets --exchange delta
```
Always copy the pair name exactly as output by this command.
