import sys
import unittest
from pathlib import Path


# Add scripts to path
sys.path.append(str(Path(__file__).parent.parent.parent / "scripts"))
import daily_optimize  # noqa: E402; isort: skip


class TestDailyOptimize(unittest.TestCase):
    def test_extract_hyperopt_params(self):
        output = """
Some logs...
More logs...
{
    "params": {
        "buy_rsi": 30
    },
    "minimal_roi": {
        "0": 0.1
    }
}
Final logs...
"""
        params = daily_optimize.extract_hyperopt_params(output)
        self.assertIn("params", params)
        self.assertEqual(params["params"]["buy_rsi"], 30)

    def test_extract_hyperopt_params_nested(self):
        # Freqtrade output format
        output = """
Best result:
{
    "strategy_name": "MyStrategy",
    "params": {
      "buy": {
        "rsi": 30
      }
    },
    "minimal_roi": {
      "0": 0.05
    }
}
"""
        params = daily_optimize.extract_hyperopt_params(output)
        self.assertIn("params", params)

    def test_find_worst_strategy(self):
        backtest_data = {
            "strategy": {
                "StratA": {"sharpe": 1.5, "max_drawdown_account": 0.1},
                "StratB": {"sharpe": 0.5, "max_drawdown_account": 0.2},  # Worst
                "StratC": {"sharpe": 2.0, "max_drawdown_account": 0.05},
            }
        }
        name, sharpe, _ = daily_optimize.find_worst_strategy(backtest_data)
        self.assertEqual(name, "StratB")
        self.assertEqual(sharpe, 0.5)

    def test_find_worst_strategy_none_sharpe(self):
        backtest_data = {
            "strategy": {
                "StratA": {
                    "sharpe": None,
                    "max_drawdown_account": 0.1,
                },  # Should be treated as -inf
                "StratB": {"sharpe": 0.5, "max_drawdown_account": 0.2},
            }
        }
        name, sharpe, _ = daily_optimize.find_worst_strategy(backtest_data)
        self.assertEqual(name, "StratA")
        self.assertEqual(sharpe, -float("inf"))


if __name__ == "__main__":
    unittest.main()
