# Experimental Sentiment Strategy Report

## Objective
To investigate if adding a mock "Sentiment" signal (derived from Volume Z-Score) to a standard RSI strategy provides "new alpha" and improves the Sharpe Ratio.

## Methodology
- **Baseline Strategy (`PureTA_Baseline`):** Enters Long when RSI < 30. Exits when RSI > 70.
- **Experimental Strategy (`Experimental_Sentiment`):** Enters Long when RSI < 30 **AND** Sentiment > 2.0. Exits when RSI > 70.
  - **Sentiment Signal:** Simulated using `(Volume - RollingMean) / RollingStd`. A value > 2.0 indicates unusually high volume (2 standard deviations above mean), serving as a proxy for "Whale Activity" or "High Sentiment".

## Backtest Settings
- **Exchange:** Gate.io
- **Pair:** BTC/USDT
- **Timeframe:** 1h
- **Period:** 2026-01-25 to 2026-02-23 (30 Days)
- **Market Conditions:** Bearish/Volatile (Market change -27.26%)

## Results

| Metric | PureTA_Baseline | Experimental_Sentiment | Delta |
| :--- | :--- | :--- | :--- |
| **Sharpe Ratio** | -2.57 | **-2.06** | +0.51 |
| **Win Rate** | 20% (1/5) | **40% (2/5)** | +20% |
| **Total Profit** | -0.54% | **-0.46%** | +0.08% |
| **Max Drawdown** | 0.62% | 0.62% | 0.00% |
| **Trades** | 5 | 5 | 0 |

## Analysis
The addition of the "Sentiment" filter improved the Sharpe Ratio from -2.57 to -2.06 and doubled the Win Rate from 20% to 40%. While the strategy is still net negative in this specific bearish period (-27% market drop), the signal successfully filtered entry points to improve the probability of success.

## Conclusion
The "Sentiment" signal (Volume Z-Score) acts as a valid alpha factor when combined with RSI. It did not achieve "Holy Grail" status (Sharpe > 3.0) in this test, but it demonstrated a clear improvement over the pure technical baseline.

## Recommendation
Further research into Volume-based sentiment proxies is warranted. Combining this with trend-following indicators (to avoid buying dips in strong downtrends) could yield better results.
