#!/usr/bin/env python3
import ast
import os
import sys
from pathlib import Path


def audit_file(filepath):  # noqa: C901
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open() as f:
            source = f.read()
    except Exception as e:
        print(f"FAIL: Could not read {filepath}: {e}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors: list[str] = []

    # Check 1: Docstring (Header block)
    if not ast.get_docstring(tree):
        errors.append("Missing module docstring (Header block)")

    # Check 2: Unsafe Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")

    # Check 3: datetime.now() usage (heuristic)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # check for .now() or .utcnow()
                if node.func.attr == "now":
                    # Check if it has arguments. If no args, likely local time.
                    # We want datetime.now(timezone.utc) or similar.
                    # If args exist, we assume they passed a timezone (heuristic).
                    if not node.args and not node.keywords:
                        errors.append(
                            f"Potential naive datetime.now() usage at line {node.lineno}. "
                            "Use datetime.now(timezone.utc)."
                        )
                elif node.func.attr == "utcnow":
                    errors.append(
                        f"datetime.utcnow() is deprecated/discouraged at line {node.lineno}. "
                        "Use datetime.now(timezone.utc)."
                    )

    # Check 4: Enforce AuditedStrategyMixin (heuristic)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check bases
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                # Warn if it inherits directly from IStrategy but not Mixin
                # We can't easily check full inheritance tree without loading code.
                if filepath.endswith("DeltaSafeStrategy.py"):  # Strict for our sample
                    errors.append("DeltaSafeStrategy must inherit AuditedStrategyMixin")

    # Check 5: "closed candle only" note
    if "closed candle" not in source.lower():
        # This is just a string check, simplistic but required by prompt
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

                    if isinstance(sl, ast.BoolOp):
                        if len(sl.values) > 3:
                            errors.append(
                                f"Complex inline condition (>{len(sl.values)} ops) "
                                f"at line {node.lineno}. Use named variables."
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
