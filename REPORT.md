# Data Hunter Report: Experimental Sentiment Strategy

## Overview
This report analyzes the performance of a new experimental strategy, `Experimental_Sentiment`, which attempts to mock "Sentiment Analysis" and "On-Chain Metrics" using Money Flow Index (MFI) as a proxy for "Whale Wallet Movements" and Volume SMA as a proxy for "Twitter Volume".

The strategy was backtested against `DeltaSafeStrategy` (baseline) on `BTC/USDT` and `ETH/USDT` futures pairs from `2025-01-01` to `2026-02-20` (approx. 415 days).

## Results

| Metric | DeltaSafeStrategy (Baseline) | Experimental_Sentiment (New) | Change |
| :--- | :--- | :--- | :--- |
| **Total Profit %** | -35.04% | **-25.54%** | +9.5% |
| **Sharpe Ratio** | -1.51 | **-1.44** | +0.07 |
| **Max Drawdown** | 36.28% | **31.64%** | -4.64% |
| **Win Rate** | 79.2% | 74.5% | -4.7% |
| **Total Trades** | 183 | 361 | +178 |
| **Market Change** | -35.51% | -35.51% | 0% |

## Analysis
The market conditions during the backtest period were significantly bearish (-35.51% drop).
- The **Baseline Strategy** closely mirrored the market decline (-35.04%).
- The **New Strategy** outperformed the baseline and the market, reducing losses to -25.54%.
- The addition of "Whale" (MFI) and "Twitter" (Volume) signals increased trade frequency (361 vs 183 trades) and improved risk-adjusted returns (Sharpe -1.44 vs -1.51).
- While the Win Rate decreased slightly, the strategy managed to avoid deeper drawdowns better than the baseline.

## Conclusion
The `Experimental_Sentiment` strategy demonstrates potential alpha by outperforming the baseline in a bearish market. However, the Sharpe Ratio (-1.44) is far below the target of > 3.0 required for "Holy Grail" status. The strategy successfully mitigates some downside risk but requires further refinement or a more favorable market regime to become profitable.

**Recommendation**: Continue research into external signals. The simulated signals (MFI/Volume) showed promise. Integrating real external data (e.g., actual Twitter sentiment or on-chain data APIs) could further improve performance.
