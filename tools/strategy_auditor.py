#!/usr/bin/env python3
import ast
import os
import sys
from pathlib import Path


def audit_file(filepath):  # noqa: C901
    print(f"Auditing {filepath}...")
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
                if n.name in ["requests", "urllib", "socket", "http", "subprocess"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http", "subprocess"]:
                errors.append(f"Unsafe import from: {node.module}")

    # Check 3: datetime.now() usage (heuristic)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # check for .now()
                if node.func.attr == "now":
                    # This is loose, matches any .now()
                    # Check if it has arguments (timezone)
                    if not node.args and not node.keywords:
                        errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")

    # Check 4: Enforce AuditedStrategyMixin (heuristic)
    has_class = False
    process_candles_ok = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it looks like a strategy (inherits IStrategy)
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)

            if "IStrategy" in bases:
                has_class = True
                if "AuditedStrategyMixin" not in bases:
                    errors.append(f"Class {node.name} must inherit AuditedStrategyMixin")

                # Check process_only_new_candles = True in body
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for t in item.targets:
                            if isinstance(t, ast.Name) and t.id == "process_only_new_candles":
                                if (
                                    isinstance(item.value, ast.Constant)
                                    and item.value.value is True
                                ):
                                    process_candles_ok = True
                                elif (
                                    isinstance(item.value, ast.NameConstant)
                                    and item.value.value is True
                                ):  # Python < 3.8
                                    process_candles_ok = True

    if has_class and not process_candles_ok:
        errors.append("process_only_new_candles must be set to True")

    # Check 5: "closed candle only" note
    if "closed candle" not in source.lower():
        errors.append("Missing 'closed candle' note/comment (Logic must run on closed candles)")

    # Check 6: Complex conditions (named sub-conditions)
    # Heuristic: Check for assignments to dataframe with complex BoolOp index
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # We look for dataframe.loc[...] = ...
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    # Check slice (index)
                    sl = target.slice
                    # Handle python < 3.9 where slice might be wrapped
                    if isinstance(sl, ast.Index):
                        sl = sl.value

                    # Check tuple of conditions (common in loc)
                    conditions = []
                    if isinstance(sl, ast.Tuple):
                        conditions = sl.elts
                    else:
                        conditions = [sl]

                    for cond in conditions:
                        if isinstance(cond, ast.BoolOp):
                            # Check if it has many values (unnamed conditions)
                            # e.g. (a & b & c & d)
                            # If values are not simple Names, it's complex
                            complex_parts = 0
                            for v in cond.values:
                                if not isinstance(v, ast.Name):
                                    # Allow UnaryOp (invert) of Name
                                    if isinstance(v, ast.UnaryOp) and isinstance(
                                        v.operand, ast.Name
                                    ):
                                        continue
                                    # Allow Compare (x < y) if simple? No, prefer named vars
                                    complex_parts += 1

                            if complex_parts > 2:
                                errors.append(
                                    f"Complex inline condition at line {node.lineno}. "
                                    "Use named variables."
                                )

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_auditor.py <file_or_dir>")
        sys.exit(1)

    target = sys.argv[1]
    failed = False

    if Path(target).is_file():
        if not audit_file(target):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if not audit_file(str(Path(root) / file)):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
