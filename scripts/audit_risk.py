import json
import glob
import ast
import sys

def check_config_files():
    config_files = glob.glob('user_data/configs/*.json')
    if not config_files:
        print("No config files found in user_data/configs/")
        return True

    all_compliant = True
    for config_file in config_files:
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
                max_open_trades = data.get('max_open_trades')
                if max_open_trades is not None:
                    if max_open_trades > 5:
                        print(f"VIOLATION: {config_file} has max_open_trades = {max_open_trades} (> 5)")
                        all_compliant = False
                    else:
                        print(f"OK: {config_file} has max_open_trades = {max_open_trades}")
                else:
                    print(f"SKIP: {config_file} does not have max_open_trades")
        except Exception as e:
            print(f"ERROR: Could not parse {config_file}: {e}")
            all_compliant = False
    return all_compliant

def check_strategy_files():
    strategy_files = glob.glob('user_data/strategies/*.py')
    if not strategy_files:
        print("No strategy files found in user_data/strategies/")
        return True

    all_compliant = True
    for strategy_file in strategy_files:
        try:
            with open(strategy_file, 'r') as f:
                tree = ast.parse(f.read())

            stoploss_found = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'stoploss':
                            if isinstance(node.value, ast.Constant): # Python 3.8+
                                stoploss_value = node.value.value
                            elif isinstance(node.value, ast.Num): # Python < 3.8
                                stoploss_value = node.value.n
                            elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
                                if isinstance(node.value.operand, ast.Constant):
                                    stoploss_value = -node.value.operand.value
                                elif isinstance(node.value.operand, ast.Num):
                                    stoploss_value = -node.value.operand.n
                                else:
                                    print(f"WARN: Could not parse stoploss value in {strategy_file}")
                                    continue
                            else:
                                print(f"WARN: Could not parse stoploss value in {strategy_file}")
                                continue

                            stoploss_found = True
                            # stoploss is typically negative. E.g. -0.10.
                            # strictly looser than -0.10 means stoploss > -0.10.
                            # So -0.05 is > -0.10 (VIOLATION).
                            # -0.20 is < -0.10 (OK).
                            # -0.10 is == -0.10 (OK).

                            if stoploss_value > -0.10:
                                print(f"VIOLATION: {strategy_file} has stoploss = {stoploss_value} (> -0.10)")
                                all_compliant = False
                            else:
                                print(f"OK: {strategy_file} has stoploss = {stoploss_value}")

            if not stoploss_found:
                 print(f"SKIP: {strategy_file} does not have stoploss defined at module level (or could not find it)")
                 # Note: It might be inherited. If inherited and not overridden, we assume base is compliant?
                 # Or maybe we should check MRO.
                 # For now, let's assume explicit definition is what we check.

        except Exception as e:
            print(f"ERROR: Could not parse {strategy_file}: {e}")
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
