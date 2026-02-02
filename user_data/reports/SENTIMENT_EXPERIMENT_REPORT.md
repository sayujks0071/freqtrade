# Sentiment Analysis Strategy Experiment

## Objective
To test whether a "mocked" sentiment signal derived from volume data can provide alpha compared to a pure technical analysis baseline (`DeltaSafeStrategy`).

## Methodology
- **Strategy:** `Experimental_Sentiment`
- **Signal:** Deterministic pseudo-random value based on volume.
  - Formula: `sentiment = (volume % 1000) / 1000.0`
- **Logic:**
  - Entry: `sentiment > 0.8` (Simulating high positive sentiment/hype)
  - Exit: `sentiment < 0.2` (Simulating negative sentiment)
- **Baseline:** `DeltaSafeStrategy` (RSI-based mean reversion)
- **Data:** 1h timeframe on Gate.io (BTC/USDT, ETH/USDT)

## Results (Backtest: 2025-11-05 to 2026-02-02)

| Metric | Experimental_Sentiment | DeltaSafeStrategy (Baseline) |
| :--- | :--- | :--- |
| **Total Profit %** | -7.41% | -4.47% |
| **Sharpe Ratio** | -14.84 | -2.40 |
| **Drawdown** | 7.66% | 5.01% |
| **Win Rate** | 44.8% | 79.5% |

## Conclusion
The experimental strategy using a mocked sentiment signal significantly underperformed the baseline. The signal derived from `volume % 1000` acts as random noise, leading to frequent, unprofitable trades compared to the more structured RSI-based entry of the baseline.

**Recommendation:** Do not deploy `Experimental_Sentiment` in its current form. Further research into *actual* sentiment data (Twitter API, On-chain analytics) is required to replace the mock signal.

## Notes
- During testing, a syntax error in `user_data/strategies/_base/AuditedStrategyMixin.py` (duplicate arguments in `log_signal`) was identified and fixed to enable backtesting.
