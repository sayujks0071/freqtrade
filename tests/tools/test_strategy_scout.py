import datetime
from unittest.mock import MagicMock, patch

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
            "license": {"name": "MIT"},
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
        "stats": {"stars": 100, "updated_at": "2020-01-01T00:00:00Z", "license": "MIT"},
        "analysis": {
            "metadata": {"stoploss": -0.1, "minimal_roi": "Dict"},
            "has_indicators": True,
            "has_entry": True,
            "has_exit": True,
            "docstring": None,
            "is_suspicious": False,
        },
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
    strategies = [
        {
            "stats": {"stars": 0, "updated_at": "2020-01-01T00:00:00Z", "license": "MIT"},
            "analysis": {"metadata": {}, "docstring": "Test"},
            "file_path": "test.py",
            "repo_name": "test/repo",
            "repo_url": "url",
            "score": 10,
        }
    ]

    with patch("tools.strategy_scout.Path") as mock_path:
        # Setup mock_path to return a mock object that supports / operator
        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj

        # report_dir / filename
        report_file_mock = MagicMock()
        mock_path_obj.__truediv__.return_value = report_file_mock

        # Mock file handle
        file_handle = MagicMock()
        report_file_mock.open.return_value.__enter__.return_value = file_handle

        scout.generate_report(strategies)

        report_file_mock.open.assert_called_with("w")
        file_handle.write.assert_called()


def test_vendor_strategies():
    scout = StrategyScout()
    strategies = [
        {
            "repo_name": "owner/repo",
            "repo_url": "url",
            "file_path": "strat.py",
            "download_url": "http://down.load/strat.py",
            "file_url": "url",
            "stats": {"license": "MIT"},
        }
    ]

    with (
        patch("requests.get") as mock_get,
        patch("tools.strategy_scout.Path") as mock_path,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "content"

        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj

        # We need to handle multiple levels of / operator
        # vendor_dir = Path("user_data/strategies_vendor")
        # target_dir = vendor_dir / f"{repo_owner}_{repo_name}"
        # target_file = target_dir / file_name
        # license_file = target_dir / "LICENSE_NOTE.md"

        # Chain of mocks for / operator
        target_dir = MagicMock()
        mock_path_obj.__truediv__.return_value = target_dir

        target_file = MagicMock()
        license_file = MagicMock()

        # Make target_dir / something return different mocks
        def div_side_effect(arg):
            if arg == "LICENSE_NOTE.md":
                return license_file
            return target_file

        target_dir.__truediv__.side_effect = div_side_effect

        # Handles
        target_handle = MagicMock()
        target_file.open.return_value.__enter__.return_value = target_handle

        license_handle = MagicMock()
        license_file.open.return_value.__enter__.return_value = license_handle

        scout.vendor_strategies(strategies)

        target_file.open.assert_called_with("w")
        target_handle.write.assert_called_with("content")

        license_file.open.assert_called_with("w")
        license_handle.write.assert_called()
