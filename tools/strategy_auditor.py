#!/usr/bin/env python3
import argparse
import ast
import os
import sys
from pathlib import Path


def fix_header(filepath):
    """
    Adds a standard header to the strategy file if missing.
    """
    header = '''"""
Strategy: [Name]
Author: [Author]
Version: 1.0
Timeframe: 5m
Source: Audited Strategy
"""
'''
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Check if it already has a docstring at the top
        tree = ast.parse(content)
        if ast.get_docstring(tree):
            print(f"File {filepath} already has a docstring. Skipping fix.")
            return False

        with open(filepath, 'w') as f:
            f.write(header + "\n" + content)
        print(f"Added header to {filepath}")
        return True
    except Exception as e:
        print(f"Failed to fix {filepath}: {e}")
        return False


def audit_file(filepath, fix=False):  # noqa: C901
    print(f"Auditing {filepath}...")

    if fix:
        fix_header(filepath)

    with Path(filepath).open() as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []

    # Check 1: Docstring (Header block)
    if not ast.get_docstring(tree):
        errors.append("Missing module docstring (Header block)")

    # Check 2: Unsafe Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http", "os", "sys", "subprocess"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http", "os", "sys", "subprocess"]:
                errors.append(f"Unsafe import from: {node.module}")

    # Check 3: datetime.now() usage (heuristic)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "now":
                    # Check arguments for timezone info
                    if not node.args and not node.keywords:
                        errors.append(f"Potential naive datetime.now() usage at line {node.lineno}. Use UTC.")

    # Check 4: Enforce AuditedStrategyMixin inheritance
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)

            # If it inherits from IStrategy (directly or via mixin check context), it should use AuditedStrategyMixin
            # Simplistic check: if class name ends with Strategy and isn't a library/mixin itself
            if "Strategy" in node.name and node.name != "IStrategy":
                 if "AuditedStrategyMixin" not in bases and "IStrategy" in bases:
                     errors.append(f"Class {node.name} must inherit AuditedStrategyMixin")

    # Check 5: "closed candle only" note
    if "process_only_new_candles" not in source:
        errors.append("Missing 'process_only_new_candles' configuration (ensure safety).")

    # Check 6: Complex conditions (named sub-conditions)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    sl = target.slice
                    # Python < 3.9 compat
                    if isinstance(sl, ast.Index):
                        sl = sl.value

                    if isinstance(sl, ast.BoolOp):
                        if len(sl.values) > 3:
                            errors.append(
                                f"Complex inline condition (>{len(sl.values)} ops) "
                                f"at line {node.lineno}. Use named boolean variables."
                            )

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix missing headers")
    args = parser.parse_args()

    target = args.path
    failed = False

    if Path(target).is_file():
        if not audit_file(target, args.fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__") and "Mixin" not in file:
                    if not audit_file(str(Path(root) / file), args.fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
