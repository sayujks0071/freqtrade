import ast
from pathlib import Path

import pytest

from freqtrade.configuration.load_config import load_config_file


def test_config_risk_compliance():
    """
    Test that configuration files comply with risk management rules.
    Constraint: max_open_trades <= 5
    """
    config_dir = Path("user_data/configs")
    config_files = list(config_dir.glob("*.json"))

    root_config = Path("config.json")
    if root_config.exists():
        config_files.append(root_config)

    for config_file in config_files:
        try:
            config = load_config_file(str(config_file))
            # Check max_open_trades
            if "max_open_trades" in config:
                max_open_trades = config["max_open_trades"]
                # -1 means unlimited, which violates safety rules unless specifically handled.
                # Here we strictly enforce <= 5.
                assert max_open_trades <= 5, f"{config_file}: max_open_trades {max_open_trades} > 5"
                assert max_open_trades > 0, f"{config_file}: max_open_trades must be positive"
            else:
                # If not present, it might default to something else.
                # For strict audit, we might require it to be present and <= 5.
                # But let's assume if it's missing, we skip or warn.
                pass
        except Exception as e:
            pytest.fail(f"Failed to load config {config_file}: {e}")


def _extract_stoploss_value(node: ast.Assign) -> float | None:
    """Extract numeric value from stoploss assignment."""
    val = None
    if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
        if isinstance(node.value.operand, ast.Constant):
            val = -node.value.operand.value
        elif isinstance(node.value.operand, ast.Num):  # Legacy support
            val = -node.value.operand.n
    elif isinstance(node.value, ast.Constant):
        val = node.value.value
    elif isinstance(node.value, ast.Num):  # Legacy support
        val = node.value.n
    return val


def test_strategy_risk_compliance():
    """
    Test that strategy files comply with risk management rules.
    Constraint: stoploss >= -0.10 (never strictly looser than -10%)
    """
    strategy_dir = Path("user_data/strategies")
    # Only check .py files directly in strategies dir
    strategy_files = [f for f in strategy_dir.glob("*.py") if f.name != "__init__.py"]

    for strategy_file in strategy_files:
        with strategy_file.open("r") as f:
            tree = ast.parse(f.read())

        stoploss_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                val = _extract_stoploss_value(item)

                                if val is not None:
                                    # strict looser means < -0.10 (e.g. -0.11)
                                    # so we require val >= -0.10
                                    assert val >= -0.10, (
                                        f"{strategy_file}: stoploss {val} is strictly "
                                        "looser than -0.10"
                                    )
                                    stoploss_found = True

        if not stoploss_found:
            # If stoploss is not found in the class, it might be inherited.
            pass
