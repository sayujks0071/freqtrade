import ast
import datetime
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add repo root to sys.path to allow importing from tools
sys.path.append(str(Path.cwd()))  # noqa: E402

from tools.strategy_scout import StrategyScout, StrategyVisitor


class TestStrategyVisitor:
    def test_visit_assign_simple(self):
        code = """
timeframe = '5m'
stoploss = -0.10
can_short = True
process_only_new_candles = True
minimal_roi = { "0": 1 }
"""
        tree = ast.parse(code)
        visitor = StrategyVisitor()
        visitor.visit(tree)

        assert visitor.metadata["timeframe"] == "5m"
        assert visitor.metadata["stoploss"] == -0.10
        assert visitor.metadata["can_short"] is True
        assert visitor.metadata["process_only_new_candles"] is True
        assert visitor.metadata["minimal_roi"] is True

    def test_visit_class_attributes(self):
        code = """
class MyStrategy(IStrategy):
    timeframe = '1h'
    stoploss = -0.05
    can_short = False

    def populate_indicators(self, dataframe, metadata):
        pass
"""
        tree = ast.parse(code)
        visitor = StrategyVisitor()
        visitor.visit(tree)

        assert visitor.metadata["timeframe"] == "1h"
        assert visitor.metadata["stoploss"] == -0.05
        assert visitor.metadata["can_short"] is False
        assert visitor.metadata["populate_indicators"] is True

    def test_visit_unary_stoploss(self):
        code = "stoploss = -0.2"
        tree = ast.parse(code)
        visitor = StrategyVisitor()
        visitor.visit(tree)
        assert visitor.metadata["stoploss"] == -0.2

    def test_visit_annotated_assign(self):
        code = """
timeframe: str = '15m'
stoploss: float = -0.1
"""
        tree = ast.parse(code)
        visitor = StrategyVisitor()
        visitor.visit(tree)
        assert visitor.metadata["timeframe"] == "15m"
        assert visitor.metadata["stoploss"] == -0.1


class TestStrategyScout:
    @pytest.fixture
    def scout(self):
        # Create scout but replace session with a mock immediately
        s = StrategyScout(token="dummy_token")
        s.session = MagicMock()
        return s

    def test_check_rate_limit_ok(self, scout):
        scout.session.get.return_value.status_code = 200
        scout.session.get.return_value.json.return_value = {
            "resources": {"core": {"remaining": 50, "reset": 1234567890}}
        }
        assert scout.check_rate_limit() is True

    def test_check_rate_limit_low(self, scout):
        scout.session.get.return_value.status_code = 200
        scout.session.get.return_value.json.return_value = {
            "resources": {"core": {"remaining": 0, "reset": 1234567890}}
        }
        # It should return False
        assert scout.check_rate_limit() is False

    def test_search_github(self, scout):
        # Mock search response
        scout.session.get.return_value.status_code = 200
        scout.session.get.return_value.json.return_value = {
            "items": [
                {"full_name": "user/repo1", "stargazers_count": 100},
                {"full_name": "user/repo2", "stargazers_count": 50},
            ]
        }
        # Mock rate limit check to always return True
        with patch.object(scout, "check_rate_limit", return_value=True):
            scout.search_github()

        assert len(scout.candidates) >= 2

    def test_filter_and_score(self, scout):
        recent_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        scout.candidates = [
            {
                "full_name": "user/good_repo",
                "stargazers_count": 100,
                "license": {"key": "mit", "name": "MIT"},
                "pushed_at": recent_date,
                "description": "A freqtrade strategy",
            },
            {
                "full_name": "user/bad_repo",
                "stargazers_count": 0,
                "license": None,  # Should be filtered out unless known source
                "pushed_at": recent_date,
                "description": "No description",
            },
        ]

        scout.filter_and_score()

        filtered_names = [c["full_name"] for c in scout.candidates]
        assert "user/good_repo" in filtered_names
        assert "user/bad_repo" not in filtered_names

        good_repo = next(c for c in scout.candidates if c["full_name"] == "user/good_repo")
        # +5 license, +2 desc, +5 recency = 12
        assert good_repo["scout_score"] >= 12

    @patch("tools.strategy_scout.requests.get")
    def test_deep_inspect(self, mock_get, scout):
        scout.candidates = [{"full_name": "user/repo1", "scout_score": 10, "scout_notes": []}]

        # Mock _find_strategy_files response
        # The first call is _find_strategy_files, which uses self.session.get
        # The second call is _analyze_strategy_content, which uses requests.get (mocked as mock_get)

        scout.session.get.return_value.status_code = 200
        scout.session.get.return_value.json.return_value = [
            {"name": "Strat.py", "download_url": "http://url"}
        ]

        # Mock content download
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "timeframe = '5m'\nstoploss = -0.1"

        with patch.object(scout, "check_rate_limit", return_value=True):
            scout.deep_inspect(limit=1)

        repo = scout.candidates[0]
        assert repo["strategy_count"] == 1
        assert repo["extracted_metadata"]["timeframe"] == "5m"
        assert repo["extracted_metadata"]["stoploss"] == -0.1
        assert "Stoploss: -0.1" in repo["scout_notes"]

    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_generate_report(self, mock_mkdir, mock_file, scout):
        scout.candidates = [
            {
                "full_name": "user/repo1",
                "html_url": "http://github.com/user/repo1",
                "scout_score": 20,
                "stargazers_count": 100,
                "license_name": "MIT",
                "strategy_count": 1,
                "pushed_at": "2023-10-01T00:00:00Z",
                "description": "Best Strat",
                "extracted_metadata": {
                    "timeframe": "5m",
                    "stoploss": -0.1,
                    "can_short": True,
                },
                "scout_notes": ["Good"],
            }
        ]

        scout.generate_report()

        mock_mkdir.assert_called()
        mock_file.assert_called()
        handle = mock_file()
        handle.write.assert_any_call("## Top 10 Candidates\n\n")
        handle.write.assert_any_call("- **Score:** 20\n")

    @patch("tools.strategy_scout.requests.get")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_vendor_strategies(self, mock_mkdir, mock_file, mock_get, scout):
        candidates = [
            {
                "full_name": "user/repo1",
                "name": "repo1",
                "html_url": "url",
                "license_name": "MIT",
                "strategy_path": "strategies",
            }
        ]

        # Mock list contents
        scout.session.get.return_value.status_code = 200
        scout.session.get.return_value.json.return_value = [
            {"name": "Strat.py", "download_url": "http://down"}
        ]

        # Mock file download
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "code"

        scout.vendor_strategies(candidates)

        mock_mkdir.assert_called()
        # Check if file was written
        # We expect write to be called with "code"
        handle = mock_file()
        # It's called for strat file and license file
        assert handle.write.call_count >= 2
