import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add scripts directory to path to import daily_optimize
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
import daily_optimize


def test_find_worst_strategy():
    backtest_data = {
        "strategy": {
            "StrategyA": {"sharpe": 1.5, "max_drawdown_account": 0.1},
            "StrategyB": {"sharpe": 0.5, "max_drawdown_account": 0.2},
            "StrategyC": {"sharpe": 2.0, "max_drawdown_account": 0.05},
        }
    }

    worst, sharpe, stats = daily_optimize.find_worst_strategy(backtest_data)
    assert worst == "StrategyB"
    assert sharpe == 0.5
    assert stats["max_drawdown_account"] == 0.2

def test_find_worst_strategy_empty():
    worst, sharpe, stats = daily_optimize.find_worst_strategy({})
    assert worst is None
    assert sharpe is None
    assert stats is None

def test_extract_hyperopt_params_single_line():
    output = 'Best result:\n{"params": {"a": 1}, "minimal_roi": {}}\n'
    params = daily_optimize.extract_hyperopt_params(output)
    assert params["params"]["a"] == 1

def test_extract_hyperopt_params_multi_line():
    output = """
Best result:
{
    "params": {
        "b": 2
    },
    "minimal_roi": {}
}
Some logs after
"""
    params = daily_optimize.extract_hyperopt_params(output)
    assert params["params"]["b"] == 2

def test_extract_hyperopt_params_nested_braces():
    output = """
Best result:
{
    "params": {
        "c": { "d": 3 }
    },
    "minimal_roi": {}
}
"""
    params = daily_optimize.extract_hyperopt_params(output)
    assert params["params"]["c"]["d"] == 3

def test_extract_hyperopt_params_mixed_logs():
    output = """
Best result:
{"params": {"e": 5}, "minimal_roi": {}}
2026-02-24 12:00:00 - ... AUDIT_SIGNAL ...
"""
    params = daily_optimize.extract_hyperopt_params(output)
    assert params["params"]["e"] == 5

def test_strategy_has_parameters(tmp_path):
    # Mock STRATEGIES_DIR
    original_strategies_dir = daily_optimize.STRATEGIES_DIR
    daily_optimize.STRATEGIES_DIR = tmp_path

    try:
        (tmp_path / "TestStrat.py").write_text("class TestStrat(IStrategy):\n    buy_params = IntParameter(1, 10)")
        assert daily_optimize.strategy_has_parameters("TestStrat") is True

        (tmp_path / "NoParamStrat.py").write_text("class NoParamStrat(IStrategy):\n    pass")
        assert daily_optimize.strategy_has_parameters("NoParamStrat") is False

    finally:
        daily_optimize.STRATEGIES_DIR = original_strategies_dir
