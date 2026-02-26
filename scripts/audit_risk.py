#!/usr/bin/env python3
"""
Risk Audit Script
Enforces risk limits:
- max_open_trades <= 5
- stoploss >= -0.10 (not strictly looser than -10%)
"""

import json
import ast
import glob
import os
import sys

def audit_configs():
    config_files = glob.glob('user_data/configs/*.json') + glob.glob('config.json')
    violations = []

    print(f"Checking {len(config_files)} config files...")
    for config_file in config_files:
        print(f"  - {config_file}")
        if not os.path.exists(config_file):
            continue

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            max_open_trades = config.get('max_open_trades', float('inf'))
            if max_open_trades > 5:
                violations.append((config_file, 'max_open_trades', max_open_trades))

            # Check stoploss in config if exists
            if 'stoploss' in config:
                stoploss = config['stoploss']
                if stoploss < -0.10:
                    violations.append((config_file, 'stoploss', stoploss))

        except Exception as e:
            print(f"Error reading {config_file}: {e}")

    return violations

def audit_strategies():
    strategy_files = glob.glob('user_data/strategies/*.py')
    violations = []

    print(f"Checking {len(strategy_files)} strategy files...")
    for strategy_file in strategy_files:
        if strategy_file.endswith('__init__.py') or '_base' in strategy_file:
            continue

        print(f"  - {strategy_file}")
        with open(strategy_file, 'r') as f:
            content = f.read()

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == 'stoploss':
                                val = get_value_from_node(node.value)
                                if val is not None and val < -0.10:
                                    violations.append((strategy_file, 'stoploss', val))
                            elif target.id == 'max_open_trades':
                                val = get_value_from_node(node.value)
                                if val is not None and val > 5:
                                    violations.append((strategy_file, 'max_open_trades', val))

        except Exception as e:
            print(f"Error parsing {strategy_file}: {e}")

    return violations

def get_value_from_node(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = get_value_from_node(node.operand)
        return -val if val is not None else None

    if isinstance(node, ast.Constant):
        return node.value

    if hasattr(ast, 'Num') and isinstance(node, ast.Num):
        return node.n

    return None

def main():
    print("Auditing Configs...")
    config_violations = audit_configs()

    print("\nAuditing Strategies...")
    strategy_violations = audit_strategies()

    if config_violations or strategy_violations:
        print("\nViolations found!")
        for file_path, key, val in config_violations:
            print(f"  [FAIL] {file_path}: {key} = {val} (Limit: <= 5 for trades, >= -0.10 for stoploss)")

        for file_path, key, val in strategy_violations:
            print(f"  [FAIL] {file_path}: {key} = {val} (Limit: <= 5 for trades, >= -0.10 for stoploss)")
        sys.exit(1)
    else:
        print("\nRisk Check Passed: No violations found.")
        sys.exit(0)

if __name__ == "__main__":
    main()
