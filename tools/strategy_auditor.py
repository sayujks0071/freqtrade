#!/usr/bin/env python3
import ast
import sys
from pathlib import Path


def check_ast(node, errors):
    for child in ast.walk(node):
        # Check for network calls (requests, urllib)
        if isinstance(child, ast.Import):
            for alias in child.names:
                if alias.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Network import found: {alias.name} (Line {child.lineno})")
        elif isinstance(child, ast.ImportFrom):
            if child.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Network import found: {child.module} (Line {child.lineno})")

        # Check for datetime.now() usage (should use UTC or timeframe)
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute):
                if (
                    isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "datetime"
                    and child.func.attr == "now"
                ):
                    # Check if arguments are present (likely timezone)
                    if not child.args:
                        errors.append(
                            f"datetime.now() usage found (Line {child.lineno}). "
                            "Ensure usage of timezone.utc."
                        )


def check_source(source, filename):
    errors = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Syntax Error: {e}")
        return errors

    check_ast(tree, errors)

    # Text-based checks
    if "process_only_new_candles" not in source:
        errors.append("Missing 'process_only_new_candles' setting (potential repainting risk).")

    return errors


def main():
    if len(sys.argv) < 2 or "--help" in sys.argv:
        print("Usage: strategy_auditor.py <file_or_dir> [--fix]")
        sys.exit(0)

    target = Path(sys.argv[1])

    files = []
    if target.is_dir():
        for path in target.rglob("*.py"):
            if not path.name.startswith("__"):
                files.append(path)
    else:
        files.append(target)

    all_passed = True

    for fpath in files:
        print(f"Auditing {fpath}...")
        try:
            with fpath.open("r") as f:
                source = f.read()

            errors = check_source(source, str(fpath))

            if errors:
                all_passed = False
                print(f"FAIL: {fpath}")
                for e in errors:
                    print(f"  - {e}")
            else:
                print(f"PASS: {fpath}")

        except Exception as e:
            print(f"ERROR processing {fpath}: {e}")
            all_passed = False

    if not all_passed:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
