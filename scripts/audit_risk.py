import ast
import json
from pathlib import Path


def check_config_file(filepath: Path) -> bool:
    """Checks and fixes max_open_trades in config files."""
    try:
        with filepath.open("r") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON: {filepath}")
                return False

        max_open_trades = config.get("max_open_trades")
        # Check if max_open_trades is explicitly defined and > 5
        if isinstance(max_open_trades, (int, float)) and max_open_trades > 5:
            print(f"Fixing {filepath}: max_open_trades {max_open_trades} -> 5")
            config["max_open_trades"] = 5
            with filepath.open("w") as f:
                json.dump(config, f, indent=4)
            return True
        return False
    except Exception as e:
        print(f"Error checking {filepath}: {e}")
        return False


def _extract_stoploss_value(node: ast.Assign) -> float | None:
    """Extracts stoploss value from AST assignment."""
    # Check for simple assignment: stoploss = ...
    if (
        len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "stoploss"
    ):
        # Handle negative numbers: stoploss = -0.10
        if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
            operand = node.value.operand
            if isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float)):
                return -float(operand.value)
            # For older python versions ast.Num
            elif hasattr(ast, "Num") and isinstance(operand, ast.Num):
                return -float(operand.n)  # type: ignore
        # Handle positive numbers (unlikely for stoploss but possible): stoploss = 0.10
        elif isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, (int, float)
        ):
            return float(node.value.value)
        elif hasattr(ast, "Num") and isinstance(node.value, ast.Num):
            return float(node.value.n)  # type: ignore
    return None


def check_strategy_file(filepath: Path) -> bool:
    """Checks and fixes stoploss in strategy files."""
    try:
        with filepath.open("r") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            print(f"Skipping invalid Python: {filepath}")
            return False

        modified = False
        lines = content.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                stoploss_val = _extract_stoploss_value(node)
                if stoploss_val is not None:
                    # Constraint: Ensure stoploss is never strictly looser than -10% (-0.10).
                    # Looser means allowing more loss. So stoploss < -0.10 is looser.
                    if stoploss_val < -0.10:
                        print(f"Fixing {filepath}: stoploss {stoploss_val} -> -0.10")
                        # Find line number (1-based)
                        lineno = node.lineno - 1

                        if lineno < len(lines):
                            original_line = lines[lineno]
                            # Preserve indentation
                            indent_len = len(original_line) - len(original_line.lstrip())
                            indent = original_line[:indent_len]
                            lines[lineno] = f"{indent}stoploss = -0.10"
                            modified = True

        if modified:
            with filepath.open("w") as f:
                f.write("\n".join(lines) + "\n")
            return True
        return False

    except Exception as e:
        print(f"Error checking {filepath}: {e}")
        return False


def main():
    modified_count = 0

    # Configs
    config_dir = Path("user_data/configs")
    if config_dir.exists():
        for f in config_dir.glob("*.json"):
            if check_config_file(f):
                modified_count += 1

    # Check root config.json if exists
    root_config = Path("config.json")
    if root_config.exists():
        if check_config_file(root_config):
            modified_count += 1

    # Strategies
    strategy_dir = Path("user_data/strategies")
    if strategy_dir.exists():
        for f in strategy_dir.glob("*.py"):
            if check_strategy_file(f):
                modified_count += 1

    if modified_count > 0:
        print(f"Fixed {modified_count} violations.")
    else:
        print("No violations found.")


if __name__ == "__main__":
    main()
