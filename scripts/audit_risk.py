#!/usr/bin/env python3
import ast
import json
import sys
from pathlib import Path


# Constraints
MAX_OPEN_TRADES_LIMIT = 5
STOPLOSS_LIMIT = -0.10  # Must be >= -0.10 (e.g. -0.05 is ok, -0.15 is not)


def check_config_file(filepath: Path) -> bool:
    try:
        with filepath.open("r") as f:
            config = json.load(f)
            max_open_trades = config.get("max_open_trades")
            if max_open_trades is not None:
                if max_open_trades == -1 or max_open_trades == float("inf"):
                    print(f"VIOLATION in {filepath}: max_open_trades is unlimited")
                    return False
                if max_open_trades > MAX_OPEN_TRADES_LIMIT:
                    print(
                        f"VIOLATION in {filepath}: max_open_trades {max_open_trades} "
                        f"> {MAX_OPEN_TRADES_LIMIT}"
                    )
                    return False
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False
    return True


def _get_value(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant):
            return -node.operand.value
        elif isinstance(node.operand, ast.Num):  # Python < 3.8
            return -node.operand.n
    elif isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Num):
        return node.n
    return None


def extract_stoploss(node):
    # Handle normal assignment: stoploss = ...
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "stoploss":
                return _get_value(node.value)
    # Handle annotated assignment: stoploss: float = ...
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == "stoploss":
            if node.value:
                return _get_value(node.value)
    return None


def check_strategy_file(filepath: Path) -> bool:
    try:
        with filepath.open("r") as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check class level assignments
                for item in node.body:
                    stoploss = extract_stoploss(item)
                    if stoploss is not None:
                        # Use strict inequality for strictly looser check
                        # "strictly looser than -10%" means stoploss < -0.10
                        if stoploss < STOPLOSS_LIMIT:
                            print(
                                f"VIOLATION in {filepath}: stoploss {stoploss} "
                                f"is strictly looser than {STOPLOSS_LIMIT}"
                            )
                            return False
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return False
    return True


def main():
    root = Path()
    user_data = root / "user_data"

    has_violations = False

    # Check root config if exists
    root_config = root / "config.json"
    if root_config.exists():
        if not check_config_file(root_config):
            has_violations = True

    # Check configs
    for json_file in user_data.rglob("*.json"):
        # Skip specific files
        if json_file.name in ["baseline_metrics.json", "sentinel_state.json"]:
            continue
        if "backtest_results" in str(json_file) or "reports" in str(json_file):
            continue

        if not check_config_file(json_file):
            has_violations = True

    # Check strategies
    strategies_dir = user_data / "strategies"
    if strategies_dir.exists():
        for py_file in strategies_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            if not check_strategy_file(py_file):
                has_violations = True

    if has_violations:
        sys.exit(1)
    else:
        print("Audit passed.")


if __name__ == "__main__":
    main()
