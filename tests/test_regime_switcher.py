import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd


# Add scripts directory to path to import regime_switcher
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

# Import regime_switcher module
import regime_switcher


def test_detect_regime_bull():
    row = pd.Series({"close": 100, "ema200": 90, "ADX_14": 30})
    regime, strategy = regime_switcher.detect_regime(row)
    assert regime == "Bull Market"
    assert strategy == "MomentumVolumeTrend"


def test_detect_regime_sideways():
    row = pd.Series({"close": 100, "ema200": 90, "ADX_14": 15})
    regime, strategy = regime_switcher.detect_regime(row)
    assert regime == "Sideways/Choppy"
    assert strategy == "BollingerRSI"


def test_detect_regime_volatile():
    row = pd.Series({"close": 80, "ema200": 90, "ADX_14": 30})
    regime, strategy = regime_switcher.detect_regime(row)
    assert regime == "Volatile/Bearish"
    assert strategy == "VolatilityBreakout"


def test_detect_regime_uncertain():
    # Price > EMA200 but ADX between 20 and 25
    row = pd.Series({"close": 100, "ema200": 90, "ADX_14": 22})
    regime, strategy = regime_switcher.detect_regime(row)
    assert regime == "Transition/Uncertain"
    assert strategy == "VolatilityBreakout"


def test_detect_regime_insufficient_data():
    row = pd.Series({"close": 100, "ema200": float("nan"), "ADX_14": 30})
    regime, strategy = regime_switcher.detect_regime(row)
    assert regime == "Insufficient Data"
    assert strategy == "DeltaSafeStrategy"


@patch("regime_switcher.ccxt.kraken")
def test_get_market_data(mock_kraken):
    mock_exchange = MagicMock()
    mock_kraken.return_value = mock_exchange
    mock_exchange.load_markets.return_value = {"BTC/USDT": {}}
    mock_exchange.fetch_ohlcv.return_value = [
        [1609459200000, 29000, 29500, 28500, 29000, 1000]
    ]

    df = regime_switcher.get_market_data()
    assert df is not None
    assert len(df) == 1
    assert df.iloc[0]["close"] == 29000
    mock_exchange.fetch_ohlcv.assert_called_once()
