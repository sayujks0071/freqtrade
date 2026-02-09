import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add tools to path
tools_path = Path(__file__).parents[1] / "tools"
sys.path.append(str(tools_path))

import validate_markets_schema  # noqa: E402


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.env = "india_prod"
    args.markets = "markets.json"
    args.prev_whitelist = "whitelist.json"
    args.out_report = "report.md"
    return args


def test_validate_market_structure_valid():
    errors = []
    m = {
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "quote": "USDT",
        "active": True,
        "contract": True,
    }
    symbol = validate_markets_schema.validate_market_structure(0, m, errors)
    assert symbol == "BTC/USDT:USDT"
    assert not errors


def test_validate_market_structure_missing_field():
    errors = []
    m = {"symbol": "BTC/USDT:USDT", "base": "BTC"}
    symbol = validate_markets_schema.validate_market_structure(0, m, errors)
    assert symbol == "BTC/USDT:USDT"
    assert len(errors) > 0
    assert "missing field 'quote'" in errors[0]


def test_validate_symbol_format_valid():
    errors = []
    validate_markets_schema.validate_symbol_format("BTC/USDT:USDT", errors)
    assert not errors


def test_validate_symbol_format_invalid():
    errors = []
    validate_markets_schema.validate_symbol_format("BTCUSDT", errors)
    assert len(errors) > 0
    assert "missing base/quote delimiter" in errors[0]


def test_validate_volume_valid():
    errors = []
    m = {"volume": 10000}
    validate_markets_schema.validate_volume(m, "BTC", errors)
    assert not errors


def test_validate_volume_invalid():
    errors = []
    m = {"volume": -100}
    validate_markets_schema.validate_volume(m, "BTC", errors)
    assert len(errors) > 0
    assert "negative volume" in errors[0]


def test_validate_schema_valid(mock_args):
    # Let's fix data to be unique
    data = []
    for i in range(20):
        data.append(
            {
                "symbol": f"BTC{i}/USDT:USDT",
                "base": f"BTC{i}",
                "quote": "USDT",
                "active": True,
                "contract": True,
                "volume": 1000,
            }
        )

    with patch("validate_markets_schema.check_environment_sanity"):
        success, errors, _report, symbols = validate_markets_schema.validate_schema(data, mock_args)

    assert success
    assert not errors
    assert len(symbols) == 20


def test_validate_drift_no_prev(mock_args):
    current_markets = [{"symbol": "BTC/USDT:USDT", "active": True}]
    report_lines = []

    # Mock Path.exists to False
    with patch("pathlib.Path.exists", return_value=False):
        success, errors = validate_markets_schema.validate_drift(
            current_markets, "prev.json", report_lines
        )

    assert success
    assert not errors
    assert "No previous whitelist found" in report_lines[1]


def test_validate_drift_fail(mock_args):
    # Previous: 10 pairs
    prev_whitelist = [f"BTC{i}/USDT:USDT" for i in range(10)]
    # Current: 2 pairs (80% removal)
    current_markets = [{"symbol": f"BTC{i}/USDT:USDT", "active": True} for i in range(2)]

    report_lines = []

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.open", new_callable=MagicMock) as mock_open,
        patch("json.load", return_value={"exchange": {"pair_whitelist": prev_whitelist}}),
    ):
        # Mock context manager for open
        mock_open.return_value.__enter__.return_value = MagicMock()

        success, errors = validate_markets_schema.validate_drift(
            current_markets, "prev.json", report_lines
        )

    assert not success
    assert len(errors) > 0
    assert "Large delist drift" in errors[0]
