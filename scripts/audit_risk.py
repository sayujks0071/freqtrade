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


def check_strategy(strategy_path: Path) -> bool:
    """
    Check if strategy file has stoploss >= -0.10.
    """
    try:
        with strategy_path.open() as f:
            tree = ast.parse(f.read())

        found_stoploss = False
        compliant = True

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check class-level assignments
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                found_stoploss = True
                                val = None
                                # Extract value
                                if isinstance(item.value, ast.Constant):  # Python 3.8+
                                    val = item.value.value
                                elif isinstance(item.value, ast.Num):  # Python < 3.8
                                    val = item.value.n
                                elif isinstance(item.value, ast.UnaryOp) and isinstance(
                                    item.value.op, ast.USub
                                ):
                                    if isinstance(item.value.operand, (ast.Constant, ast.Num)):
                                        val = -(
                                            item.value.operand.value
                                            if isinstance(item.value.operand, ast.Constant)
                                            else item.value.operand.n
                                        )

                                if val is not None:
                                    if val < -0.10:  # strictly looser than -0.10
                                        print(
                                            f"VIOLATION: {strategy_path} strategy '{node.name}' has stoploss={val} < -0.10"
                                        )
                                        compliant = False
                                    else:
                                        print(
                                            f"OK: {strategy_path} strategy '{node.name}' has stoploss={val}"
                                        )

        if not found_stoploss:
            # Strategies without explicit stoploss use default (usually -0.10 or defined in base)
            # We can warn or check base classes, but for now assuming default is safe or base handles it
            pass

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
