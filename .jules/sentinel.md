# Sentinel Journal

This log tracks all critical events triggered by the Sentinel circuit breaker.

## Usage
Run the Sentinel alongside your Freqtrade bot:
```bash
python3 scripts/sentinel.py --config user_data/configs/config.delta.live.json
```

## Emergency Triggers
1. **Drawdown > 5% in 1 hour**: Protects against rapid account depletion.
2. **Bitcoin Drop > 10% in 4 hours**: Protects against market crashes.

## Log
