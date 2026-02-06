import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure scripts is in path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import regime_switcher


class TestRegimeSwitcher:
    @pytest.fixture
    def mock_market_data(self):
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "timestamp": dates.astype(int) / 10**6,
            "open": [100.0] * 10,
            "high": [110.0] * 10,
            "low": [90.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
            "date": dates,
        })
        return df

    @patch("scripts.regime_switcher.ccxt.binance")
    def test_get_market_data(self, mock_binance):
        mock_exchange = MagicMock()
        mock_binance.return_value = mock_exchange
        mock_exchange.fetch_ohlcv.return_value = [
            [1672531200000, 100, 110, 90, 100, 1000]
        ]

        df = regime_switcher.get_market_data()
        assert not df.empty
        assert "date" in df.columns
        assert len(df) == 1

    @patch("scripts.regime_switcher.ta")
    def test_detect_regime_bull(self, mock_ta, mock_market_data):
        # Setup mock indicators
        def ema_side_effect(df, timeperiod=200):
            return df["ema200"]

        def adx_side_effect(df, timeperiod=14):
            return df["adx"]

        mock_ta.EMA.side_effect = ema_side_effect
        mock_ta.ADX.side_effect = adx_side_effect

        df = mock_market_data.copy()
        df["ema200"] = 90.0
        df["adx"] = 30.0
        df.iloc[-1, df.columns.get_loc("close")] = 100.0

        regime, strategy, allow_short = regime_switcher.detect_regime(df)
        assert regime == "Bull"
        assert strategy == "MomentumVolumeTrend"
        assert allow_short is False

    @patch("scripts.regime_switcher.ta")
    def test_detect_regime_sideways(self, mock_ta, mock_market_data):
        def ema_side_effect(df, timeperiod=200):
            return df["ema200"]

        def adx_side_effect(df, timeperiod=14):
            return df["adx"]

        mock_ta.EMA.side_effect = ema_side_effect
        mock_ta.ADX.side_effect = adx_side_effect

        df = mock_market_data.copy()
        # ADX < 20 should prioritize Sideways even if price < EMA200 (Bear)
        df["ema200"] = 110.0  # Bearish trend signal
        df["adx"] = 15.0  # But Choppy/Sideways
        df.iloc[-1, df.columns.get_loc("close")] = 100.0

        regime, strategy, allow_short = regime_switcher.detect_regime(df)
        assert regime == "Sideways"
        assert strategy == "BollingerRSI"
        assert allow_short is False

    @patch("scripts.regime_switcher.ta")
    def test_detect_regime_volatile(self, mock_ta, mock_market_data):
        def ema_side_effect(df, timeperiod=200):
            return df["ema200"]

        def adx_side_effect(df, timeperiod=14):
            return df["adx"]

        mock_ta.EMA.side_effect = ema_side_effect
        mock_ta.ADX.side_effect = adx_side_effect

        df = mock_market_data.copy()
        df["ema200"] = 110.0
        df["adx"] = 30.0
        df.iloc[-1, df.columns.get_loc("close")] = 100.0

        regime, strategy, allow_short = regime_switcher.detect_regime(df)
        assert regime == "Volatile/Bear"
        assert strategy == "VolatilityBreakout"
        assert allow_short is True

    @patch("scripts.regime_switcher.Path")
    @patch("json.dump")
    @patch("json.load")
    def test_update_config(self, mock_load, mock_dump, mock_path):
        # Setup path structure
        # Path(__file__).resolve().parents[1] / ...

        # Mock the Path object created in the script
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.resolve.return_value = mock_path_instance

        # When .parents[1] is accessed
        mock_parents = MagicMock()
        mock_path_instance.parents = [MagicMock(), mock_parents]  # 0, 1

        # When / operator is used on parents[1]
        mock_config_file = MagicMock()
        mock_parents.__truediv__.return_value = mock_config_file

        # File exists
        mock_config_file.exists.return_value = True

        # Open context manager
        mock_file_handle = MagicMock()
        mock_config_file.open.return_value.__enter__.return_value = mock_file_handle

        # Mock json load
        mock_load.return_value = {
            "strategy": "OldStrategy",
            "unidirectional_only": True,
        }

        regime_switcher.update_config("NewStrategy", True)

        mock_load.assert_called()
        mock_dump.assert_called()
        args, _ = mock_dump.call_args
        saved_config = args[0]
        assert saved_config["strategy"] == "NewStrategy"
        assert saved_config["unidirectional_only"] is False

    @patch("scripts.regime_switcher.Path")
    def test_log_decision(self, mock_path):
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.resolve.return_value = mock_path_instance

        mock_parents = MagicMock()
        mock_path_instance.parents = [MagicMock(), mock_parents]

        mock_log_file = MagicMock()
        mock_parents.__truediv__.return_value = mock_log_file

        mock_log_file.exists.return_value = True

        regime_switcher.log_decision("Bull", "MomentumVolumeTrend")

        mock_log_file.open.assert_called_with("a")
