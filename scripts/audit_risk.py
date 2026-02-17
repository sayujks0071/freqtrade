import ast
import glob
import json
import sys
from pathlib import Path


def check_configs():
    violations = []
    # Check multiple locations for config files
    config_patterns = ["config.json", "user_data/config.json", "user_data/configs/*.json"]

    config_files = []
    for pattern in config_patterns:
        found = glob.glob(pattern)  # noqa: PTH207
        config_files.extend(found)

    # Remove duplicates
    config_files = list(set(config_files))

    if not config_files:
        print("Warning: No config files found.")
        return violations

    print(f"Checking config files: {config_files}")

    for config_file_path in config_files:
        config_path = Path(config_file_path)
        try:
            with config_path.open("r") as f:
                config = json.load(f)

                if not isinstance(config, dict):
                    violations.append(
                        f"Config error in {config_path}: Root element must be a dictionary"
                    )
                    continue

                max_open_trades = config.get("max_open_trades")

                if max_open_trades is None:
                    violations.append(
                        f"Config violation in {config_path}: "
                        "max_open_trades is missing (defaults to unlimited)"
                    )
                elif isinstance(max_open_trades, (int, float)):
                    if max_open_trades == -1:
                        violations.append(
                            f"Config violation in {config_path}: max_open_trades is -1 (unlimited)"
                        )
                    elif max_open_trades > 5:
                        violations.append(
                            f"Config violation in {config_path}: "
                            f"max_open_trades ({max_open_trades}) > 5"
                        )
                else:
                    violations.append(
                        f"Config violation in {config_path}: "
                        f"max_open_trades has invalid type ({type(max_open_trades)})"
                    )

        except json.JSONDecodeError:
            violations.append(f"Error parsing JSON in {config_path}")
        except Exception as e:
            violations.append(f"Error reading {config_path}: {e}")

    return violations


def get_ast_value(node):
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    return None


def check_strategy_node(node, strategy_file, violations):
    if not isinstance(node, ast.ClassDef):
        return

    for item in node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "stoploss":
                    value_node = item.value
                    stoploss_val = None

                    if isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
                        operand_val = get_ast_value(value_node.operand)
                        if isinstance(operand_val, (int, float)):
                            stoploss_val = -operand_val

                    elif isinstance(value_node, (ast.Constant, ast.Num)):
                        val = get_ast_value(value_node)
                        if isinstance(val, (int, float)):
                            stoploss_val = val

                    if stoploss_val is not None:
                        # Constraint: stoploss >= -0.10
                        if stoploss_val < -0.10:
                            violations.append(
                                f"Strategy violation in {strategy_file} (class {node.name}): "
                                f"stoploss ({stoploss_val}) < -0.10"
                            )


def check_strategies():
    violations = []
    strategy_files = glob.glob("user_data/strategies/*.py")  # noqa: PTH207

    if not strategy_files:
        print("Warning: No strategy files found in user_data/strategies/")
        return violations

    print(f"Checking strategy files: {strategy_files}")

    for strategy_file_path in strategy_files:
        if "__init__.py" in strategy_file_path or "_base" in strategy_file_path:
            continue

        strategy_path = Path(strategy_file_path)

        try:
            with strategy_path.open("r") as f:
                tree = ast.parse(f.read(), filename=str(strategy_path))

                for node in tree.body:
                    check_strategy_node(node, strategy_path, violations)

        except SyntaxError:
            violations.append(f"Error parsing Python syntax in {strategy_path}")
        except Exception as e:
            violations.append(f"Error checking {strategy_path}: {e}")

    return violations


def main():
    print("Starting Risk Audit...")
    config_violations = check_configs()
    strategy_violations = check_strategies()

    all_violations = config_violations + strategy_violations

    if all_violations:
        print("\nFound violations:")
        for v in all_violations:
            print(f" - {v}")
        sys.exit(1)
    else:
        print("\nSuccess: No violations found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
