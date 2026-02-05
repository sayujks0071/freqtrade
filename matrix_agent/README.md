# Matrix Agent - Crypto Trading System

## Overview

Matrix Agent is a **survivorship-focused crypto trading system** implementing an 8-layer architecture designed to maximize long-term expected returns while minimizing risk through strict discipline and systematic decision-making.

### Core Philosophy

```
"I am not here to trade. I am here to reject most trades."
```

The system operates on four non-negotiable principles:

1. **Survival > Profit** - Preserve capital at all costs
2. **Asymmetry > Win Rate** - Focus on risk/reward, not winning percentage
3. **NO TRADE is a successful decision** - Missing opportunities is acceptable
4. **Expected R < 3 → Mandatory NO TRADE** - High threshold for entry

## System Architecture

```
Environment (Market)
  ↓
Layer 1: Macro Gatekeeper (4H / 1D)     [VETO POWER]
  ↓
Layer 2: Anti-Consensus Filter           [VALIDATION]
  ↓
Layer 3: Liquidity Hunter (SFP Hunter)  [DIRECTION]
  ↓
Layer 4: Committee Decision              [VOTING]
  ↓
Layer 5: Minimax Executor                [EXECUTION]
  ↓
Layer 6: Risk Governor                   [PROTECTION]
  ↓
Layer 7: Reward Engine                   [LEARNING]
  ↓
Layer 8: Weekly Review Agent             [REVIEW]
```

## Installation

```bash
# Clone or navigate to the project directory
cd /Users/mac/freq

# Install dependencies
pip install numpy pandas TA-Lib technical

# The Matrix Agent core is included in matrix_agent/
```

## Quick Start

```python
from matrix_agent.core import MatrixAgent

# Initialize the agent
agent = MatrixAgent()

# Analyze a trading pair
signal = agent.analyze_market("BTC/USDT")

if signal.decision.value == "approve":
    print(f"Trade approved: {signal.direction.value}")
    print(f"Entry: {signal.entry_price:.4f}")
    print(f"Stop: {signal.stop_loss:.4f}")
    print(f"TP1: {signal.take_profit_1:.4f}")
    print(f"Expected R: {signal.expected_r:.2f}")

    # Execute the trade
    result = agent.execute_trade(signal)
else:
    print(f"Trade rejected: {signal.rejection_reason}")

# Batch analyze multiple pairs
signals = agent.batch_analyze(["BTC/USDT", "ETH/USDT", "SOL/USDT"])

# Get system status
status = agent.get_system_status()
print(f"System Status: {status['system_status']}")
print(f"Total Trades: {status['total_trades']}")
print(f"Acceptance Rate: {status['acceptance_rate']*100:.1f}%")

# Clean up
agent.close()
```

## Layer Details

### Layer 1: Macro Gatekeeper (Veto Layer)

Determines if a trade is worth being swept based on macro conditions:

**Approved Conditions (any one triggers approval):**
- Clear trend + RSI pullback zone (40-45 / 55-60)
- Extreme Funding (≤ -0.03% or ≥ +0.05%)
- Price at high/low/liquidity edge

**Rejected Conditions:**
- RSI ≈ 50 (neutral zone)
- Price in range middle
- Mild positive Funding with rising trend

### Layer 2: Anti-Consensus Filter

Evaluates market consensus to avoid trading with the crowd:

- High consensus → Raise Expected R threshold to ≥ 4
- Prohibit chasing price
- Only allow SFP reversal at high consensus

### Layer 3: Liquidity Hunter (SFP Detector)

**The ONLY allowed entry logic: SFP (Swing Failure Pattern)**

**Bullish SFP:**
1. Price breaks below key prior low (liquidity grab)
2. Candle low < that low point
3. Close price recovers above that low point

**Bearish SFP:**
1. Price breaks above key prior high (liquidity grab)
2. Candle high > that high point
3. Close price drops back below that high point

### Layer 4: Committee Decision

Multi-agent voting system:

| Agent | Weight | Power |
|-------|--------|-------|
| Macro Agent | 30% | Veto |
| Risk Agent | 30% | Veto |
| Liquidity Agent | 25% | Direction |
| Anti-Consensus Agent | 15% | Validation |

### Layer 5: Minimax Executor

Game theory execution answering two questions:

1. **Worst Case:** Maximum I can lose?
2. **Best Case:** Maximum I can gain?

**Conditions:**
- Expected R ≥ 3 (high consensus ≥ 4)
- Stop Loss = Outside SFP extreme
- Risk ≤ 1% of account

### Layer 6: Risk Governor

**Hard Rules (Non-Negotiable):**
- Single trade risk ≤ 1%
- Maximum position ≤ 20%
- Drawdown > 5% → Auto reduce frequency
- Drawdown > 8% → Forced NO TRADE

### Layer 7: Reward Engine

Post-trade reinforcement learning:

- **Reward** whether worth betting, not whether profitable
- **Reward** NO TRADE decisions
- **Penalize** non-A+ executions

### Layer 8: Weekly Review Agent

**Must execute every 7 days:**

Checklist:
1. Is NO TRADE ratio ≥ 60%?
2. Were there any non-A+ executions?
3. Is A+ average Expected R ≥ 3?
4. Which pattern contributed most profit?

**Red Line Mechanism:**
- Non-A+ executions ≥ 2 → System degradation warning
- 2 consecutive weeks A+ failure → SAFE MODE

## Configuration

### Default Configuration

```python
config = {
    # SFP Detection
    'sfp_config': {
        'swing_period': 5,
        'min_swing_strength': 0.5,
        'confirmation_bars': 1,
        'tolerance_pct': 0.001
    },

    # Macro Analysis
    'macro_config': {
        'rsi_bullish_low': 40,
        'rsi_bullish_high': 45,
        'rsi_bearish_low': 55,
        'rsi_bearish_high': 60,
        'extreme_funding_short': -0.0003,
        'extreme_funding_long': 0.0005
    },

    # Risk Management
    'risk_config': {
        'max_position_pct': 0.20,
        'single_trade_risk_pct': 0.01,
        'warning_drawdown_pct': 0.05,
        'critical_drawdown_pct': 0.08
    },

    # Trading Pairs
    'trading_pairs': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
}
```

## Output Format

### EXECUTE_TRADE

```
EXECUTE_LONG / EXECUTE_SHORT
Entry: [price]
Stop: [price]
TP1: [price]
TP2: [price]
Expected R: [ratio]
Reason: [Structured explanation covering Macro + Liquidity + Risk + Consensus]
```

### NO_TRADE

```
NO TRADE
Reason: [Macro / Liquidity / Risk / Consensus - specify which layer rejected]
```

## Performance Tracking

### Key Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| NO TRADE Ratio | ≥ 60% | Discipline indicator |
| A+ Execution Rate | ≥ 70% | Quality indicator |
| Average Expected R | ≥ 3.0 | Asymmetry indicator |
| Win Rate | ≥ 30% | Secondary metric |
| Profit Factor | ≥ 1.5 | Risk-adjusted returns |
| Max Drawdown | ≤ 8% | Risk control |

### Performance Dashboard

```python
# Get performance metrics
metrics = agent.get_performance_metrics()

print(f"Total Trades: {metrics['total_trades']}")
print(f"Win Rate: {metrics['win_rate']*100:.1f}%")
print(f"Profit Factor: {metrics['profit_factor']:.2f}")
print(f"NO TRADE Ratio: {metrics['no_trade_ratio']*100:.1f}%")
print(f"A+ Ratio: {metrics['a_plus_ratio']*100:.1f}%")
print(f"Avg Expected R: {metrics['avg_expected_r']:.2f}")
```

## Integration with FreqTrade

The Matrix Agent can integrate with existing FreqTrade installations:

```python
from matrix_agent.integrations import MatrixFreqTradeStrategy

# Create custom strategy inheriting from Matrix Agent
class MatrixStrategy(MatrixFreqTradeStrategy):
    pass
```

## Safety Features

### Safe Mode Activation

Safe mode is automatically activated when:
- Drawdown exceeds 15%
- 2 consecutive weekly reviews fail
- Manual trigger via API

### Forced NO TRADE Conditions

The system will force NO TRADE when:
- Drawdown > 10%
- Max positions (3) reached
- System in safe mode
- Any layer vetoes the trade

## Best Practices

1. **Start with paper trading** - Test the system without real funds
2. **Monitor weekly reviews** - Review performance every Sunday
3. **Maintain discipline** - Never override committee decisions
4. **Adjust incrementally** - Change one parameter at a time
5. **Keep records** - Track all trades and decisions

## Common Issues

### Low Acceptance Rate

If acceptance rate is too low:
- Check macro conditions
- Verify SFP detection is working
- Review consensus levels

### High Drawdown

If drawdown exceeds limits:
- Reduce position sizes
- Increase Expected R threshold
- Enable safe mode

### Poor Win Rate

If win rate is too low:
- This is expected (system aims for asymmetry)
- Focus on Expected R and profit factor
- Review A+ execution quality

## Contributing

To contribute to Matrix Agent:

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit pull request

## License

Matrix Agent is open source software licensed under MIT License.

## Support

For issues and questions:
- Check the documentation
- Review weekly reports
- Enable debug logging for detailed analysis

---

**Remember: "I am not here to trade. I am here to reject most trades."**
