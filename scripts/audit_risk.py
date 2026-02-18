#!/usr/bin/env python3
import json
import sys
import ast
from pathlib import Path

def audit_config(filepath):
    print(f"Auditing Config: {filepath}...")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: Error reading {filepath}: {e}")
        return False

    max_open_trades = data.get('max_open_trades')
    if max_open_trades is None:
        print(f"FAIL: max_open_trades not found in {filepath}. Must be explicitly set <= 5.")
        return False

    # Check if value is valid number
    if not isinstance(max_open_trades, (int, float)):
         print(f"FAIL: max_open_trades is not a number in {filepath}")
         return False

    if max_open_trades > 5:
        print(f"FAIL: max_open_trades ({max_open_trades}) > 5 in {filepath}")
        return False

    print(f"PASS: {filepath}")
    return True

def audit_strategy(filepath):
    print(f"Auditing Strategy: {filepath}...")
    try:
        with open(filepath, 'r') as f:
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
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == 'stoploss':
                            # Handle simple assignment: stoploss = -0.10 or stoploss = 0.05
                            if isinstance(item.value, ast.Constant):
                                stoploss_value = item.value.value
                            elif isinstance(item.value, ast.UnaryOp) and isinstance(item.value.op, ast.USub) and isinstance(item.value.operand, ast.Constant):
                                stoploss_value = -item.value.operand.value
                            else:
                                print(f"WARN: stoploss found but complex/dynamic value in {filepath}")
                                # specific check for manual review if dynamic
                                pass

                            has_stoploss = True

    if has_stoploss:
        if stoploss_value is not None:
            # Check: stoploss >= -0.10
            # If stoploss < -0.10, it's strictly looser (e.g. -0.11).
            if stoploss_value < -0.10:
                print(f"FAIL: stoploss ({stoploss_value}) < -0.10 in {filepath}")
                return False
    else:
        # Freqtrade default stoploss is -0.10.
        print(f"WARN: stoploss not explicitly defined in {filepath}. Assuming default (-0.10) which is compliant.")

    print(f"PASS: {filepath}")
    return True

def main():
    failed = False

    # Audit configs
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

    # Audit strategies
    strategy_dir = Path("user_data/strategies")
    if strategy_dir.exists():
        # Iterate files recursively
        for strategy_file in strategy_dir.rglob("*.py"):
            # Skip hidden files
            if strategy_file.name.startswith("__"):
                continue

            # Skip _base directory content.
            # Using str(strategy_file) to check if _base is in path is safer than parent check if recursive
            if "_base" in strategy_file.parts:
                continue

            if not audit_strategy(strategy_file):
                failed = True
    else:
        print("WARN: user_data/strategies/ does not exist.")

    if failed:
        sys.exit(1)
    else:
        print("All checks passed.")

if __name__ == "__main__":
    main()
