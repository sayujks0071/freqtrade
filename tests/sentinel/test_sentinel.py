import pytest
from unittest.mock import MagicMock, patch
import json
import time
from scripts.sentinel import Sentinel, FreqtradeClient, MarketData

@pytest.fixture
def mock_freqtrade_client():
    with patch('scripts.sentinel.FreqtradeClient') as MockClient:
        client = MockClient.return_value
        client.get_balance.return_value = {"total": 1000.0}
        client.stop_bot.return_value = {"status": "stopped"}
        yield client

@pytest.fixture
def mock_market_data():
    with patch('scripts.sentinel.MarketData') as MockMarket:
        market = MockMarket.return_value
        market.get_price_drop.return_value = 0.0
        yield market

@pytest.fixture
def sentinel(mock_freqtrade_client, mock_market_data):
    # Mock state file to avoid file I/O
    with patch('scripts.sentinel.STATE_FILE') as mock_file:
        mock_file.exists.return_value = False

        # Instantiate Sentinel (mocks are injected via patch in __init__ if we did that,
        # but here we are patching the classes used inside __init__)
        # Actually, since Sentinel instantiates them in __init__, we need to patch the classes where they are imported
        # or use dependency injection.
        # Given the script structure, patching 'scripts.sentinel.FreqtradeClient' and 'scripts.sentinel.MarketData'
        # before instantiating Sentinel works.

        s = Sentinel()
        # Ensure our fixtures are the ones used
        s.ft_client = mock_freqtrade_client
        s.market = mock_market_data

        # Reset state
        s.state = {"balance_history": [], "triggered": False}
        return s

def test_drawdown_trigger(sentinel):
    # Simulate history with high balance
    sentinel.state["balance_history"] = [
        {"ts": time.time() - 1800, "balance": 1000.0} # 30 mins ago
    ]

    # Current balance drops significantly (e.g. 900, which is 10% drop)
    sentinel.ft_client.get_balance.return_value = {"total": 900.0}

    sentinel.run_check()

    # Verify Kill Switch was called
    sentinel.ft_client.kill_switch.assert_called_once()
    assert sentinel.state["triggered"] is True

def test_btc_drop_trigger(sentinel):
    # Balance is fine
    sentinel.ft_client.get_balance.return_value = {"total": 1000.0}

    # BTC drops 15%
    sentinel.market.get_price_drop.return_value = 15.0

    sentinel.run_check()

    # Verify Kill Switch was called
    sentinel.ft_client.kill_switch.assert_called_once()
    assert sentinel.state["triggered"] is True

def test_no_trigger_normal_conditions(sentinel):
    # Balance stable
    sentinel.state["balance_history"] = [
        {"ts": time.time() - 1800, "balance": 1000.0}
    ]
    sentinel.ft_client.get_balance.return_value = {"total": 990.0} # 1% drop

    # BTC stable
    sentinel.market.get_price_drop.return_value = 2.0

    sentinel.run_check()

    # Verify Kill Switch NOT called
    sentinel.ft_client.kill_switch.assert_not_called()
    assert sentinel.state["triggered"] is False

def test_already_triggered(sentinel):
    sentinel.state["triggered"] = True

    sentinel.run_check()

    # Should exit immediately without checking API
    sentinel.ft_client.get_balance.assert_not_called()
    sentinel.market.get_price_drop.assert_not_called()

def test_balance_history_update(sentinel):
    # Test that balance is added to history
    sentinel.ft_client.get_balance.return_value = {"total": 1050.0}

    sentinel.run_check()

    history = sentinel.state["balance_history"]
    assert len(history) == 1
    assert history[0]["balance"] == 1050.0
