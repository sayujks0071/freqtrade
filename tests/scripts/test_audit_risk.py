from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.audit_risk import check_config_file, check_strategy_file


def test_check_config_file_valid():
    mock_path = MagicMock(spec=Path)
    mock_path.open.return_value.__enter__.return_value.read.return_value = '{"max_open_trades": 3}'
    # We need to mock json.load separately since it takes a file object
    with patch("json.load", return_value={"max_open_trades": 3}):
         assert check_config_file(mock_path) is True

def test_check_config_file_invalid_unlimited():
    mock_path = MagicMock(spec=Path)
    with patch("json.load", return_value={"max_open_trades": -1}):
         assert check_config_file(mock_path) is False

def test_check_config_file_invalid_high():
    mock_path = MagicMock(spec=Path)
    with patch("json.load", return_value={"max_open_trades": 10}):
         assert check_config_file(mock_path) is False

def test_check_strategy_file_valid():
    content = """
from freqtrade.strategy import IStrategy
class MyStrategy(IStrategy):
    stoploss = -0.10
"""
    mock_path = MagicMock(spec=Path)
    mock_path.open.return_value.__enter__.return_value.read.return_value = content
    assert check_strategy_file(mock_path) is True

def test_check_strategy_file_invalid_loose():
    content = """
from freqtrade.strategy import IStrategy
class MyStrategy(IStrategy):
    stoploss = -0.20
"""
    mock_path = MagicMock(spec=Path)
    mock_path.open.return_value.__enter__.return_value.read.return_value = content
    assert check_strategy_file(mock_path) is False

def test_check_strategy_file_annotated_valid():
    content = """
from freqtrade.strategy import IStrategy
class MyStrategy(IStrategy):
    stoploss: float = -0.10
"""
    mock_path = MagicMock(spec=Path)
    mock_path.open.return_value.__enter__.return_value.read.return_value = content
    assert check_strategy_file(mock_path) is True

def test_check_strategy_file_annotated_invalid():
    content = """
from freqtrade.strategy import IStrategy
class MyStrategy(IStrategy):
    stoploss: float = -0.20
"""
    mock_path = MagicMock(spec=Path)
    mock_path.open.return_value.__enter__.return_value.read.return_value = content
    assert check_strategy_file(mock_path) is False
