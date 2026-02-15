import ast
import json
import sys
from pathlib import Path


def check_config_files():
    config_files = []

    config_dir = Path("user_data/configs")
    if config_dir.exists():
        config_files.extend(config_dir.glob("*.json"))

    root_config = Path("config.json")
    if root_config.exists():
        config_files.append(root_config)

    if not config_files:
        print("No config files found.")
        return True

    all_compliant = True
    for config_file in config_files:
        try:
            with config_file.open() as f:
                data = json.load(f)
                max_open_trades = data.get("max_open_trades")
                if max_open_trades is not None:
                    if max_open_trades > 5:
                        print(
                            f"VIOLATION: {config_file} has max_open_trades = "
                            f"{max_open_trades} (> 5)"
                        )
                        all_compliant = False
                    else:
                        print(f"OK: {config_file} has max_open_trades = {max_open_trades}")
                else:
                    print(f"SKIP: {config_file} does not have max_open_trades")
        except Exception as e:
            print(f"ERROR: Could not parse {config_file}: {e}")
            all_compliant = False
    return all_compliant


def get_stoploss_from_node(node, strategy_file):
    if isinstance(node.value, ast.Constant):  # Python 3.8+
        return node.value.value
    elif isinstance(node.value, ast.Num):  # Python < 3.8
        return node.value.n
    elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
        if isinstance(node.value.operand, ast.Constant):
            return -node.value.operand.value
        elif isinstance(node.value.operand, ast.Num):
            return -node.value.operand.n

    print(f"WARN: Could not parse stoploss value in {strategy_file}")
    return None


def check_single_strategy(strategy_file):
    try:
        with strategy_file.open() as f:
            tree = ast.parse(f.read())

        stoploss_found = False
        compliant = True

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "stoploss":
                        stoploss_value = get_stoploss_from_node(node, strategy_file)

                        if stoploss_value is None:
                            continue

                        stoploss_found = True
                        # strictly looser than -10% means < -0.10 (e.g. -0.20)
                        if stoploss_value < -0.10:
                            print(
                                f"VIOLATION: {strategy_file} has stoploss = "
                                f"{stoploss_value} (< -0.10)"
                            )
                            compliant = False
                        else:
                            print(f"OK: {strategy_file} has stoploss = {stoploss_value}")

        if not stoploss_found:
            print(f"SKIP: {strategy_file} does not have stoploss defined")

        return compliant

    except Exception as e:
        print(f"ERROR: Could not parse {strategy_file}: {e}")
        return False


def check_strategy_files():
    strategy_dir = Path("user_data/strategies")
    if not strategy_dir.exists():
        print("No strategy directory found.")
        return True

    strategy_files = list(strategy_dir.glob("*.py"))

    if not strategy_files:
        print("No strategy files found in user_data/strategies/")
        return True

    all_compliant = True
    for strategy_file in strategy_files:
        if not check_single_strategy(strategy_file):
            all_compliant = False

    return all_compliant


if __name__ == "__main__":
    print("Starting Audit...")
    configs_ok = check_config_files()
    strategies_ok = check_strategy_files()

    if configs_ok and strategies_ok:
        print("Audit PASSED: All checks passed.")
        sys.exit(0)
    else:
        print("Audit FAILED: Violations found.")
        sys.exit(1)
