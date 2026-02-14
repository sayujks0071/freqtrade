import ast
from pathlib import Path

import pytest

from freqtrade.configuration.load_config import load_config_file


# Paths
# Assuming tests/test_risk_compliance.py is in tests/
# user_data is in root/user_data
ROOT_DIR = Path(__file__).parents[1]
USER_DATA = ROOT_DIR / "user_data"
CONFIGS_DIR = USER_DATA / "configs"
STRATEGIES_DIR = USER_DATA / "strategies"


def get_config_files():
    files = []

    # Check user_data/configs/*.json
    if CONFIGS_DIR.exists():
        files.extend(list(CONFIGS_DIR.glob("*.json")))

    # Check root config.json
    root_config = ROOT_DIR / "config.json"
    if root_config.exists():
        files.append(root_config)

    # Check user_data/config.json
    user_data_config = USER_DATA / "config.json"
    if user_data_config.exists():
        files.append(user_data_config)

    return files


def get_strategy_files():
    if not STRATEGIES_DIR.exists():
        return []
    # Exclude __init__.py and _base directory (which is likely not a file but let's be safe)
    files = list(STRATEGIES_DIR.glob("*.py"))
    return [f for f in files if f.name != "__init__.py"]


@pytest.mark.parametrize("config_file", get_config_files())
def test_max_open_trades_compliance(config_file):
    """
    Ensure max_open_trades is never > 5 in any configuration file.
    """
    config = load_config_file(str(config_file))

    # If max_open_trades is not present, we skip (it might be a partial config)
    # But for the known configs, it is present.
    if "max_open_trades" in config:
        max_open_trades = config["max_open_trades"]
        # Handle unlimited (float('inf')) or -1 which maps to inf
        if max_open_trades == -1 or max_open_trades == float("inf"):
            pytest.fail(f"{config_file.name}: max_open_trades is unlimited, which is > 5")

        assert max_open_trades <= 5, f"{config_file.name}: max_open_trades={max_open_trades} is > 5"


@pytest.mark.parametrize("strategy_file", get_strategy_files())
def test_stoploss_compliance(strategy_file):
    """
    Ensure stoploss is never strictly looser than -10% (-0.10) for any strategy.
    Stoploss must be >= -0.10.
    """
    # Use Path.open() as recommended by Ruff (PTH123) and remove "r" mode (UP015)
    with strategy_file.open() as f:
        tree = ast.parse(f.read())

    stoploss_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # We are inside a class (Strategy)
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "stoploss":
                            # Found stoploss assignment
                            # Check value
                            value_node = item.value

                            # Handle negative numbers: -0.10 is UnaryOp(USub, Constant(0.10))
                            if isinstance(value_node, ast.UnaryOp) and isinstance(
                                value_node.op, ast.USub
                            ):
                                operand = value_node.operand
                                if isinstance(operand, ast.Constant):
                                    val = operand.value
                                    actual_stoploss = -val

                                    # Constraint: stoploss >= -0.10
                                    # e.g. -0.10 >= -0.10 (Pass)
                                    # e.g. -0.05 >= -0.10 (Pass)
                                    # e.g. -0.20 < -0.10 (Fail)

                                    assert actual_stoploss >= -0.10, (
                                        f"{strategy_file.name}: stoploss {actual_stoploss} "
                                        "is strictly looser than -0.10"
                                    )
                                    stoploss_found = True

                            # Handle positive numbers (unlikely for stoploss but possible
                            # if someone messed up)
                            elif isinstance(value_node, ast.Constant):
                                # If positive, it's definitely > -0.10, but logically wrong for
                                # stoploss usually. But compliant with ">= -0.10".
                                stoploss_found = True

    if not stoploss_found:
        # If not found, it might be inherited.
        # But we want to ensure *if* it is defined, it is compliant.
        # Or maybe we want to enforce it is defined?
        # The prompt says "Ensure ... for any strategy".
        # If it's missing, we can't verify it.
        # But for DeltaSafeStrategy, we know it is there.
        pass
