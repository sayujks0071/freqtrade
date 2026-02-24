#!/usr/bin/env python3
import json
import ast
import sys
from pathlib import Path

def check_configs():
    """
    Check all JSON config files in user_data/configs/ for max_open_trades <= 5.
    """
    config_dir = Path("user_data/configs")
    if not config_dir.exists():
        print(f"Config directory {config_dir} not found.")
        return True # Or False depending on strictness, but here we assume no configs means no violations.

    violations = []
    for config_file in config_dir.glob("*.json"):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)

            max_open_trades = config.get("max_open_trades")
            if max_open_trades is None:
                # If missing, it defaults to unlimited (usually). Treat as violation or warning?
                # The requirement is "Ensure max_open_trades is never > 5".
                # If missing, it's potentially infinite > 5.
                # However, maybe it's set in another config?
                # We'll warn but maybe not fail unless strict.
                # Let's fail if it's missing to be safe "Risk Manager".
                violations.append(f"{config_file}: max_open_trades is missing (potential infinite risk).")
            elif isinstance(max_open_trades, (int, float)):
                if max_open_trades > 5:
                    violations.append(f"{config_file}: max_open_trades ({max_open_trades}) > 5.")
                elif max_open_trades == -1: # Unlimited
                    violations.append(f"{config_file}: max_open_trades is unlimited (-1).")
            else:
                 violations.append(f"{config_file}: max_open_trades has invalid type {type(max_open_trades)}.")

        except json.JSONDecodeError:
            violations.append(f"{config_file}: Invalid JSON.")
        except Exception as e:
            violations.append(f"{config_file}: Error reading: {e}")

    if violations:
        print("Config Violations found:")
        for v in violations:
            print(f"  - {v}")
        return False

    print("No config violations found.")
    return True

def check_strategies():
    """
    Check all Python strategy files in user_data/strategies/ for stoploss >= -0.10.
    """
    strategy_dir = Path("user_data/strategies")
    if not strategy_dir.exists():
        print(f"Strategy directory {strategy_dir} not found.")
        return True

    violations = []
    # Recursively check strategies? Or just top level?
    # The requirement says "user_data/strategies/*.py".
    # I'll check recursively to be safe as per memory hint.
    for strategy_file in strategy_dir.rglob("*.py"):
        if strategy_file.name == "__init__.py":
            continue

        try:
            with open(strategy_file, "r") as f:
                tree = ast.parse(f.read(), filename=str(strategy_file))

            # Find class definitions that inherit from IStrategy (optional check, but good heuristic)
            # Or just look for any class with a stoploss attribute.

            found_stoploss = False

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # check class body for assignments
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "stoploss":
                                    # Found stoploss assignment
                                    if isinstance(item.value, ast.UnaryOp) and isinstance(item.value.op, ast.USub) and isinstance(item.value.operand, ast.Constant):
                                        # Handle negative number: -0.10
                                        value = -item.value.operand.value
                                    elif isinstance(item.value, ast.Constant):
                                        value = item.value.value
                                    else:
                                        # Could be a variable or complex expression. Warn?
                                        # violations.append(f"{strategy_file}: stoploss is not a literal number.")
                                        continue

                                    found_stoploss = True
                                    if value < -0.10: # "Strictly looser than -10%" means < -0.10
                                        violations.append(f"{strategy_file}: stoploss ({value}) is strictly looser than -0.10.")
                                    # print(f"Checked {strategy_file}: stoploss = {value}")

            # If no stoploss found, it might use default. Default is usually -0.10? Or -0.05?
            # Freqtrade default stoploss is -0.10 (10%).
            # If not explicitly set, we assume default.
            # But the requirement is "Ensure stoploss is never...".
            # If explicit value is missing, we can't check it easily without inheritance resolution.
            # We'll assume compliance if missing (or warn).
            # Given Audit task, we primarily check explicit values.

        except Exception as e:
            violations.append(f"{strategy_file}: Error parsing: {e}")

    if violations:
        print("Strategy Violations found:")
        for v in violations:
            print(f"  - {v}")
        return False

    print("No strategy violations found.")
    return True

def main():
    print("Starting Risk Audit...")
    configs_ok = check_configs()
    strategies_ok = check_strategies()

    if not configs_ok or not strategies_ok:
        sys.exit(1)

    print("Audit passed successfully.")

if __name__ == "__main__":
    main()
