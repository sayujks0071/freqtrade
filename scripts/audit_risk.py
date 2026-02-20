#!/usr/bin/env python3
"""
Risk Audit Script
Scans configuration and strategy files to enforce risk limits.
Constraints:
- max_open_trades <= 5 (in configs)
- stoploss >= -0.10 (in strategies, never strictly looser than -10%)
"""

import ast
import json
import sys
from pathlib import Path


def check_config_file(filepath: Path) -> bool:
    """
    Checks a configuration file for risk violations.
    Constraint: max_open_trades <= 5
    """
    try:
        with filepath.open(encoding="utf-8") as f:
            config = json.load(f)

        max_open_trades = config.get("max_open_trades")
        if max_open_trades is not None:
            if isinstance(max_open_trades, (int, float)):
                if max_open_trades > 5:
                    print(f"VIOLATION: {filepath} - max_open_trades ({max_open_trades}) > 5")
                    return False
            else:
                print(
                    f"WARNING: {filepath} - max_open_trades is not a number: "
                    f"{max_open_trades}"
                )
                # Treat non-numeric as potentially unsafe if we can't verify?
                # Usually max_open_trades is int.
                # If it's -1 (unlimited), that's > 5 logically.
                if max_open_trades == -1:
                    print(
                        f"VIOLATION: {filepath} - max_open_trades is unlimited (-1), "
                        "which is > 5"
                    )
                    return False

        return True
    except json.JSONDecodeError:
        print(f"ERROR: {filepath} - Invalid JSON")
        return False
    except Exception as e:
        print(f"ERROR: {filepath} - {e}")
        return False


def check_strategy_file(filepath: Path) -> bool:
    """
    Checks a strategy file for risk violations.
    Constraint: stoploss >= -0.10
    """
    try:
        with filepath.open(encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                val = _get_value_from_node(item.value)
                                if val is not None and isinstance(val, (int, float)):
                                    if val < -0.10:
                                        print(
                                            f"VIOLATION: {filepath} - stoploss ({val}) "
                                            "is strictly looser than -0.10"
                                        )
                                        return False
                                    # Precision issue check: -0.10000000000000001 is < -0.10?
                                    # Floating point comparison.
                                    # If val is exactly -0.10, it passes.
                                    # If val is -0.11, it fails.
    except Exception as e:
        print(f"ERROR: {filepath} - {e}")
        return False

    return True


def _get_value_from_node(node: ast.AST) -> int | float | None:
    """
    Extracts numeric value from AST node.
    Handles positive numbers (Constant) and negative numbers (UnaryOp -> Constant).
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _get_value_from_node(node.operand)
        if operand is not None:
            return -operand
    return None


def main():
    """
    Main execution function.
    """
    root_dir = Path()
    user_data_dir = root_dir / "user_data"

    violations = False

    # Check Configs
    config_files = list(user_data_dir.glob("configs/*.json"))
    if (root_dir / "config.json").exists():
        config_files.append(root_dir / "config.json")

    for config_file in config_files:
        if not check_config_file(config_file):
            violations = True

    # Check Strategies
    strategy_files = list(user_data_dir.glob("strategies/*.py"))

    for strategy_file in strategy_files:
        if not check_strategy_file(strategy_file):
            violations = True

    if violations:
        sys.exit(1)
    else:
        print("Audit passed: All configurations and strategies are compliant.")
        sys.exit(0)


if __name__ == "__main__":
    main()
