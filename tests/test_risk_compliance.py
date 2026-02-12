import re
from pathlib import Path

import pytest

from freqtrade.configuration.load_config import load_config_file


def get_configs():
    # Get all json files in user_data/configs/
    files = list(Path("user_data/configs").glob("*.json"))

    # Also check potential root config locations
    potential_roots = ["config.json", "user_data/config.json"]
    for p in potential_roots:
        path = Path(p)
        if path.exists():
            files.append(path)

    # Convert to strings for pytest
    return [str(f) for f in files]


def get_strategies():
    return [str(f) for f in Path("user_data/strategies").glob("*.py")]


@pytest.mark.parametrize("config_file", get_configs())
def test_config_risk_limits(config_file):
    """
    Ensure max_open_trades is never > 5 in configuration files.
    Uses freqtrade's own config loader to handle comments and trailing commas.
    """
    try:
        config = load_config_file(config_file)
    except Exception as e:
        pytest.fail(f"Failed to load config {config_file}: {e}")

    max_open_trades = config.get("max_open_trades")
    if max_open_trades is not None:
        assert max_open_trades <= 5, (
            f"{config_file}: max_open_trades ({max_open_trades}) must be <= 5"
        )


@pytest.mark.parametrize("strategy_file", get_strategies())
def test_strategy_risk_limits(strategy_file):
    """
    Ensure stoploss is never strictly looser than -10% (-0.10) for any strategy.
    """
    if strategy_file.endswith("__init__.py"):
        return

    # Use regex for strategy parsing to avoid import issues or side effects
    with Path(strategy_file).open("r") as f:
        content = f.read()

    # Regex to find stoploss assignment.
    # Handles: stoploss = -0.10, stoploss = -0.2, etc.
    # Note: This is a simple static check. It assumes stoploss is defined as a class
    # attribute or global.
    match = re.search(r"stoploss\s*=\s*([-+]?\d*\.?\d+)", content)

    if match:
        stoploss_val = float(match.group(1))
        # Strictly looser than -0.10 means < -0.10 (e.g. -0.20)
        # So stoploss must be >= -0.10
        assert stoploss_val >= -0.10, f"{strategy_file}: stoploss ({stoploss_val}) must be >= -0.10"
    else:
        # If no stoploss found, we check if it looks like a strategy file
        if "class " in content and "(IStrategy" in content:
            # If it inherits IStrategy but doesn't define stoploss,
            # it might be relying on default or base class.
            # Ideally we should warn, but for now let's fail if we want strict enforcement.
            # However, some strategies might define it dynamically.
            # Given the "Audit" nature, reporting missing stoploss is safer.
            pytest.fail(f"{strategy_file}: No explicit stoploss definition found.")
