from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from freqtrade.plugins.protections.daily_loss_limit import DailyLossLimit


@pytest.fixture
def protection_config():
    return {
        "max_daily_loss": 0.05,
        "max_daily_loss_abs": 100.0,
    }


@pytest.fixture
def config():
    return {"dry_run_wallet": 1000}


def test_daily_loss_limit_no_trades(protection_config, config, mocker):
    mocker.patch("freqtrade.persistence.Trade.get_trades_proxy", return_value=[])

    protection = DailyLossLimit(config, protection_config)
    result = protection.global_stop(datetime.now(UTC), "long")
    assert result is None


def test_daily_loss_limit_profit(protection_config, config, mocker):
    # Trade with profit
    mock_trade = MagicMock()
    mock_trade.close_profit_abs = 50.0
    mocker.patch("freqtrade.persistence.Trade.get_trades_proxy", return_value=[mock_trade])

    protection = DailyLossLimit(config, protection_config)
    result = protection.global_stop(datetime.now(UTC), "long")
    assert result is None


def test_daily_loss_limit_hit_abs(protection_config, config, mocker):
    # Trade with loss > 100
    mock_trade = MagicMock()
    mock_trade.close_profit_abs = -150.0
    mocker.patch("freqtrade.persistence.Trade.get_trades_proxy", return_value=[mock_trade])

    protection = DailyLossLimit(config, protection_config)
    result = protection.global_stop(datetime.now(UTC), "long")

    assert result is not None
    assert result.lock is True
    assert "Daily Loss Limit hit (ABS)" in result.reason


def test_daily_loss_limit_hit_pct(protection_config, config, mocker):
    # Trade with loss > 5% of 1000 (50)
    mock_trade = MagicMock()
    mock_trade.close_profit_abs = -60.0
    mocker.patch("freqtrade.persistence.Trade.get_trades_proxy", return_value=[mock_trade])

    protection = DailyLossLimit(config, protection_config)
    result = protection.global_stop(datetime.now(UTC), "long")

    assert result is not None
    assert result.lock is True
    assert "Daily Loss Limit hit (%)" in result.reason
