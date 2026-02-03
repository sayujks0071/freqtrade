import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add scripts to path so we can import sentinel
scripts_path = Path(__file__).parent.parent.parent / "scripts"
sys.path.append(str(scripts_path.resolve()))

from sentinel import Sentinel  # noqa: E402


@pytest.fixture
def sentinel():
    with patch("sentinel.ccxt.gateio") as mock_ccxt:
        s = Sentinel()
        s.exchange = mock_ccxt.return_value
        return s


def test_initialization(sentinel):
    assert sentinel.balance_history == []
    assert sentinel.exchange is not None


@patch("sentinel.requests.Session")
def test_get_current_balance(mock_session_cls, sentinel):
    mock_session = mock_session_cls.return_value
    sentinel.session = mock_session
    sentinel.session.headers = {}

    # Mock login response
    # When .post() is called (for login)
    mock_post = sentinel.session.post.return_value
    mock_post.status_code = 200
    mock_post.json.return_value = {"access_token": "test_token"}

    # Mock balance response
    # When .get() is called (for balance)
    mock_get = sentinel.session.get.return_value
    mock_get.status_code = 200
    mock_get.json.return_value = {"total": 1000.0}

    # Since we set sentinel.session in init, we need to mock the instance methods directly
    # or rely on the mock passed to init if we mocked it there.
    # But init creates a real Session(). Let's mock the methods on the instance.
    sentinel.session.post = MagicMock(return_value=mock_post)
    sentinel.session.get = MagicMock(return_value=mock_get)

    balance = sentinel.get_current_balance()
    assert balance == 1000.0
    assert "Authorization" in sentinel.session.headers


def test_update_balance_history(sentinel):
    now = datetime.now(UTC)
    sentinel.update_balance_history(1000.0)
    assert len(sentinel.balance_history) == 1
    assert sentinel.balance_history[0][1] == 1000.0

    # Add old entry
    old_time = now - timedelta(hours=2)
    sentinel.balance_history.insert(0, (old_time, 900.0))

    sentinel.update_balance_history(1100.0)
    # The old one should be removed, the first one (from start of test) kept, and new one added.
    # Actually, the start of test 'now' is fresh.
    # update_balance_history appends then prunes.
    # So we expect 2 entries.

    assert len(sentinel.balance_history) == 2
    # Check values. Note: order matters.
    # 1. 1000.0 (added first)
    # 2. 1100.0 (added second)
    # 900.0 (inserted at index 0) should be pruned because it's 2h old.
    assert sentinel.balance_history[0][1] == 1000.0
    assert sentinel.balance_history[1][1] == 1100.0


def test_check_drawdown_no_trigger(sentinel):
    now = datetime.now(UTC)
    sentinel.balance_history = [(now - timedelta(minutes=30), 1000.0), (now, 980.0)]
    # Drop is 20 / 1000 = 0.02 (2%) < 5%
    assert sentinel.check_drawdown(980.0) is False


def test_check_drawdown_trigger(sentinel):
    now = datetime.now(UTC)
    sentinel.balance_history = [(now - timedelta(minutes=30), 1000.0), (now, 900.0)]
    # Drop is 100 / 1000 = 0.10 (10%) > 5%
    assert sentinel.check_drawdown(900.0) is True


def test_check_btc_crash_no_trigger(sentinel):
    # OHLCV: timestamp, open, high, low, close, volume
    sentinel.exchange.fetch_ohlcv.return_value = [
        [0, 100, 105, 95, 100, 10],  # High 105
        [0, 100, 102, 98, 100, 10],  # High 102
        [0, 100, 100, 90, 98, 10],  # Current close 98
    ]
    # Max High: 105. Current: 98. Drop: (105-98)/105 = 7/105 = 0.066 < 10%
    assert sentinel.check_btc_crash() is False


def test_check_btc_crash_trigger(sentinel):
    sentinel.exchange.fetch_ohlcv.return_value = [
        [0, 100, 120, 95, 100, 10],  # High 120
        [0, 100, 102, 98, 100, 10],
        [0, 100, 100, 90, 100, 10],  # Current close 100
    ]
    # Max High: 120. Current: 100. Drop: 20/120 = 0.166 > 10%
    assert sentinel.check_btc_crash() is True


@patch("sentinel.requests.post")
def test_send_alert(mock_post, sentinel):
    sentinel.send_alert("Test Alert")
    mock_post.assert_called_once()
    assert "Test Alert" in mock_post.call_args[1]["json"]["message"]


@patch("sentinel.requests.post")
def test_trigger_emergency(mock_webhook_post, sentinel):
    sentinel.session = MagicMock()

    sentinel.trigger_emergency("Test Reason")

    # Check Webhook
    mock_webhook_post.assert_called()

    # Check RPC ForceExit and Stop
    assert sentinel.session.post.call_count == 2
    calls = [call[0][0] for call in sentinel.session.post.call_args_list]
    assert any("forceexit" in c for c in calls)
    assert any("stop" in c for c in calls)


def test_get_current_balance_connection_error(sentinel):
    sentinel.session = MagicMock()
    sentinel.session.headers = {"Authorization": "Bearer token"}
    # Raise exception on get
    sentinel.session.get.side_effect = Exception("Connection refused")

    balance = sentinel.get_current_balance()
    assert balance is None


def test_get_current_balance_login_failure(sentinel):
    sentinel.session = MagicMock()
    sentinel.session.headers = {}

    sentinel.session.post.return_value.status_code = 401  # Wrong password

    balance = sentinel.get_current_balance()
    assert balance is None


def test_get_current_balance_token_expired(sentinel):
    sentinel.session = MagicMock()
    sentinel.session.headers = {"Authorization": "Bearer expired_token"}

    mock_response = MagicMock()
    mock_response.status_code = 401
    sentinel.session.get.return_value = mock_response

    balance = sentinel.get_current_balance()
    assert balance is None
    # Authorization header should be removed
    assert "Authorization" not in sentinel.session.headers
