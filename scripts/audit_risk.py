#!/usr/bin/env python3
"""
Risk Audit Script
Enforces risk limits on configuration and strategy files.
Limits:
- max_open_trades <= 5 (in config.json and user_data/configs/*.json)
- stoploss >= -0.10 (in user_data/strategies/*.py)
"""

import ast
import json
import sys
from pathlib import Path


# Limits
MAX_OPEN_TRADES_LIMIT = 5
STOPLOSS_LIMIT = -0.10  # Must be >= -0.10 (e.g. -0.05 is ok, -0.20 is not)


def check_and_fix_config(filepath: Path) -> bool:
    """
    Checks and fixes max_open_trades in a JSON config file.
    Returns True if file was modified.
    """
    try:
        with filepath.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error decoding JSON in {filepath}")
        return False
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    modified = False

    if "max_open_trades" in data:
        val = data["max_open_trades"]
        # If it's -1 (unlimited) or > 5, it's a violation.
        # Wait, usually -1 means unlimited which is definitely > 5 trades.
        # The constraint is "never > 5". So -1 is a violation.
        # But wait, is -1 treated as infinity? Yes.
        # So check: if val == -1 or val > MAX_OPEN_TRADES_LIMIT:

        is_violation = False
        if isinstance(val, (int, float)):
            if val == -1 or val > MAX_OPEN_TRADES_LIMIT:
                is_violation = True

        if is_violation:
            print(f"Violation in {filepath}: max_open_trades={val} > {MAX_OPEN_TRADES_LIMIT}")
            data["max_open_trades"] = MAX_OPEN_TRADES_LIMIT
            modified = True

    if modified:
        try:
            with filepath.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print(f"Fixed {filepath}: Set max_open_trades to {MAX_OPEN_TRADES_LIMIT}")
            return True
        except Exception as e:
            print(f"Error writing {filepath}: {e}")
            return False

    return False


def get_stoploss_value(node: ast.Assign) -> float | None:
    """Extract stoploss value from an AST Assign node."""
    value_node = node.value
    val = None

    if isinstance(value_node, ast.Constant):  # Python 3.8+
        val = value_node.value
    elif isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
        operand = value_node.operand
        if isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float)):
            val = -operand.value

    if isinstance(val, (int, float)):
        return float(val)
    return None


def process_stoploss_node(
    node: ast.Assign, lines: list[str], filepath: Path
) -> bool:
    """Check if node is a stoploss assignment and fix if needed."""
    # Check targets
    is_stoploss = False
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "stoploss":
            is_stoploss = True
            break

    if not is_stoploss:
        return False

    val = get_stoploss_value(node)

    if val is not None:
        # Constraint: stoploss >= -0.10
        # e.g. -0.05 is OK (-0.05 >= -0.10)
        # -0.20 is Violation (-0.20 < -0.10)
        if val < STOPLOSS_LIMIT:
            print(
                f"Violation in {filepath} line {node.lineno}: stoploss={val} < {STOPLOSS_LIMIT}"
            )

            # Fix it
            # We use line number to replace the line.
            # But we must preserve indentation.
            line_idx = node.lineno - 1
            original_line = lines[line_idx]

            # Heuristic to preserve indentation:
            # Find the indentation of the original line
            indent = len(original_line) - len(original_line.lstrip())
            indent_str = original_line[:indent]

            # Replace line
            # Assuming simple assignment: stoploss = -0.20
            # We replace with: stoploss = -0.10
            # We try to keep comments if any?
            # Simplest is to just rewrite the assignment.
            if "#" in original_line:
                comment = original_line.split("#", 1)[1]
                new_line = (
                    f"{indent_str}stoploss = {STOPLOSS_LIMIT}  "
                    f"# {comment.strip()} (Fixed by Audit)"
                )
            else:
                new_line = f"{indent_str}stoploss = {STOPLOSS_LIMIT}"

            lines[line_idx] = new_line
            return True
    return False


def check_and_fix_strategy(filepath: Path) -> bool:
    """
    Checks and fixes stoploss in a Python strategy file.
    Returns True if file was modified.
    """
    try:
        with filepath.open("r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        print(f"SyntaxError parsing {filepath}")
        return False

    modified = False
    lines = source.splitlines()

    # We look for class definitions, then assignments to stoploss within them.
    # But stoploss can also be defined at module level (less common for strategies
    # but possible if not inside class?)
    # Usually it's inside the class inheriting from IStrategy.
    # We'll just look for any assignment to 'stoploss' variable/attribute in the file.
    # This might catch false positives if 'stoploss' is used as a local variable,
    # but in a strategy file, top-level class attributes are the concern.
    # To be safer, we can check if it's inside a ClassDef.

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if process_stoploss_node(node, lines, filepath):
                modified = True

    if modified:
        try:
            with filepath.open("w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")  # Restore newline at end
            print(f"Fixed {filepath}: Set stoploss to {STOPLOSS_LIMIT}")
            return True
        except Exception as e:
            print(f"Error writing {filepath}: {e}")
            return False

    return False


def main():
    root = Path.cwd()
    modified_count = 0

    # 1. Check configs
    config_files = list(root.glob("config.json")) + list(
        root.glob("user_data/configs/*.json")
    )
    for cf in config_files:
        if check_and_fix_config(cf):
            modified_count += 1

    # 2. Check strategies
    # Also check recursively? The prompt says "user_data/strategies/*.py" which usually
    # implies top level, but strictly "strategies/*.py" could mean recursive if
    # using glob("**/*.py"). Given the previous ls, there is _base/AuditedStrategyMixin.py.
    # Usually mixins don't define stoploss, but if they do, we should check.
    # I'll check recursively just in case.
    strategy_files_recursive = list(root.glob("user_data/strategies/**/*.py"))

    for sf in strategy_files_recursive:
        if check_and_fix_strategy(sf):
            modified_count += 1

    if modified_count > 0:
        print(f"Audit complete. {modified_count} files fixed.")
        sys.exit(0)  # Success (changes made)
    else:
        print("Audit complete. No violations found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
