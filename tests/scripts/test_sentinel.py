import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add scripts directory to sys.path
scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
sys.path.append(str(scripts_dir))

try:
    from sentinel import Sentinel
except ImportError:
    # Fallback if scripts dir not found (shouldn't happen with correct path)
    pytest.fail("Could not import Sentinel from scripts/")


@pytest.fixture
def mock_requests():
    with patch("sentinel.requests") as mock:
        yield mock


@pytest.fixture
def mock_ccxt():
    with patch("sentinel.ccxt") as mock:
        yield mock


@pytest.fixture
def sentinel_instance(mock_requests, mock_ccxt):
    # Mock config loading
    with patch("sentinel.load_config_file", return_value={}):
        # Mock Path.exists to return False so it doesn't try to read real file
        with patch.object(Path, "exists", return_value=False):
            sentinel = Sentinel(Path("dummy_config.json"), "http://localhost:8080", "user", "pass")

            # Mock successful authentication
            mock_requests.post.return_value.status_code = 200
            mock_requests.post.return_value.json.return_value = {
                "access_token": "token",
                "refresh_token": "refresh",
            }
            sentinel.authenticate()

            return sentinel


def test_initialization(sentinel_instance):
    assert sentinel_instance.api_url == "http://localhost:8080"
    assert sentinel_instance.access_token == "token"
    # Exchange defaults to binance or mocked one
    assert sentinel_instance.exchange is not None


def test_get_balance(sentinel_instance, mock_requests):
    mock_requests.get.return_value.status_code = 200
    mock_requests.get.return_value.json.return_value = {"total": 1500.0}

    balance = sentinel_instance.get_balance()
    assert balance == 1500.0

    # Verify call
    mock_requests.get.assert_called_with(
        "http://localhost:8080/api/v1/balance",
        headers={"Authorization": "Bearer token"},
        timeout=10,
    )


def test_check_drawdown_no_history(sentinel_instance, mock_requests):
    mock_requests.get.return_value.status_code = 200
    mock_requests.get.return_value.json.return_value = {"total": 1000.0}

    # First check, no history, so no drawdown
    assert sentinel_instance.check_drawdown() is False
    assert len(sentinel_instance.balance_history) == 1
    assert sentinel_instance.balance_history[0][1] == 1000.0


def test_check_drawdown_trigger(sentinel_instance, mock_requests):
    now = datetime.now(UTC)

    # Inject history: Peak was 1000.0 (30 mins ago)
    sentinel_instance.balance_history.append((now - timedelta(minutes=30), 1000.0))

    # Current balance drops to 900.0 (10% drop)
    mock_requests.get.return_value.status_code = 200
    mock_requests.get.return_value.json.return_value = {"total": 900.0}

    # Drawdown = (1000 - 900) / 1000 = 0.1 > 0.05 => Trigger
    assert sentinel_instance.check_drawdown() is True


def test_check_drawdown_safe(sentinel_instance, mock_requests):
    now = datetime.now(UTC)

    # Inject history: Peak was 1000.0
    sentinel_instance.balance_history.append((now - timedelta(minutes=30), 1000.0))

    # Current balance drops to 960.0 (4% drop)
    mock_requests.get.return_value.status_code = 200
    mock_requests.get.return_value.json.return_value = {"total": 960.0}

    # Drawdown = (1000 - 960) / 1000 = 0.04 < 0.05 => No Trigger
    assert sentinel_instance.check_drawdown() is False


def test_get_btc_price_drop(sentinel_instance):
    mock_exchange = MagicMock()
    sentinel_instance.exchange = mock_exchange

    # OHLCV: [timestamp, open, high, low, close, volume]
    # Scenario: High was 50k, now close is 40k (20% drop)
    mock_exchange.fetch_ohlcv.return_value = [
        [0, 48000, 50000, 48000, 49000, 10],  # High 50k
        [0, 49000, 49500, 48000, 48500, 10],
        [0, 48500, 49000, 47000, 47500, 10],
        [0, 47500, 48000, 46000, 46500, 10],
        [0, 46500, 47000, 40000, 40000, 10],  # Current Close 40k
    ]

    drop = sentinel_instance.get_btc_price_drop()
    # Max High = 50000, Current = 40000
    # Drop = (50000 - 40000) / 50000 = 0.2
    assert drop == 0.2
    assert sentinel_instance.check_btc_crash() is True


def test_emergency_stop(sentinel_instance, mock_requests):
    sentinel_instance.emergency_stop("Test Reason")

    # Verify Force Exit Call
    mock_requests.post.assert_any_call(
        "http://localhost:8080/api/v1/forceexit",
        json={"tradeid": "all"},
        headers={"Authorization": "Bearer token"},
        timeout=10,
    )

    # Verify Stop Call
    mock_requests.post.assert_any_call(
        "http://localhost:8080/api/v1/stop", headers={"Authorization": "Bearer token"}, timeout=10
    )
