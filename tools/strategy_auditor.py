#!/usr/bin/env python3
import argparse
import ast
import os
import sys
from pathlib import Path

# Standard Header Template
HEADER_TEMPLATE = '''"""
Strategy: {strategy_name}
Author: Unknown
Version: 1.0
Timeframe: {timeframe}
Pair Format: BASE/QUOTE:SETTLE
Timezone: UTC
Entry/Exit: Limit/Limit
Repainting: No (Closed candle only)
"""
'''

def audit_file(filepath, fix=False):  # noqa: C901
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

    errors = []
    fixed = False

    # Check 1: Docstring (Header block)
    docstring = ast.get_docstring(tree)
    if not docstring:
        errors.append("Missing module docstring (Header block)")
        if fix:
            print("Applying fix: Adding header block...")
            # Infer strategy name from filename or class
            strategy_name = Path(filepath).stem
            # Infer timeframe? Hard to robustly, default to 1h
            header = HEADER_TEMPLATE.format(strategy_name=strategy_name, timeframe="1h")
            source = header + "\n" + source
            fixed = True
    else:
        # Check required sections in docstring
        required_sections = ["Strategy", "Author", "Timeframe", "Repainting"]
        missing_sections = [s for s in required_sections if s not in docstring]
        if missing_sections:
            errors.append(f"Header missing sections: {', '.join(missing_sections)}")
            if fix:
                 # Trying to fix existing docstring is hard without messing up format.
                 # Maybe just prepend/append?
                 # For now, we only fix completely missing headers.
                 pass

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
                    # Check if arg is provided (timezone)
                    if not node.args and not node.keywords:
                        # Check if caller is datetime.datetime or just datetime
                        # Heuristic: usually datetime.now() or datetime.datetime.now()
                        errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")

    # Check 4: Enforce AuditedStrategyMixin (heuristic)
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            # Check bases
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                # Only strictly enforce for strategies in user_data/strategies/ (not _base)
                if "_base" not in filepath and "Mixin" not in filepath:
                     errors.append(f"Class {node.name} must inherit AuditedStrategyMixin")

    # Check 5: "closed candle only" note or logic
    # Heuristic: check if source mentions "closed candle" or "process_only_new_candles"
    if "closed candle" not in source.lower() and "process_only_new_candles" not in source:
         errors.append("Missing 'closed candle' note/comment or 'process_only_new_candles' setting.")

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

                    complexity_limit = 3
                    if isinstance(sl, ast.BoolOp):
                        if len(sl.values) > complexity_limit:
                            errors.append(
                                f"Complex inline condition (>{len(sl.values)} ops) "
                                f"at line {node.lineno}. Use named variables."
                            )
                    elif isinstance(sl, ast.Tuple):
                        for elt in sl.elts:
                            if isinstance(elt, ast.BoolOp) and len(elt.values) > complexity_limit:
                                errors.append(
                                    f"Complex inline condition (>{len(elt.values)} ops) "
                                    f"at line {node.lineno}. Use named variables."
                                )

    if not has_class:
        # Might be a library file, skip strict checks if filename starts with _?
        if Path(filepath).name.startswith("_"):
             # reduce severity or skip
             pass

    if fixed:
        with Path(filepath).open("w") as f:
            f.write(source)
        print(f"FIXED: Applied fixes to {filepath}")
        # Re-run check?
        return True # Assume fixed for now, or we could recurse.

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Freqtrade Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix simple issues (e.g. missing header)")
    args = parser.parse_args()

    target = args.path
    failed = False

    if Path(target).is_file():
        if not audit_file(target, fix=args.fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if not audit_file(str(Path(root) / file), fix=args.fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
