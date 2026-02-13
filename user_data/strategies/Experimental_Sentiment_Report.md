# Experimental Sentiment Strategy Report

**Date:** 2026-02-13
**Period:** 2026-01-01 to 2026-01-30 (Adjusted due to data availability)

## Hypothesis
Using Money Flow Index (MFI) as a proxy for "Whale Wallet Movements" (MFI < 20) combined with RSI < 30 (Oversold) will identify high-probability reversal points better than RSI alone.

## Results

| Strategy | Sharpe Ratio | Profit % | Max Drawdown | Trades |
| :--- | :--- | :--- | :--- | :--- |
| **DeltaSafeStrategy (Baseline)** | -2.88 | -5.88% | 7.06% | 9 |
| **Experimental_Sentiment** | -2.73 | -5.70% | 6.29% | 8 |

## Conclusion
The `Experimental_Sentiment` strategy showed a slight improvement over the baseline `DeltaSafeStrategy` in all key metrics (Sharpe, Profit, Drawdown).
- Sharpe Ratio improved from -2.88 to -2.73.
- Net Profit improved from -5.88% to -5.70%.
- Max Drawdown reduced from 7.06% to 6.29%.

**Holy Grail Check:** Failed. Sharpe Ratio is -2.73 (< 3.0). The strategy is still unprofitable in the tested market conditions.
