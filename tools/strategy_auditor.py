#!/usr/bin/env python3
import argparse
import ast
import sys
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
        no_repainting="Logic runs on closed candles only (process_only_new_candles=True)",
    )

    return shebang + header + source


def is_loc_assignment(target):
    """
    Checks if the target is a dataframe.loc assignment.
    Returns True if so.
    """
    if isinstance(target, ast.Subscript):
        if isinstance(target.value, ast.Attribute) and target.value.attr == "loc":
            if isinstance(target.value.value, ast.Name) and target.value.value.id == "dataframe":
                return True
    return False


def get_row_indexer(target):
    """
    Extracts the row indexer from a .loc assignment.
    """
    sl = target.slice
    # Python < 3.9 compatibility
    if isinstance(sl, ast.Index):
        sl = sl.value

    # If slice is a Tuple (row_indexer, col_indexer)
    if isinstance(sl, ast.Tuple):
        if len(sl.elts) >= 1:
            return sl.elts[0]
    else:
        return sl
    return None


def check_condition_complexity(node, child):
    """
    Checks if an assignment is a complex inline condition.
    Returns error string if complex, None otherwise.
    """
    for target in child.targets:
        if is_loc_assignment(target):
            row_indexer = get_row_indexer(target)
            if row_indexer:
                if isinstance(row_indexer, ast.BoolOp):
                    return (
                        f"Complex inline condition in {node.name} at line {child.lineno}. "
                        f"Use named variables."
                    )
                elif isinstance(row_indexer, ast.BinOp):
                    if not (
                        isinstance(row_indexer.left, (ast.Name, ast.UnaryOp))
                        and isinstance(row_indexer.right, (ast.Name, ast.UnaryOp))
                    ):
                        return (
                            f"Complex inline condition in {node.name} at line {child.lineno}. "
                            f"Use named variables."
                        )
    return None


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
                start_line = node.lineno
                # heuristic if old python
                end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10

                body_source = "\n".join(source_lines[start_line - 1 : end_line])
                if "#" not in body_source:
                    errors.append(f"Missing comments in {node.name} (explain the thesis)")

                # Check assignments to .loc
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        complexity_error = check_condition_complexity(node, child)
                        if complexity_error:
                            errors.append(complexity_error)

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
        errors.append("Missing 'process_only_new_candles = True' (No Repainting)")

    # 2. Check for UTC usage
    # We look for datetime.now() without timezone.utc
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                # Check args/keywords for timezone
                if node.args or node.keywords:
                    # heuristic: assumes if args present, likely timezone or we can't be sure
                    pass
                else:
                    errors.append(
                        f"Potential unsafe datetime.now() at line {node.lineno}. "
                        f"Use datetime.now(timezone.utc)."
                    )

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
            source_lines = source.splitlines()  # update lines
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
        for err in logic_errors:
            print(f"  FAIL: {err}")

    # 3. Safety Check
    safety_errors = check_safety(tree)
    if safety_errors:
        for err in safety_errors:
            print(f"  FAIL: {err}")

    # 4. Inheritance Check
    inheritance_errors = check_inheritance(tree, filepath)
    if inheritance_errors:
        for err in inheritance_errors:
            print(f"  FAIL: {err}")

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
                if f.name.startswith("__"):
                    continue
                if "AuditedStrategyMixin" in f.name:
                    continue
                if not audit_file(str(f), fix=args.fix):
                    failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
