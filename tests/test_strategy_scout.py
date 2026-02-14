from unittest.mock import MagicMock, patch
import pytest
from tools.strategy_scout import StrategyScout

@pytest.fixture
def scout():
    return StrategyScout(token="test_token")

def test_init(scout):
    assert scout.token == "test_token"
    assert scout.session.headers["Authorization"] == "token test_token"
    assert scout.candidates == []

@patch("tools.strategy_scout.requests.Session.get")
def test_check_rate_limit_ok(mock_get, scout):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "resources": {
            "core": {
                "remaining": 50,
                "reset": 1234567890
            }
        }
    }
    mock_get.return_value = mock_resp
    assert scout.check_rate_limit() is True

@patch("tools.strategy_scout.requests.Session.get")
def test_check_rate_limit_low(mock_get, scout):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "resources": {
            "core": {
                "remaining": 0,
                "reset": 1234567890
            }
        }
    }
    mock_get.return_value = mock_resp
    # It should print a warning and return False
    assert scout.check_rate_limit() is False

@patch("tools.strategy_scout.requests.Session.get")
def test_search_github(mock_get, scout):
    # Mock rate limit check
    with patch.object(scout, "check_rate_limit", return_value=True):
        # Mock search response
        mock_resp_search = MagicMock()
        mock_resp_search.status_code = 200
        mock_resp_search.json.return_value = {
            "items": [
                {"full_name": "user/repo1", "stargazers_count": 100},
                {"full_name": "user/repo2", "stargazers_count": 50}
            ]
        }

        # Mock known source response
        mock_resp_known = MagicMock()
        mock_resp_known.status_code = 200
        mock_resp_known.json.return_value = {"full_name": "freqtrade/freqtrade-strategies", "stargazers_count": 5000}

        mock_get.side_effect = [
            mock_resp_search, mock_resp_search, mock_resp_search, mock_resp_search, mock_resp_search, # 5 queries
            mock_resp_known # 1 known source
        ]

        scout.search_github()

        # Check candidates
        # We expect unique candidates.
        # "user/repo1" and "user/repo2" from search, and "freqtrade/freqtrade-strategies" from known.
        assert len(scout.candidates) == 3
        names = [c["full_name"] for c in scout.candidates]
        assert "user/repo1" in names
        assert "freqtrade/freqtrade-strategies" in names

def test_filter_and_score(scout):
    scout.candidates = [
        {
            "full_name": "user/repo1",
            "description": "A freqtrade strategy",
            "pushed_at": "2023-01-01T00:00:00Z",
            "license": {"key": "mit", "name": "MIT License"}
        },
        {
            "full_name": "user/repo2",
            "description": "No license",
            "pushed_at": "2023-01-01T00:00:00Z",
            "license": None
        }
    ]

    scout.filter_and_score()

    # repo2 has no license, so it should be filtered out unless it's a known source (it's not)
    assert len(scout.candidates) == 1
    assert scout.candidates[0]["full_name"] == "user/repo1"
    assert scout.candidates[0]["scout_score"] > 0
