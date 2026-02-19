import sys
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts to path to allow importing daily_optimize
# We assume the test is run from repo root
scripts_path = Path.cwd() / "scripts"
if str(scripts_path) not in sys.path:
    sys.path.append(str(scripts_path))

try:
    import daily_optimize
except ImportError:
    # If scripts/ is not in path correctly, try relative to file
    sys.path.append(str(Path(__file__).parent.parent / "scripts"))
    import daily_optimize


class TestDailyOptimize(unittest.TestCase):
    def test_find_worst_strategy(self):
        backtest_data = {
            "strategy": {
                "StratA": {"sharpe": 1.5, "max_drawdown_account": 0.1},
                "StratB": {"sharpe": 0.5, "max_drawdown_account": 0.2},
                "StratC": {"sharpe": 2.0, "max_drawdown_account": 0.05},
            }
        }
        name, sharpe, stats = daily_optimize.find_worst_strategy(backtest_data)
        self.assertEqual(name, "StratB")
        self.assertEqual(sharpe, 0.5)

    def test_find_worst_strategy_with_negative_sharpe(self):
        backtest_data = {
            "strategy": {
                "StratA": {"sharpe": -0.5, "max_drawdown_account": 0.1},
                "StratB": {"sharpe": -1.5, "max_drawdown_account": 0.2},
                "StratC": {"sharpe": 0.1, "max_drawdown_account": 0.05},
            }
        }
        name, sharpe, stats = daily_optimize.find_worst_strategy(backtest_data)
        self.assertEqual(name, "StratB")
        self.assertEqual(sharpe, -1.5)

    def test_extract_hyperopt_params(self):
        output = """
        Some logs...
        More logs...
        {
            "params": {
                "buy": {},
                "roi": {}
            }
        }
        Final logs...
        """
        params = daily_optimize.extract_hyperopt_params(output)
        self.assertIn("params", params)

    def test_extract_hyperopt_params_garbage(self):
        output = """
        No json here.
        Just text.
        """
        params = daily_optimize.extract_hyperopt_params(output)
        self.assertEqual(params, {})

    def test_improvement_logic_helpers(self):
        """
        Test the logic we intend to implement in daily_optimize.py
        This helps verify our proposed changes logic before applying them.
        """
        # Case 1: Positive Sharpe improvement
        current_sharpe = 1.0
        new_sharpe = 1.06
        # Logic: new > current and new > current * 1.05
        improved = (new_sharpe > current_sharpe) and (new_sharpe > current_sharpe * 1.05)
        self.assertTrue(improved)

        # Case 2: Negative Sharpe, not improved enough
        current_sharpe = -1.0
        new_sharpe = -1.02 # Worse than current (-1.0) but better than -1.05 target?
        # new > -1.05 is True.
        # But new > current is False (-1.02 < -1.0).
        improved = (new_sharpe > current_sharpe) and (new_sharpe > current_sharpe * 1.05)
        self.assertFalse(improved)

        # Case 3: Negative Sharpe, improved
        current_sharpe = -1.0
        new_sharpe = -0.9 # Better than -1.0
        # -0.9 > -1.0 is True.
        # -0.9 > -1.05 is True.
        improved = (new_sharpe > current_sharpe) and (new_sharpe > current_sharpe * 1.05)
        self.assertTrue(improved)

        # Case 4: Zero Drawdown
        current_dd = 0.0
        new_dd = 0.0
        # Logic: new < current if current > 0 else new <= current
        dd_improved = new_dd < current_dd if current_dd > 0 else new_dd <= current_dd
        self.assertTrue(dd_improved)

        # Case 5: Zero Drawdown, regression
        current_dd = 0.0
        new_dd = 0.01
        dd_improved = new_dd < current_dd if current_dd > 0 else new_dd <= current_dd
        self.assertFalse(dd_improved)

if __name__ == "__main__":
    unittest.main()
