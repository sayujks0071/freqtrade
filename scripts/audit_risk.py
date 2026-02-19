#!/usr/bin/env python3
"""
Risk Audit Script
"""

import ast
import json
import sys
from pathlib import Path


def check_config(config_path: Path) -> bool:
    """
    Check if config file has max_open_trades <= 5.
    """
    try:
        with config_path.open() as f:
            config = json.load(f)
            max_open_trades = config.get("max_open_trades", float("inf"))
            if max_open_trades > 5:
                print(f"VIOLATION: {config_path} has max_open_trades={max_open_trades} > 5")
                return False
            print(f"OK: {config_path} has max_open_trades={max_open_trades}")
            return True
    except FileNotFoundError:
        print(f"WARNING: {config_path} not found")
        return True
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse {config_path}: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error processing {config_path}: {e}")
        return False


def _extract_value_from_node(node: ast.AST) -> int | float | None:
    """
    Extract numeric value from AST node.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, (int, float)) else None
    # For older Python versions, though 3.12+ uses Constant
    elif isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand_val = _extract_value_from_node(node.operand)
        if operand_val is not None:
            return -operand_val
    return None


def _check_class_node(node: ast.ClassDef, strategy_path: Path) -> bool:
    """
    Check a ClassDef node for stoploss compliance.
    Returns False if a violation is found, True otherwise.
    """
    for item in node.body:
        if not isinstance(item, ast.Assign):
            continue

        for target in item.targets:
            if not isinstance(target, ast.Name) or target.id != "stoploss":
                continue

            val = _extract_value_from_node(item.value)

            if val is not None:
                if val < -0.10:  # strictly looser than -0.10
                    print(
                        f"VIOLATION: {strategy_path} strategy '{node.name}' "
                        f"has stoploss={val} < -0.10"
                    )
                    return False
                else:
                    print(f"OK: {strategy_path} strategy '{node.name}' has stoploss={val}")
    return True


def check_strategy(strategy_path: Path) -> bool:
    """
    Check if strategy file has stoploss >= -0.10.
    """
    try:
        with strategy_path.open() as f:
            tree = ast.parse(f.read())

        compliant = True

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not _check_class_node(node, strategy_path):
                    compliant = False

        return compliant

    except Exception as e:
        print(f"ERROR: Could not parse {strategy_path}: {e}")
        return False


def main():
    config_dir = Path("user_data/configs")
    strategy_dir = Path("user_data/strategies")

    files_to_check = list(config_dir.glob("*.json"))
    strategies_to_check = list(strategy_dir.glob("*.py"))

    # Also check config.json if it exists
    if Path("config.json").exists():
        files_to_check.append(Path("config.json"))

    success = True

    print("--- Auditing Configurations ---")
    if not files_to_check:
        print("No configuration files found in user_data/configs/ or root.")

    for f in files_to_check:
        if not check_config(f):
            success = False

    print("\n--- Auditing Strategies ---")
    if not strategies_to_check:
        print("No strategy files found in user_data/strategies/.")

    for f in strategies_to_check:
        if f.name.startswith("_") or f.name == "__init__.py":
            continue
        if not check_strategy(f):
            success = False

    if not success:
        sys.exit(1)
    print("\nAudit passed.")


if __name__ == "__main__":
    main()
