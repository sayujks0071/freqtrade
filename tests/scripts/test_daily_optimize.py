
import sys
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

# Add scripts directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / 'scripts'))

import daily_optimize

def test_find_worst_strategy():
    backtest_data = {
        "strategy": {
            "StratA": {"sharpe": 2.0, "max_drawdown_account": 0.1},
            "StratB": {"sharpe": 1.0, "max_drawdown_account": 0.2},
            "StratC": {"sharpe": 3.0, "max_drawdown_account": 0.05}
        }
    }

    name, sharpe, stats = daily_optimize.find_worst_strategy(backtest_data)

    assert name == "StratB"
    assert sharpe == 1.0
    assert stats["max_drawdown_account"] == 0.2

def test_find_worst_strategy_empty():
    backtest_data = {"strategy": {}}
    name, sharpe, stats = daily_optimize.find_worst_strategy(backtest_data)
    assert name is None
    assert sharpe == -float("inf")
    assert stats is None

def test_extract_hyperopt_params():
    output = """
    Some output...
    Best result:
    {
        "params": {
            "buy": {"buy_rsi": 30},
            "roi": {"0": 0.1}
        }
    }
    """
    params = daily_optimize.extract_hyperopt_params(output)
    assert params["buy"]["buy_rsi"] == 30
    assert params["roi"]["0"] == 0.1

def test_evaluate_improvement_pass():
    # New Sharpe > 1.05 * Old Sharpe AND New DD < Old DD
    current_sharpe = 1.0
    current_dd = 0.2
    new_sharpe = 1.1  # 1.1 > 1.05
    new_dd = 0.15     # 0.15 < 0.2

    assert daily_optimize.evaluate_improvement(current_sharpe, current_dd, new_sharpe, new_dd) is True

def test_evaluate_improvement_fail_sharpe():
    current_sharpe = 1.0
    current_dd = 0.2
    new_sharpe = 1.04 # 1.04 < 1.05
    new_dd = 0.15

    assert daily_optimize.evaluate_improvement(current_sharpe, current_dd, new_sharpe, new_dd) is False

def test_evaluate_improvement_fail_drawdown():
    current_sharpe = 1.0
    current_dd = 0.2
    new_sharpe = 1.1
    new_dd = 0.21     # 0.21 > 0.2

    assert daily_optimize.evaluate_improvement(current_sharpe, current_dd, new_sharpe, new_dd) is False

def test_evaluate_improvement_fail_both():
    current_sharpe = 1.0
    current_dd = 0.2
    new_sharpe = 1.0
    new_dd = 0.25

    assert daily_optimize.evaluate_improvement(current_sharpe, current_dd, new_sharpe, new_dd) is False

@patch('daily_optimize.get_latest_backtest_file')
@patch('daily_optimize.get_all_strategy_names')
@patch('daily_optimize.read_backtest_result')
def test_establish_baseline_existing_full(mock_read, mock_get_strategies, mock_get_file):
    mock_get_file.return_value = Path("dummy.json")
    mock_get_strategies.return_value = ["StratA"]
    mock_read.return_value = {
        "strategy": {
            "StratA": {"sharpe": 1.5, "max_drawdown_account": 0.1}
        }
    }

    name, sharpe, dd = daily_optimize.establish_baseline()

    assert name == "StratA"
    assert sharpe == 1.5
    assert dd == 0.1

@patch('daily_optimize.get_latest_backtest_file')
@patch('daily_optimize.run_backtest_job')
@patch('daily_optimize.get_all_strategy_names')
def test_establish_baseline_no_existing(mock_get_strategies, mock_run_backtest, mock_get_file):
    mock_get_file.return_value = None
    mock_get_strategies.return_value = ["StratA", "StratB"]
    mock_run_backtest.return_value = {
        "strategy": {
            "StratA": {"sharpe": 2.0, "max_drawdown_account": 0.1},
            "StratB": {"sharpe": 1.0, "max_drawdown_account": 0.2}
        }
    }

    name, sharpe, dd = daily_optimize.establish_baseline()

    # StratB is worse
    assert name == "StratB"
    assert sharpe == 1.0
    assert dd == 0.2
    mock_run_backtest.assert_called_with(["StratA", "StratB"])

@patch('daily_optimize.get_latest_backtest_file')
@patch('daily_optimize.run_backtest_job')
@patch('daily_optimize.get_all_strategy_names')
@patch('daily_optimize.read_backtest_result')
def test_establish_baseline_partial_results(mock_read, mock_get_strategies, mock_run_backtest, mock_get_file):
    mock_get_file.return_value = Path("partial.json")
    mock_get_strategies.return_value = ["StratA", "StratB"]
    # File only has StratA
    mock_read.return_value = {
        "strategy": {
            "StratA": {"sharpe": 1.5, "max_drawdown_account": 0.1}
        }
    }

    # Mock return of the FULL backtest
    mock_run_backtest.return_value = {
        "strategy": {
            "StratA": {"sharpe": 1.5, "max_drawdown_account": 0.1},
            "StratB": {"sharpe": 0.5, "max_drawdown_account": 0.3}
        }
    }

    name, sharpe, dd = daily_optimize.establish_baseline()

    # It should have re-run backtest on ALL strategies
    mock_run_backtest.assert_called_with(["StratA", "StratB"])

    # And picked StratB as the worst
    assert name == "StratB"
    assert sharpe == 0.5
    assert dd == 0.3
