#!/usr/bin/env python3
"""
Audit risk configuration in configs and strategies.

Checks:
1. max_open_trades <= 5 in all config files (and not -1 for unlimited).
2. stoploss >= -0.10 (not strictly looser than -10%) in all strategy and config files.
"""

import ast
import json
import sys
from pathlib import Path


def check_config_risk(filepath: Path) -> bool:
    """Check max_open_trades and stoploss in config file."""
    try:
        with filepath.open("r") as f:
            config = json.load(f)

        violation_found = False

        # 1. Check max_open_trades
        max_open_trades = config.get("max_open_trades")
        if max_open_trades is not None:
            # -1 means unlimited, which is > 5
            if max_open_trades == -1 or max_open_trades > 5:
                print(
                    f"VIOLATION: max_open_trades > 5 (or unlimited) in {filepath} (found {max_open_trades})"
                )
                violation_found = True

        # 2. Check stoploss (global default)
        stoploss = config.get("stoploss")
        if stoploss is not None:
            # stoploss in json is a float, e.g. -0.10
            if isinstance(stoploss, (int, float)) and stoploss < -0.10:
                print(f"VIOLATION: stoploss < -0.10 in {filepath} (found {stoploss})")
                violation_found = True

        return violation_found
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON in {filepath}")
        return False
    except Exception as e:
        print(f"ERROR checking {filepath}: {e}")
        return False


def validate_stoploss_value(value_node, filepath) -> bool:
    """Validate stoploss value node."""
    val: float | int | None = None
    # Check for negative number (UnaryOp USub)
    if isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
        operand = value_node.operand
        if isinstance(operand, ast.Constant):
            if isinstance(operand.value, (int, float)):
                val = -operand.value

    # Check for positive number (unlikely for stoploss but possible)
    elif isinstance(value_node, ast.Constant):
        if isinstance(value_node.value, (int, float)):
            val = value_node.value

    if val is not None and isinstance(val, (int, float)) and val < -0.10:
        print(f"VIOLATION: stoploss < -0.10 in {filepath} (found {val})")
        return True
    return False


def check_strategy_risk(filepath: Path) -> bool:
    """Check stoploss in strategy file using AST."""
    try:
        with filepath.open("r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    # Check for simple assignment: stoploss = -0.10
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                if validate_stoploss_value(item.value, filepath):
                                    return True
                    # Check for annotated assignment: stoploss: float = -0.10
                    elif isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name) and item.target.id == "stoploss":
                            if item.value and validate_stoploss_value(item.value, filepath):
                                return True
        return False
    except Exception as e:
        print(f"ERROR checking {filepath}: {e}")
        return False


def main():
    violations = False

    # Check Configs
    config_files = list(Path("user_data/configs").glob("*.json"))
    if Path("config.json").exists():
        config_files.append(Path("config.json"))

    for config_file in config_files:
        if check_config_risk(config_file):
            violations = True

    # Check Strategies
    strategy_files = Path("user_data/strategies").glob("*.py")
    for strategy_file in strategy_files:
        if check_strategy_risk(strategy_file):
            violations = True

    if violations:
        sys.exit(1)
    else:
        print("Audit Passed: No risk violations found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
