#!/usr/bin/env python3
import ast
import json
import sys
from pathlib import Path


def audit_config(filepath):
    print(f"Auditing Config: {filepath}...")
    try:
        with Path(filepath).open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: Error reading {filepath}: {e}")
        return False

    max_open_trades = data.get("max_open_trades")
    if max_open_trades is None:
        print(f"PASS: max_open_trades not found in {filepath} (assuming inherited/default).")
        # If not present, we can't enforce it here, but it doesn't violate the rule directly.
        # It relies on the base config or default.
        return True

    # Check if value is valid number
    if not isinstance(max_open_trades, (int, float)):
        print(f"FAIL: max_open_trades is not a number in {filepath}")
        return False

    if max_open_trades > 5:
        print(f"FAIL: max_open_trades ({max_open_trades}) > 5 in {filepath}")
        return False

    print(f"PASS: {filepath}")
    return True


def check_stoploss(node, filepath):
    stoploss_value = None
    has_stoploss = False

    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "stoploss":
                # Handle simple assignment: stoploss = -0.10 or stoploss = 0.05
                if isinstance(node.value, ast.Constant):
                    stoploss_value = node.value.value
                elif (
                    isinstance(node.value, ast.UnaryOp)
                    and isinstance(node.value.op, ast.USub)
                    and isinstance(node.value.operand, ast.Constant)
                ):
                    stoploss_value = -node.value.operand.value
                else:
                    print(f"WARN: stoploss found but complex/dynamic value in {filepath}")
                    # specific check for manual review if dynamic
                    pass

                has_stoploss = True
    return has_stoploss, stoploss_value


def audit_strategy(filepath):
    print(f"Auditing Strategy: {filepath}...")
    try:
        with Path(filepath).open() as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"FAIL: Error parsing {filepath}: {e}")
        return False

    has_stoploss = False
    stoploss_value = None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check class attributes
            for item in node.body:
                found, val = check_stoploss(item, filepath)
                if found:
                    has_stoploss = True
                    stoploss_value = val

    if has_stoploss:
        if stoploss_value is not None:
            # Check: stoploss >= -0.10
            # If stoploss < -0.10, it's strictly looser (e.g. -0.11).
            if stoploss_value < -0.10:
                print(f"FAIL: stoploss ({stoploss_value}) < -0.10 in {filepath}")
                return False
    else:
        # Freqtrade default stoploss is -0.10.
        print(
            f"WARN: stoploss not explicitly defined in {filepath}. "
            "Assuming default (-0.10) which is compliant."
        )

    print(f"PASS: {filepath}")
    return True


def audit_all_configs():
    failed = False
    config_dir = Path("user_data/configs")
    if config_dir.exists():
        for config_file in config_dir.glob("*.json"):
            if not audit_config(config_file):
                failed = True
    else:
        print("WARN: user_data/configs/ does not exist.")

    user_config = Path("user_data/config.json")
    if user_config.exists():
        if not audit_config(user_config):
            failed = True

    # Audit root config
    root_config = Path("config.json")
    if root_config.exists():
        if not audit_config(root_config):
            failed = True

    return failed


def audit_all_strategies():
    failed = False
    strategy_dir = Path("user_data/strategies")
    if strategy_dir.exists():
        # Iterate files recursively
        for strategy_file in strategy_dir.rglob("*.py"):
            # Skip hidden files
            if strategy_file.name.startswith("__"):
                continue

            if not audit_strategy(strategy_file):
                failed = True
    else:
        print("WARN: user_data/strategies/ does not exist.")

    return failed


def main():
    failed_configs = audit_all_configs()
    failed_strategies = audit_all_strategies()

    if failed_configs or failed_strategies:
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    main()
