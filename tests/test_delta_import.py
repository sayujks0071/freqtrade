
import sys
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

# Mock freqtrade dependencies to avoid full environment requirement if possible
# But better to rely on installed env.

try:
    # Add user_data strategies to path as freqtrade does
    strategy_path = Path("user_data/strategies")
    sys.path.append(str(strategy_path))

    # Try importing DeltaSafeStrategy
    # We need to simulate the environment where _base is in path
    # DeltaSafeStrategy does sys.path.append(str(Path(__file__).parent / "_base"))
    # So importing it should trigger that.

    # However, DeltaSafeStrategy relies on freqtrade modules.
    # We assume they are installed or available.

    from user_data.strategies.DeltaSafeStrategy import DeltaSafeStrategy
    print("Successfully imported DeltaSafeStrategy")

    # Instantiate
    config = {"stake_currency": "USDT", "minimal_roi": {}, "stoploss": -0.1, "timeframe": "5m"}
    strat = DeltaSafeStrategy(config=config)
    print("Successfully instantiated DeltaSafeStrategy")

except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
