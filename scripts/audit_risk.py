import ast
import json
import sys
from pathlib import Path


def audit_config(filepath: Path) -> bool:
    try:
        with filepath.open() as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"WARNING: Could not parse JSON {filepath}")
                return False

            if isinstance(data, dict) and "max_open_trades" in data:
                val = data["max_open_trades"]
                if isinstance(val, (int, float)) and val > 5:
                    print(f"ERROR: {filepath} has max_open_trades={val} > 5")
                    return False
    except Exception as e:
        print(f"WARNING: Error auditing {filepath}: {e}")
        return False
    return True


def get_stoploss_from_node(node: ast.Assign) -> float | None:
    val = None
    # Use ast.Constant for literals (Python 3.8+)
    if isinstance(node.value, ast.Constant):
        val = node.value.value
    elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
        if isinstance(node.value.operand, ast.Constant):
            operand_val = node.value.operand.value
            if isinstance(operand_val, (int, float)):
                val = -operand_val
    return val


def check_stoploss_in_class(class_node: ast.ClassDef, filepath: Path) -> bool:
    for item in class_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "stoploss":
                    val = get_stoploss_from_node(item)

                    if val is not None and isinstance(val, (int, float)):
                        if val < -0.10:
                            print(
                                f"ERROR: {filepath} has stoploss={val} "
                                "which is strictly looser than -0.10"
                            )
                            return False
    return True


def audit_strategy(filepath: Path) -> bool:
    try:
        with filepath.open() as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                print(f"WARNING: SyntaxError in {filepath}")
                return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not check_stoploss_in_class(node, filepath):
                    return False
    except Exception as e:
        print(f"WARNING: Error auditing {filepath}: {e}")
        return False
    return True


def main():
    success = True
    base_dir = Path("user_data")

    # Check config.json in root if exists
    root_config = Path("config.json")
    if root_config.exists():
        if not audit_config(root_config):
            success = False

    # Check recursively in user_data
    if base_dir.exists():
        for filepath in base_dir.rglob("*"):
            if filepath.suffix == ".json":
                if not audit_config(filepath):
                    success = False
            elif filepath.suffix == ".py":
                if not audit_strategy(filepath):
                    success = False
    else:
        print(f"WARNING: {base_dir} does not exist.")

    if not success:
        sys.exit(1)
    else:
        print("Audit successful: No violations found.")


if __name__ == "__main__":
    main()
