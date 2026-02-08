import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add tools directory to path to import strategy_scout
sys.path.append(str(Path(__file__).parent.parent / "tools"))

from strategy_scout import StrategyScout, extract_strategy_details  # noqa: E402, RUF100


class TestStrategyScout(unittest.TestCase):
    def test_extract_strategy_details(self):
        content = """
class MyStrategy(IStrategy):
    timeframe = '5m'
    stoploss = -0.10
    minimal_roi = {"0": 0.2}
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 100

    def populate_indicators(self, dataframe, metadata):
        pass
"""
        details = extract_strategy_details(content)
        self.assertEqual(details["timeframe"], "5m")
        self.assertEqual(details["stoploss"], -0.10)
        self.assertEqual(details["can_short"], True)
        self.assertEqual(details["process_only_new_candles"], True)
        self.assertEqual(details["startup_candle_count"], 100)
        self.assertTrue(details["populate_indicators"])
        self.assertTrue(details["has_class"])

    def test_extract_strategy_details_no_class(self):
        content = """
def my_func():
    pass
"""
        details = extract_strategy_details(content)
        self.assertFalse(details["has_class"])

    @patch("strategy_scout.requests.Session")
    def test_search_github(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        # Mock rate limit check
        mock_session.get.return_value.status_code = 200

        # We need to mock the responses for search queries + known sources
        # Total calls:
        # 4 queries * (1 rate limit + 1 search) = 8 calls
        # 1 known source * (1 rate limit + 1 repo fetch) = 2 calls
        # However, check_rate_limit might be called more or less depending on implementation details

        # Instead of list side_effect which is brittle, let's use a function based on URL
        def side_effect(url, **kwargs):
            if "rate_limit" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: {"resources": {"core": {"remaining": 50, "reset": 1234567890}}},
                )
            if "search/repositories" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: {
                        "items": [
                            {
                                "full_name": "user/repo1",
                                "stargazers_count": 100,
                                "description": "freqtrade strategy",
                                "pushed_at": "2023-01-01T00:00:00Z",
                            }
                        ]
                    },
                )
            if "repos/freqtrade/freqtrade-strategies" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: {
                        "full_name": "freqtrade/freqtrade-strategies",
                        "stargazers_count": 500,
                        "description": "Official",
                        "pushed_at": "2023-01-01T00:00:00Z",
                    },
                )
            return MagicMock(status_code=404)

        mock_session.get.side_effect = side_effect

        scout = StrategyScout()
        scout.search_github()

        self.assertTrue(len(scout.candidates) >= 1)
        found_names = [c["full_name"] for c in scout.candidates]
        self.assertIn("user/repo1", found_names)
        self.assertIn("freqtrade/freqtrade-strategies", found_names)

    @patch("strategy_scout.requests.Session")
    @patch("strategy_scout.requests.get")
    def test_deep_inspect_and_score(self, mock_get, mock_session_cls):
        mock_session = mock_session_cls.return_value

        # Setup candidates
        scout = StrategyScout()
        repo = {
            "full_name": "user/repo1",
            "stargazers_count": 100,
            "description": "freqtrade strategy",
            "html_url": "http://github.com/user/repo1",
            "pushed_at": "2023-01-01T00:00:00Z",
            "license": {"key": "mit", "name": "MIT License"},
        }
        scout.candidates = [repo]

        # Mock session get for find_strategy_files
        def side_effect(url, **kwargs):
            if "rate_limit" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: {"resources": {"core": {"remaining": 50, "reset": 1234567890}}},
                )
            if "contents/user_data/strategies" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: [{"name": "MyStrat.py", "download_url": "http://dl.url"}],
                )
            return MagicMock(status_code=404)

        mock_session.get.side_effect = side_effect

        # Mock download content
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = """
class MyStrat(IStrategy):
    stoploss = -0.05
    can_short = True
    timeframe = '5m'
"""

        scout.filter_and_score()  # Initialize fields
        scout.deep_inspect(limit=1)

        updated_repo = scout.candidates[0]
        self.assertIn("Futures (can_short=True)", updated_repo["scout_notes"])
        self.assertEqual(updated_repo["strategy_details"]["timeframe"], "5m")
        # Base score checks
        # Recency: > 365 days -> -2
        # Description: +2
        # Strategies found: +1
        # Stoploss: +2
        # Can Short: +3
        # Timeframe: +1
        # Total approx: 7
        self.assertTrue(updated_repo["scout_score"] > 0)


if __name__ == "__main__":
    unittest.main()
