import datetime
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest
from tools.strategy_scout import StrategyScout

# Sample data
SAMPLE_SEARCH_RESULT = {
    "items": [
        {
            "id": 1,
            "full_name": "test/repo1",
            "html_url": "https://github.com/test/repo1",
            "stargazers_count": 100,
            "forks_count": 10,
            "updated_at": "2023-01-01T00:00:00Z",
            "license": {"name": "MIT"}
        }
    ]
}

SAMPLE_STRATEGY_CODE = """
from freqtrade.strategy import IStrategy
import talib.abstract as ta

class MyStrategy(IStrategy):
    stoploss = -0.10
    minimal_roi = {"0": 0.2}
    timeframe = "5m"
    process_only_new_candles = True

    def populate_indicators(self, dataframe, metadata):
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        return dataframe
"""

SAMPLE_SUSPICIOUS_CODE = """
class MyStrategy(IStrategy):
    # This uses martingale
    pass
"""

def test_search_repos():
    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = SAMPLE_SEARCH_RESULT
        # Mock headers
        mock_get.return_value.headers = {"x-ratelimit-remaining": "10"}

        scout = StrategyScout()
        repos = scout.search_repos(["test"])

        assert len(repos) == 1
        assert repos[0]["full_name"] == "test/repo1"

def test_analyze_strategy_code():
    scout = StrategyScout()
    analysis = scout.analyze_strategy_code(SAMPLE_STRATEGY_CODE)

    assert analysis["is_strategy"] is True
    assert analysis["metadata"]["stoploss"] == -0.10
    assert analysis["metadata"]["timeframe"] == "5m"
    assert analysis["has_indicators"] is True
    assert analysis["has_entry"] is True
    assert analysis["has_exit"] is True
    assert analysis["is_suspicious"] is False

    # Test suspicious
    susp_analysis = scout.analyze_strategy_code(SAMPLE_SUSPICIOUS_CODE)
    # Note: parsing simple class without imports might work if valid syntax
    if susp_analysis:
        assert susp_analysis["is_suspicious"] is True

def test_score_strategy():
    scout = StrategyScout()

    # Case 1: Old strategy, but good features
    strategy = {
        "stats": {
            "stars": 100,
            "updated_at": "2020-01-01T00:00:00Z",
            "license": "MIT"
        },
        "analysis": {
            "metadata": {"stoploss": -0.1, "minimal_roi": "Dict"},
            "has_indicators": True,
            "has_entry": True,
            "has_exit": True,
            "docstring": None,
            "is_suspicious": False
        }
    }

    # Stars: 100 -> +1
    # Risk: SL+ROI -> +10
    # Content: Ind+Entry+Exit -> +7
    # Total: 18
    score = scout.score_strategy(strategy)
    assert score == 18

    # Case 2: Recent strategy
    now_str = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    strategy["stats"]["updated_at"] = now_str
    # Recency < 90 days -> +10
    # Total: 28
    score = scout.score_strategy(strategy)
    assert score == 28

def test_generate_report():
    scout = StrategyScout()
    strategies = [{
        "stats": {"stars": 0, "updated_at": "2020-01-01T00:00:00Z", "license": "MIT"},
        "analysis": {"metadata": {}, "docstring": "Test"},
        "file_path": "test.py",
        "repo_name": "test/repo",
        "repo_url": "url",
        "score": 10
    }]

    with patch("tools.strategy_scout.Path") as mock_path, \
         patch("builtins.open", mock_open()) as mock_file:

        # Setup mock_path to return a mock object that supports / operator
        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj
        mock_path_obj.__truediv__.return_value = MagicMock()

        scout.generate_report(strategies)

        mock_file.assert_called()
        handle = mock_file()
        handle.write.assert_called()

def test_vendor_strategies():
    scout = StrategyScout()
    strategies = [{
        "repo_name": "owner/repo",
        "repo_url": "url",
        "file_path": "strat.py",
        "download_url": "http://down.load/strat.py",
        "file_url": "url",
        "stats": {"license": "MIT"}
    }]

    with patch("requests.get") as mock_get, \
         patch("tools.strategy_scout.Path") as mock_path, \
         patch("builtins.open", mock_open()) as mock_file:

        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "content"

        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj
        mock_path_obj.__truediv__.return_value = MagicMock()

        scout.vendor_strategies(strategies)

        mock_file.assert_called()
        # Verify it wrote content and license
        assert mock_file.call_count >= 2
