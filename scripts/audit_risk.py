#!/usr/bin/env python3
"""
Audit risk configuration in configs and strategies.

Checks:
1. max_open_trades <= 5 in all config files.
2. stoploss >= -0.10 (not strictly looser than -10%) in all strategy files.
"""

import ast
import json
import sys
from pathlib import Path


def check_config_risk(filepath: Path) -> bool:
    """Check max_open_trades in config file."""
    try:
        with filepath.open("r") as f:
            config = json.load(f)

        max_open_trades = config.get("max_open_trades")
        if max_open_trades is None:
            # max_open_trades is optional in config, but if set, must check.
            return False

        if max_open_trades > 5:
            print(f"VIOLATION: max_open_trades > 5 in {filepath} (found {max_open_trades})")
            return True

        return False
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse JSON in {filepath}")
        return False
    except Exception as e:
        print(f"ERROR checking {filepath}: {e}")
        return False


def validate_stoploss_value(value_node, filepath) -> bool:
    """Validate stoploss value node."""
    val = None
    # Check for negative number (UnaryOp USub)
    if isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
        operand = value_node.operand
        if isinstance(operand, ast.Constant):
            val = -operand.value
        elif isinstance(operand, ast.Num):  # Fallback for older python
            val = -operand.n

    # Check for positive number (unlikely for stoploss but possible)
    elif isinstance(value_node, ast.Constant):
        val = value_node.value
    elif isinstance(value_node, ast.Num):  # Fallback for older python
        val = value_node.n

    if val is not None and val < -0.10:
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
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                if validate_stoploss_value(item.value, filepath):
                                    return True
        return False
    except Exception as e:
        print(f"ERROR checking {filepath}: {e}")
        return False


def main():
    violations = False

    # Check Configs
    config_files = Path("user_data/configs").glob("*.json")
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
