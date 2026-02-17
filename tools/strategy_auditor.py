#!/usr/bin/env python3
import ast
import argparse
import sys
import re
from pathlib import Path

REQUIRED_HEADER_FIELDS = [
    "Strategy Name",
    "Author",
    "Version",
    "Supported Timeframes",
    "Supported Pair Format",
    "Timezone",
    "Entry Conditions",
    "Exit Conditions",
    "No Repainting",
]

HEADER_TEMPLATE = """\"\"\"
Strategy Name: {name}
Author: {author}
Version: {version}
Supported Timeframes: {timeframes}
Supported Pair Format: {pair_format}
Timezone: {timezone}

Entry Conditions:
  - Long: {entry_long}
  - Short: {entry_short}

Exit Conditions:
  - Long: {exit_long}
  - Short: {exit_short}

No Repainting: {no_repainting}
\"\"\"
"""

def check_header(source):
    """
    Checks if the source has a docstring with required fields.
    Returns (True, None) or (False, list_of_missing_fields).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, ["Syntax Error"]

    docstring = ast.get_docstring(tree)
    if not docstring:
        return False, REQUIRED_HEADER_FIELDS

    missing = []
    for field in REQUIRED_HEADER_FIELDS:
        if field not in docstring:
            missing.append(field)

    return len(missing) == 0, missing

def add_header(source, filepath):
    """
    Adds a template header to the source file.
    """
    # Try to preserve shebang
    lines = source.splitlines()
    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines[0] + "\n"
        source = "\n".join(lines[1:])

    # Defaults
    name = Path(filepath).stem
    header = HEADER_TEMPLATE.format(
        name=name,
        author="Unknown",
        version="1.0",
        timeframes="Unknown",
        pair_format="Delta Futures (BTC/USDT:USDT) -> Contract (BTCUSDT)",
        timezone="UTC (datetime.now(timezone.utc))",
        entry_long="Describe long entry",
        entry_short="Describe short entry (if any)",
        exit_long="Describe long exit",
        exit_short="Describe short exit (if any)",
        no_repainting="Logic runs on closed candles only (process_only_new_candles=True)"
    )

    return shebang + header + source

def check_logic(tree, source_lines):
    """
    Checks populate_entry_trend and populate_exit_trend.
    Returns a list of errors.
    """
    errors = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name in ["populate_entry_trend", "populate_exit_trend"]:
                # Check for comments in the function body
                # We use line numbers to scan source
                start_line = node.lineno
                end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10 # heuristic if old python

                body_source = "\n".join(source_lines[start_line-1:end_line])
                if "#" not in body_source:
                    errors.append(f"Missing comments in {node.name} (explain the thesis)")

                # Check assignments to .loc
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            # We look for dataframe.loc[condition, 'col'] = 1
                            if isinstance(target, ast.Subscript):
                                # Check if target.value is dataframe.loc (Attribute) or dataframe (Name)
                                # Pandas .loc usage: target.value is Attribute(value=Name(dataframe), attr='loc')
                                is_loc = False
                                if isinstance(target.value, ast.Attribute) and target.value.attr == "loc":
                                    if isinstance(target.value.value, ast.Name) and target.value.value.id == "dataframe":
                                        is_loc = True

                                if is_loc:
                                    # Check slice
                                    sl = target.slice
                                    # Python < 3.9 compatibility
                                    if isinstance(sl, ast.Index):
                                        sl = sl.value

                                    # If slice is a Tuple (row_indexer, col_indexer)
                                    row_indexer = None
                                    if isinstance(sl, ast.Tuple):
                                        if len(sl.elts) >= 1:
                                            row_indexer = sl.elts[0]
                                    else:
                                        row_indexer = sl

                                    if row_indexer:
                                        # Check if row_indexer is a complex BoolOp
                                        # We allow Name, Call (some functions), or simple comparison maybe?
                                        # User wants "named boolean sub-conditions".
                                        # So we reject BoolOp with multiple values inline.
                                        if isinstance(row_indexer, ast.BoolOp):
                                            errors.append(
                                                f"Complex inline condition in {node.name} at line {child.lineno}. "
                                                f"Use named variables."
                                            )
                                        elif isinstance(row_indexer, ast.BinOp):
                                            # Bitwise operators are BinOp in pandas context usually (&, |)
                                            # But ast treats & as BitAnd (BinOp)
                                            # If it's a simple BinOp, it might be okay?
                                            # But "named boolean sub-conditions" implies we want `dataframe.loc[long_cond, ...]`
                                            # So any BinOp (like `a & b`) is arguably "not a named variable".
                                            # However, we might allow `long_cond1 & long_cond2`.
                                            # If the operands are not Names, then it's complex.
                                            if not (isinstance(row_indexer.left, (ast.Name, ast.UnaryOp)) and
                                                    isinstance(row_indexer.right, (ast.Name, ast.UnaryOp))):
                                                 errors.append(
                                                    f"Complex inline condition in {node.name} at line {child.lineno}. "
                                                    f"Use named variables."
                                                )

    return errors

def check_safety(tree):
    errors = []

    # 1. Check for process_only_new_candles = True
    found_process_only = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                    if isinstance(node.value, ast.Constant) and node.value.value is True:
                        found_process_only = True
                    # python < 3.8
                    elif isinstance(node.value, ast.NameConstant) and node.value.value is True:
                        found_process_only = True

    if not found_process_only:
        # Check if it's defined in class scope
        pass
        # Actually the above walk covers class attributes too if they are Assign nodes.
        # But we should ensure it's True.
        # If not found, we warn.
        errors.append("Missing 'process_only_new_candles = True' (No Repainting)")

    # 2. Check for UTC usage
    # We look for datetime.now() without timezone.utc
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                # Check args/keywords for timezone
                has_tz = False
                if node.args or node.keywords:
                    # heuristic: assumes if args are present, it's likely timezone or we can't be sure
                    # We can check if arg is timezone.utc or datetime.UTC
                    pass
                else:
                    errors.append(f"Potential unsafe datetime.now() at line {node.lineno}. Use datetime.now(timezone.utc).")

    return errors

def check_inheritance(tree, filepath):
    errors = []
    # If file defines a Strategy class, it should inherit AuditedStrategyMixin
    # We assume the strategy class is the one that inherits IStrategy

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases:
                if "AuditedStrategyMixin" not in bases:
                    errors.append(f"Class {node.name} must inherit AuditedStrategyMixin")
    return errors

def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    path = Path(filepath)
    with path.open("r", encoding="utf-8") as f:
        source = f.read()

    source_lines = source.splitlines()

    # 1. Header Check
    valid_header, missing_fields = check_header(source)
    if not valid_header:
        if fix:
            print(f"  Fixing missing header in {filepath}...")
            new_source = add_header(source, filepath)
            with path.open("w", encoding="utf-8") as f:
                f.write(new_source)
            source = new_source
            source_lines = source.splitlines() # update lines
        else:
            print(f"  FAIL: Missing header fields: {', '.join(missing_fields)}")
            return False

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  FAIL: Syntax Error: {e}")
        return False

    # 2. Logic Check
    logic_errors = check_logic(tree, source_lines)
    if logic_errors:
        for e in logic_errors:
            print(f"  FAIL: {e}")

    # 3. Safety Check
    safety_errors = check_safety(tree)
    if safety_errors:
        for e in safety_errors:
            print(f"  FAIL: {e}")

    # 4. Inheritance Check
    inheritance_errors = check_inheritance(tree, filepath)
    if inheritance_errors:
        for e in inheritance_errors:
            print(f"  FAIL: {e}")

    if logic_errors or safety_errors or inheritance_errors:
        return False

    print("  PASS")
    return True

def main():
    parser = argparse.ArgumentParser(description="Audit Freqtrade strategies.")
    parser.add_argument("paths", nargs="+", help="Files or directories to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")

    args = parser.parse_args()

    failed = False

    for p in args.paths:
        path = Path(p)
        if path.is_file():
            if not audit_file(str(path), fix=args.fix):
                failed = True
        elif path.is_dir():
            for f in path.rglob("*.py"):
                if f.name.startswith("__"): continue
                if "AuditedStrategyMixin" in f.name: continue
                if not audit_file(str(f), fix=args.fix):
                    failed = True

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
