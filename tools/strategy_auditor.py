#!/usr/bin/env python3
import ast
import os
import sys
import argparse
from pathlib import Path


REQUIRED_HEADER_SECTIONS = [
    "Strategy", "Author", "Version", "Timeframes",
    "Pair Format", "Timezone", "Entry", "Exit", "No repainting"
]


def is_named_variable(node):
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
        return is_named_variable(node.operand)
    return False


def validate_condition(node, lineno, errors):
    # Allow single Name or ~Name
    if is_named_variable(node):
        return

    # If it's a BoolOp (A & B), check all values
    if isinstance(node, ast.BoolOp):
        for val in node.values:
            if not is_named_variable(val):
                errors.append(
                    f"Complex condition in dataframe.loc at line {lineno}. Use named boolean variables (e.g., `long_cond = ...`)."
                )
                return
    else:
        # Any other type (Compare, Call, etc.) is considered "unreadable one-liner" for this strict rule
        errors.append(
            f"Inline condition in dataframe.loc at line {lineno}. Use named boolean variables."
        )


def check_trend_method(node, errors):
    # Check for docstring (thesis)
    if not ast.get_docstring(node):
        errors.append(f"Method '{node.name}' missing docstring explaining market thesis")

    # Check logic
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            # Check for dataframe.loc[...] = ...
            for target in child.targets:
                if isinstance(target, ast.Subscript):
                    # Check if target is dataframe.loc
                    is_df_loc = False
                    # target.value -> Attribute(value=Name(id='dataframe'), attr='loc')
                    if isinstance(target.value, ast.Attribute) and target.value.attr == "loc":
                        if isinstance(target.value.value, ast.Name) and target.value.value.id == "dataframe":
                            is_df_loc = True

                    if is_df_loc:
                        # Check slice
                        sl = target.slice
                        if isinstance(sl, ast.Index):
                            sl = sl.value  # Py<3.9

                        # If tuple (row, col), take row
                        if isinstance(sl, ast.Tuple):
                            row = sl.elts[0]
                        else:
                            row = sl

                        # Analyze row indexer
                        validate_condition(row, child.lineno, errors)


def fix_header(filepath):
    with open(filepath, 'r') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"Cannot fix {filepath}: Syntax Error")
        return

    doc_node = None
    if tree.body and isinstance(tree.body[0], ast.Expr) and \
       (isinstance(tree.body[0].value, ast.Constant) or isinstance(tree.body[0].value, ast.Str)):
        doc_node = tree.body[0]

    required = {
        "Strategy": Path(filepath).stem,
        "Author": "(Unknown)",
        "Version": "1.0",
        "Timeframes": "1h",
        "Pair Format": "Delta (BTCUSDT)",
        "Timezone": "UTC ISO-8601",
        "Entry": "Describe entry conditions",
        "Exit": "Describe exit conditions",
        "No repainting": "Logic runs on closed candles"
    }

    if doc_node:
        existing_doc = ast.get_docstring(tree)
        if not existing_doc:
            existing_doc = ""

        # Check what's missing
        missing_keys = []
        for key in required:
            if key.lower() not in existing_doc.lower():
                missing_keys.append(key)

        if not missing_keys:
            return

        print(f"Fixing header in {filepath} (appending missing sections)...")
        new_content = existing_doc.strip() + "\n\n" + "-" * 20 + "\n"
        for key in missing_keys:
            new_content += f"{key}: {required[key]}\n"

        # Replace in source
        lines = source.splitlines(keepends=True)
        start_line = doc_node.lineno - 1
        end_line = doc_node.end_lineno

        new_doc_block = f'"""\n{new_content}\n"""'

        # We replace the lines.
        # Note: If the docstring is on one line but we expand it, it's fine.
        lines[start_line:end_line] = [new_doc_block + "\n"]

        with open(filepath, 'w') as f:
            f.writelines(lines)

    else:
        print(f"Fixing header in {filepath} (creating new)...")
        content = "\n".join([f"{k}: {v}" for k, v in required.items()])
        new_doc_block = f'"""\n{content}\n"""\n'
        with open(filepath, 'w') as f:
            f.write(new_doc_block + source)


def audit_file(filepath, fix=False):  # noqa: C901
    if fix:
        fix_header(filepath)
        # Re-read source after fix to audit correctly?
        # Yes, but usually we fix then audit.

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
    doc = ast.get_docstring(tree)
    if not doc:
        errors.append("Missing module docstring (Header block)")
    else:
        missing = [s for s in REQUIRED_HEADER_SECTIONS if s.lower() not in doc.lower()]
        if missing:
            errors.append(f"Missing header sections: {', '.join(missing)}")

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
                if node.func.attr == "now":
                    if not node.args and not node.keywords:
                        errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")

    # Check 4: Class definitions (Inheritance, Attributes, Methods)
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True

            # Inheritance check
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                 if filepath.endswith("DeltaSafeStrategy.py"):
                    errors.append("DeltaSafeStrategy must inherit AuditedStrategyMixin")

            # Attribute check: process_only_new_candles
            has_proc_candles = False
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id == "process_only_new_candles":
                            # Check if True
                            if (isinstance(item.value, ast.Constant) and item.value.value is True) or \
                               (isinstance(item.value, ast.NameConstant) and item.value.value is True):
                                has_proc_candles = True
            if not has_proc_candles:
                errors.append("Strategy must set process_only_new_candles = True")

            # Method checks
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name in ["populate_entry_trend", "populate_exit_trend", "populate_entry_trend_short", "populate_exit_trend_short"]:
                        check_trend_method(item, errors)

    if not has_class:
        # Might be a library file
        pass

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Audit strategies for Freqtrade/Delta compliance.")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
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
