#!/usr/bin/env python3
import ast
import json
import sys
from pathlib import Path


# Resolve the root directory (one level up from scripts/)
ROOT_DIR = Path(__file__).resolve().parent.parent


def check_configs():
    config_files = []
    config_dir = ROOT_DIR / "user_data" / "configs"
    if config_dir.is_dir():
        config_files.extend(list(config_dir.glob("*.json")))

    root_config = ROOT_DIR / "config.json"
    if root_config.exists():
        config_files.append(root_config)

    clean = True
    for config_file in config_files:
        try:
            with config_file.open() as f:
                config = json.load(f)
                max_open_trades = config.get("max_open_trades", float("inf"))

                if max_open_trades == -1:
                    max_open_trades = float("inf")

                if max_open_trades > 5:
                    print(f"VIOLATION: {config_file} has max_open_trades = {max_open_trades} > 5")
                    clean = False
        except Exception as e:
            print(f"ERROR reading {config_file}: {e}")
            clean = False
    return clean


def extract_stoploss(node):
    """Extract stoploss value from an AST node."""
    if not isinstance(node, ast.Assign):
        return None

    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "stoploss":
            value = node.value
            stoploss_val = None
            if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
                if isinstance(value.operand, ast.Constant):
                    stoploss_val = -value.operand.value
                elif isinstance(value.operand, ast.Num):  # Python < 3.8
                    stoploss_val = -value.operand.n
            elif isinstance(value, ast.Constant):
                stoploss_val = value.value
            elif isinstance(value, ast.Num):
                stoploss_val = value.n
            return stoploss_val
    return None


def check_strategy_file(strategy_file):
    """Check a single strategy file for stoploss violations."""
    try:
        with strategy_file.open() as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    stoploss_val = extract_stoploss(item)
                    if stoploss_val is not None:
                        # strictly looser means < -0.10 (e.g. -0.20)
                        # We want stoploss >= -0.10
                        if stoploss_val < -0.10:
                            print(
                                f"VIOLATION: {strategy_file} has stoploss = {stoploss_val} < -0.10"
                            )
                            return False
    except Exception as e:
        print(f"ERROR reading {strategy_file}: {e}")
        return False
    return True


def check_strategies():
    strategy_files = []
    strategy_dir = ROOT_DIR / "user_data" / "strategies"
    if strategy_dir.is_dir():
        # Recursively find all python files
        strategy_files.extend(list(strategy_dir.rglob("*.py")))

    clean = True
    for strategy_file in strategy_files:
        if strategy_file.name == "__init__.py":
            continue
        if not check_strategy_file(strategy_file):
            clean = False
    return clean


if __name__ == "__main__":
    configs_ok = check_configs()
    strategies_ok = check_strategies()
    if not configs_ok or not strategies_ok:
        sys.exit(1)
    print("Audit passed.")
    sys.exit(0)
