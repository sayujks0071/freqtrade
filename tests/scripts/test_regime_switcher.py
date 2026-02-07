import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Mock talib before importing regime_switcher if not available
try:
    import talib.abstract
except ImportError:
    sys.modules["talib"] = MagicMock()
    sys.modules["talib.abstract"] = MagicMock()


# Import the script
sys.path.append(str(Path(__file__).parents[2]))
import scripts.regime_switcher as rs


@pytest.fixture
def mock_config(tmp_path):
    config_dir = tmp_path / "user_data" / "configs"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config_production.json"

    initial_config = {"strategy": "OldStrategy"}
    with open(config_file, "w") as f:
        json.dump(initial_config, f)

    return config_file


@pytest.fixture
def mock_log(tmp_path):
    return tmp_path / "regime_log.md"


@pytest.fixture
def mock_project_root(tmp_path):
    with patch("scripts.regime_switcher.get_project_root", return_value=tmp_path):
        yield tmp_path

def create_dummy_df(length=205, close_val=100):
    return pd.DataFrame({
        "timestamp": range(length),
        "open": [100] * length,
        "high": [105] * length,
        "low": [95] * length,
        "close": [close_val] * length,
        "volume": [1000] * length
    })

@patch("scripts.regime_switcher.ccxt.kucoin")
@patch("scripts.regime_switcher.ta")
def test_regime_bull_market(mock_ta, mock_ccxt, mock_project_root, mock_config, mock_log):
    # Setup Data (205 rows)
    df = create_dummy_df(close_val=105)

    # Mock exchange
    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv.return_value = df.values.tolist()
    mock_ccxt.return_value = mock_exchange

    # Mock Indicators
    # EMA200 < Close (Bullish) -> Say EMA is 90
    mock_ta.EMA.return_value = pd.Series([90] * 205)
    # ADX > 25 -> Say 30
    mock_ta.ADX.return_value = pd.Series([30] * 205)
    # ATR
    mock_ta.ATR.return_value = pd.Series([2] * 205)

    # Run
    rs.main()

    # Verify Config Update
    with open(mock_config, "r") as f:
        config = json.load(f)
    assert config["strategy"] == "MomentumVolumeTrend"

    # Verify Log
    with open(mock_log, "r") as f:
        content = f.read()
    assert "Bull Market" in content
    assert "MomentumVolumeTrend" in content


@patch("scripts.regime_switcher.ccxt.kucoin")
@patch("scripts.regime_switcher.ta")
def test_regime_sideways_market(mock_ta, mock_ccxt, mock_project_root, mock_config, mock_log):
    # Setup Data
    df = create_dummy_df(close_val=100)

    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv.return_value = df.values.tolist()
    mock_ccxt.return_value = mock_exchange

    # Mock Indicators
    # ADX < 20 -> Say 15
    mock_ta.ADX.return_value = pd.Series([15] * 205)
    mock_ta.EMA.return_value = pd.Series([100] * 205)
    mock_ta.ATR.return_value = pd.Series([1] * 205)

    # Run
    rs.main()

    # Verify Config
    with open(mock_config, "r") as f:
        config = json.load(f)
    assert config["strategy"] == "BollingerRSI"


@patch("scripts.regime_switcher.ccxt.kucoin")
@patch("scripts.regime_switcher.ta")
def test_regime_crash_market(mock_ta, mock_ccxt, mock_project_root, mock_config, mock_log):
    # Setup Data
    df = create_dummy_df(close_val=70)

    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv.return_value = df.values.tolist()
    mock_ccxt.return_value = mock_exchange

    # Mock Indicators
    # EMA200 > Close -> Say 100 (Close is 70)
    mock_ta.EMA.return_value = pd.Series([100] * 205)
    # ADX: Needs to be between 20 and 25 to fail first two checks?
    # Or just ensure it doesn't trigger Sideways (ADX > 20)
    mock_ta.ADX.return_value = pd.Series([40] * 205)

    mock_ta.ATR.return_value = pd.Series([5] * 205)

    # Run
    rs.main()

    # Verify Config
    with open(mock_config, "r") as f:
        config = json.load(f)
    assert config["strategy"] == "VolatilityBreakout"
