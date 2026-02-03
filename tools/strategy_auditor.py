#!/usr/bin/env python3
import argparse
import ast
import glob
import sys
from pathlib import Path


REQUIRED_HEADER_FIELDS = [
    "Strategy name",
    "Author",
    "Version",
    "Supported timeframes",
    "Supported pair format",
    "Timezone rule",
    "Entry conditions",
    "Exit conditions",
    "No repainting",
]

DEFAULT_HEADER = '''"""
Strategy name: {name}
Author: Unknown
Version: 1.0
Supported timeframes: 1h
Supported pair format: Base/Quote:Settle (e.g. BTC/USDT:USDT)
Timezone rule: UTC ISO-8601
Entry conditions: Check populate_entry_trend
Exit conditions: Check populate_exit_trend
No repainting: Validated
"""
'''


def check_header(node):
    docstring = ast.get_docstring(node)
    if not docstring:
        return False, "Missing module docstring"

    missing = []
    for field in REQUIRED_HEADER_FIELDS:
        if field not in docstring:
            missing.append(field)

    if missing:
        return False, f"Missing header fields: {', '.join(missing)}"

    return True, "Header OK"


def check_logic(node, filepath):  # noqa: C901
    issues = []

    # Find strategy class
    class_node = None
    for item in node.body:
        if isinstance(item, ast.ClassDef):
            # Heuristic: inherits from IStrategy or has populate_ methods
            # For now assume the first class is the strategy
            class_node = item
            break

    if not class_node:
        # If no class found, maybe it's not a strategy file or just helper
        # We can skip logic checks but warn.
        return []

    methods_to_check = ["populate_entry_trend", "populate_exit_trend"]

    with Path(filepath).open() as f:
        file_lines = f.readlines()

    for method_name in methods_to_check:
        method_node = None
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                method_node = item
                break

        if not method_node:
            continue

        # Check for comments
        # AST nodes have lineno (1-based)
        start_line = method_node.lineno - 1
        end_line = getattr(method_node, "end_lineno", start_line + len(method_node.body))

        method_text = "".join(file_lines[start_line:end_line])
        if "#" not in method_text:
            issues.append(f"Method {method_name} missing comments explaining logic")

        # Check for complex boolean conditions in .loc assignments
        # Use ast.walk to check nested statements (e.g. inside if/for)
        for child_node in ast.walk(method_node):
            if isinstance(child_node, ast.Assign):
                for target in child_node.targets:
                    if isinstance(target, ast.Subscript):
                        slice_node = target.slice

                        # Unwrap Index if present (Python < 3.9)
                        if isinstance(slice_node, ast.Index):
                            slice_node = slice_node.value

                        # Handle Tuple (row, col)
                        mask = slice_node
                        if isinstance(slice_node, ast.Tuple):
                            if len(slice_node.elts) > 0:
                                mask = slice_node.elts[0]

                        # Check if mask is a BoolOp (and/or) or BinOp (bitwise & / |)
                        if isinstance(mask, ast.BoolOp):
                            issues.append(
                                f"Line {child_node.lineno}: Method {method_name} has complex "
                                "boolean condition (and/or) in .loc. Extract to named variable."
                            )
                        elif isinstance(mask, ast.BinOp) and isinstance(
                            mask.op, (ast.BitAnd, ast.BitOr)
                        ):
                            issues.append(
                                f"Line {child_node.lineno}: Method {method_name} has complex "
                                "boolean condition (&/|) in .loc. Extract to named variable."
                            )

    return issues


def audit_file(strat_path: Path, fix: bool = False) -> bool:
    """
    Audits a single strategy file.
    Returns True if failed, False if OK (or fixed).
    """
    print(f"Checking {strat_path}...")
    failed = False
    try:
        with strat_path.open() as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"ERROR: Could not parse {strat_path}: {e}")
        return True

    # Header Check
    header_ok, header_msg = check_header(tree)

    if not header_ok:
        if fix and "Missing module docstring" in header_msg:
            print(f"FIXING: Adding header to {strat_path}")
            name = strat_path.stem
            new_header = DEFAULT_HEADER.format(name=name)
            with strat_path.open("w") as f:
                f.write(new_header + source)

            # Re-read source to verify logic
            with strat_path.open() as f:
                source = f.read()
            tree = ast.parse(source)
            header_ok = True
            print("Header added.")
        else:
            print(f"FAIL: {header_msg}")
            failed = True

    # Logic Check
    issues = check_logic(tree, strat_path)
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
        failed = True

    if header_ok and not issues:
        print("OK")

    return failed


def main():
    parser = argparse.ArgumentParser(description="Audit strategies for compliance.")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    parser.add_argument("strategies", nargs="*", help="Strategies to check")

    args = parser.parse_args()

    # Collect files
    strategies_paths = []
    input_patterns = args.strategies if args.strategies else ["user_data/strategies/*.py"]

    for pattern in input_patterns:
        # Check if it's a direct file
        p = Path(pattern)
        if p.is_file():
            strategies_paths.append(p)
        else:
            # Expand glob
            expanded = list(glob.glob(pattern))  # noqa: PTH207
            if not expanded and "*" not in pattern:
                print(f"Warning: {pattern} not found.")
            strategies_paths.extend([Path(x) for x in expanded])

    # Filter out __init__.py and _base directory
    strategies_paths = [
        s for s in strategies_paths if s.name != "__init__.py" and "_base" not in str(s)
    ]

    # Remove duplicates
    strategies_paths = sorted(list(set(strategies_paths)))

    any_failed = False
    for strat_path in strategies_paths:
        if audit_file(strat_path, args.fix):
            any_failed = True

    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
