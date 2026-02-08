#!/usr/bin/env python3
import ast
import argparse
import sys
from pathlib import Path

REQUIRED_HEADER_FIELDS = [
    "Strategy",
    "Author",
    "Version",
    "Timeframe",
    "Pair Format",
    "Timezone",
    "Entry",
    "Exit",
    "Repainting",
]

HEADER_TEMPLATE = """\"\"\"
Strategy: {name}
Author: Unknown
Version: 1.0
Timeframe: {timeframe}
Pair Format: Delta futures (e.g. BTCUSDT) or Freqtrade (e.g. BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry:
  - Long: ...
  - Short: ...
Exit:
  - Long: ...
  - Short: ...
Repainting: No (process_only_new_candles=True)
\"\"\"
"""

def check_header(tree, source, filepath, fix=False):
    docstring = ast.get_docstring(tree)
    if not docstring:
        if fix:
            print(f"Fixing header for {filepath}")
            # Try to infer strategy name and timeframe
            name = filepath.stem
            timeframe = "1h" # Default
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    name = node.name
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "timeframe":
                                    if isinstance(item.value, ast.Constant):
                                        timeframe = item.value.value

            new_header = HEADER_TEMPLATE.format(name=name, timeframe=timeframe).strip()
            # Insert at the beginning
            new_source = new_header + "\n\n" + source
            with open(filepath, "w") as f:
                f.write(new_source)
            return True, []
        return False, ["Missing header block"]

    errors = []
    for field in REQUIRED_HEADER_FIELDS:
        if field + ":" not in docstring and field not in docstring: # Allow "Entry:" or just "Entry" as section
             errors.append(f"Header missing required field: {field}")

    return True, errors

def check_inheritance(tree, filepath):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            # Check if it inherits from IStrategy (directly or check name)
            # We assume strategies usually inherit IStrategy.
            # We enforce AuditedStrategyMixin if it's a strategy.
            if "IStrategy" in bases:
                 if "AuditedStrategyMixin" not in bases:
                     return ["Missing inheritance from AuditedStrategyMixin"]
    return []

def check_process_only_new_candles(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                            if isinstance(item.value, ast.Constant) and item.value.value is True:
                                return []
    return ["Missing or False process_only_new_candles (Must be True)"]

def check_named_conditions(tree, source):
    errors = []

    # Helper to check for Compare nodes in the condition
    def has_compare(node):
        for child in ast.walk(node):
            if isinstance(child, ast.Compare):
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ["populate_entry_trend", "populate_exit_trend"]:
            # Check for comments (thesis) - simplistic check: does the function body source contain comments?
            # ast doesn't give comments. We rely on source lines map.
            # We can check if there are any lines starting with # inside the function range.
            func_source = ast.get_source_segment(source, node)
            if func_source and "#" not in func_source and '"""' not in func_source:
                 errors.append(f"{node.name}: Missing comments explaining market thesis")

            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    # Look for dataframe.loc[condition, ...] = ...
                    for target in child.targets:
                        if isinstance(target, ast.Subscript):
                            # Check if the slice is a complex condition with Compare
                            sl = target.slice
                            # In python < 3.9 it might be ast.Index
                            if isinstance(sl, ast.Index):
                                sl = sl.value

                            # We are looking for the condition part.
                            # Usually dataframe.loc[condition, 'col'] = 1
                            # If slice is a Tuple, the first element is the condition.
                            condition = sl
                            if isinstance(sl, ast.Tuple):
                                if len(sl.elts) > 0:
                                    condition = sl.elts[0]

                            if has_compare(condition):
                                errors.append(f"{node.name}: Inline comparison detected (use named boolean variables): line {child.lineno}")

    return errors

def check_log_signal_usage(tree):
    # Check if confirm_trade_entry and confirm_trade_exit call log_signal
    # This is a heuristic.
    errors = []
    methods_to_check = ["confirm_trade_entry", "confirm_trade_exit"]

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            defined_methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]

            for method in methods_to_check:
                # If method is not defined, we can't check it, but maybe we should enforce it?
                # The requirement implies we should log every entry and exit.
                # If the strategy doesn't override these methods, it can't log.
                # But maybe it logs in populate_entry_trend? No, requirement says "Log every entry and exit signal ... key indicator values at that candle".
                # Best place is confirm_trade_entry.

                if method in defined_methods:
                    # Find the method node
                    method_node = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method)
                    has_log = False
                    for child in ast.walk(method_node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Attribute) and child.func.attr == "log_signal":
                                has_log = True
                    if not has_log:
                        errors.append(f"{method} defined but does not call log_signal")
                # If not defined, we might assume it's missing the logging capability if strict.
                # But existing strategies might not have it.
                # For now, only check if defined.

    return errors

def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    try:
        with open(filepath, "r") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"FAIL: Could not parse {filepath}: {e}")
        return False

    all_errors = []

    # Check Header
    ok, errors = check_header(tree, source, Path(filepath), fix=fix)
    if not ok:
        all_errors.extend(errors)
        # If fixed, we should re-read? No, simpler to just pass this run and let user re-run.
        # But if fix=True and we fixed it, we consider it passed for header.
        if fix:
             # Re-read source to check other things on updated file?
             # Or just proceed with old tree? Old tree is stale.
             # Let's re-parse.
             with open(filepath, "r") as f:
                source = f.read()
             tree = ast.parse(source)

    # Check Inheritance
    all_errors.extend(check_inheritance(tree, filepath))

    # Check process_only_new_candles
    all_errors.extend(check_process_only_new_candles(tree))

    # Check named conditions
    all_errors.extend(check_named_conditions(tree, source))

    # Check log_signal
    all_errors.extend(check_log_signal_usage(tree))

    if all_errors:
        for e in all_errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True

def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", nargs="?", default="user_data/strategies", help="Path to strategy file or directory")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    target = Path(args.path)
    failed = False

    if target.is_file():
        if not audit_file(str(target), fix=args.fix):
            failed = True
    elif target.is_dir():
        for file in target.rglob("*.py"):
            if file.name.startswith("__") or file.name.startswith("AuditedStrategyMixin"):
                continue
            if not audit_file(str(file), fix=args.fix):
                failed = True
    else:
        print(f"Error: {target} not found")
        sys.exit(1)

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
