import unittest
import pandas as pd
import sys
from pathlib import Path

# Add scripts to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

try:
    from regime_switcher import calculate_indicators, determine_regime, STRATEGY_BULL, STRATEGY_SIDEWAYS, STRATEGY_VOLATILE
except ImportError:
    # Fallback if running from root
    sys.path.append("scripts")
    from regime_switcher import calculate_indicators, determine_regime, STRATEGY_BULL, STRATEGY_SIDEWAYS, STRATEGY_VOLATILE

class TestRegimeSwitcher(unittest.TestCase):
    def test_calculate_indicators(self):
        # We need more data for EMA200
        df = pd.DataFrame({
            "close": [100 + i for i in range(300)],
            "high": [105 + i for i in range(300)],
            "low": [95 + i for i in range(300)],
            "open": [100 + i for i in range(300)],
            "volume": [1000] * 300
        })
        df = calculate_indicators(df)
        self.assertIn("EMA_200", df.columns)
        # Check for ADX column (pandas_ta names might vary, logic handles it but let's check basic existence)
        self.assertTrue(any(col.startswith("ADX") for col in df.columns))
        self.assertIn("volatility_spike", df.columns)

    def test_determine_regime_bull(self):
        row = {
            "close": 50000,
            "EMA_200": 40000,
            "ADX_14": 30,
            "volatility_spike": False
        }
        regime, strategy = determine_regime(row)
        self.assertEqual(strategy, STRATEGY_BULL)

    def test_determine_regime_sideways(self):
        row = {
            "close": 40000,
            "EMA_200": 40000,
            "ADX_14": 15,
            "volatility_spike": False
        }
        regime, strategy = determine_regime(row)
        self.assertEqual(strategy, STRATEGY_SIDEWAYS)

    def test_determine_regime_volatile(self):
        row = {
            "close": 30000,
            "EMA_200": 40000,
            "ADX_14": 40,
            "volatility_spike": True
        }
        regime, strategy = determine_regime(row)
        self.assertEqual(strategy, STRATEGY_VOLATILE)

    def test_determine_regime_weak_bear(self):
        # Price < EMA200 but no spike -> Weak Bear -> Volatile Strategy (default for Bear)
        row = {
            "close": 35000,
            "EMA_200": 40000,
            "ADX_14": 20, # > 20 but not volatile spike
            "volatility_spike": False
        }
        regime, strategy = determine_regime(row)
        self.assertEqual(strategy, STRATEGY_VOLATILE)

if __name__ == "__main__":
    unittest.main()
