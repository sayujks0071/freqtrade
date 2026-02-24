#!/usr/bin/env python3
import ast
import json
import sys
from pathlib import Path


def check_configs() -> bool:
    """
    Check all JSON config files in user_data/configs/ and config.json for max_open_trades <= 5.
    """
    config_files = list(Path("user_data/configs").glob("*.json"))
    root_config = Path("config.json")
    if root_config.exists():
        config_files.append(root_config)

    if not config_files:
        print("No config files found to check.")
        return True

    violations = []
    for config_file in config_files:
        try:
            with config_file.open() as f:
                config = json.load(f)

            max_open_trades = config.get("max_open_trades")
            if max_open_trades is None:
                violations.append(
                    f"{config_file}: max_open_trades is missing (potential infinite risk)."
                )
            elif isinstance(max_open_trades, (int, float)):
                if max_open_trades > 5:
                    violations.append(f"{config_file}: max_open_trades ({max_open_trades}) > 5.")
                elif max_open_trades == -1:  # Unlimited
                    violations.append(f"{config_file}: max_open_trades is unlimited (-1).")
            else:
                violations.append(
                    f"{config_file}: max_open_trades has invalid type {type(max_open_trades)}."
                )

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


def check_strategy_file(strategy_file: Path) -> list[str]:
    """
    Check a single strategy file for stoploss compliance.
    """
    local_violations = []
    try:
        with strategy_file.open() as f:
            tree = ast.parse(f.read(), filename=str(strategy_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # check class body for assignments
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "stoploss":
                                # Found stoploss assignment
                                value = None
                                if (
                                    isinstance(item.value, ast.UnaryOp)
                                    and isinstance(item.value.op, ast.USub)
                                    and isinstance(item.value.operand, ast.Constant)
                                ):
                                    # Handle negative number: -0.10
                                    value = -item.value.operand.value
                                elif isinstance(item.value, ast.Constant):
                                    value = item.value.value
                                else:
                                    # Could be a variable or complex expression.
                                    continue

                                if value < -0.10:
                                    local_violations.append(
                                        f"{strategy_file}: stoploss ({value}) "
                                        "is strictly looser than -0.10."
                                    )

    except Exception as e:
        local_violations.append(f"{strategy_file}: Error parsing: {e}")

    return local_violations


def check_strategies() -> bool:
    """
    Check all Python strategy files in user_data/strategies/ for stoploss >= -0.10.
    """
    strategy_dir = Path("user_data/strategies")
    if not strategy_dir.exists():
        print(f"Strategy directory {strategy_dir} not found.")
        return True

    violations = []
    for strategy_file in strategy_dir.rglob("*.py"):
        if strategy_file.name == "__init__.py":
            continue

        violations.extend(check_strategy_file(strategy_file))

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
