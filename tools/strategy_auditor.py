#!/usr/bin/env python3
import argparse
import ast
import contextlib
import os
import sys
from pathlib import Path


def check_header(docstring, errors):
    if not docstring:
        errors.append("Missing module docstring (Header block)")
        return

    required_keywords = [
        "Strategy name",
        "Author",
        "Version",
        "Supported timeframes",
        "Supported pair format",
        "Timezone",
        "Entry",
        "Exit",
        "No repainting",
    ]

    missing = []
    lower_doc = docstring.lower()
    for kw in required_keywords:
        if kw.lower() not in lower_doc:
            if kw == "Entry" and ("long entry" in lower_doc or "short entry" in lower_doc):
                continue
            if kw == "Exit" and ("long exit" in lower_doc or "short exit" in lower_doc):
                continue
            if kw == "Supported timeframes" and "timeframe" in lower_doc:
                continue
            if kw == "Supported pair format" and (
                "pair format" in lower_doc or "symbols" in lower_doc
            ):
                continue

            missing.append(kw)

    if missing:
        errors.append(f"Header missing sections: {', '.join(missing)}")


def check_boolean_logic(tree, source, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
        ]:
            check_method_logic(node, errors)
            check_method_comments(node, source, errors)


def check_method_comments(node, source, errors):
    with contextlib.suppress(Exception):
        segment = ast.get_source_segment(source, node)
        if segment and "#" not in segment:
            errors.append(
                f"Method {node.name} missing comments explaining the market thesis."
            )


def check_method_logic(method_node, errors):
    for node in ast.walk(method_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if (
                        isinstance(target.value, ast.Attribute)
                        and target.value.attr == "loc"
                    ):
                        check_loc_index(target.slice, node.lineno, errors)


def is_safe_expression(node):
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Name):
        return True
    if isinstance(node, ast.BinOp):
        return is_safe_expression(node.left) and is_safe_expression(node.right)
    return False


def check_loc_index(slice_node, lineno, errors):
    if isinstance(slice_node, ast.Index):
        slice_node = slice_node.value

    node_to_check = slice_node

    if isinstance(slice_node, ast.Tuple):
        if slice_node.elts:
            node_to_check = slice_node.elts[0]

    if not is_safe_expression(node_to_check):
        if isinstance(node_to_check, (ast.BinOp, ast.BoolOp, ast.Compare)):
            errors.append(
                f"Line {lineno}: Complex inline boolean condition found. "
                "Use named boolean variables for clarity."
            )


def fix_file_header(filepath, tree):
    strategy_name = "UnknownStrategy"
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            strategy_name = node.name
            break

    header = f'''"""
Strategy Name: {strategy_name}
Author: Unknown
Version: 1.0
Supported timeframes: 1h, 4h
Supported pair format: Delta Futures (e.g. BTCUSDT) normalized to BASE/QUOTE:SETTLE
Timezone: UTC ISO-8601
Entry definitions:
  - Long entry: RSI < 30
Exit definitions:
  - Long exit: RSI > 70
No repainting: Logic runs on closed candles only.
"""
'''
    with Path(filepath).open("r", encoding="utf-8") as f:
        content = f.read()

    if ast.get_docstring(tree):
        print(f"  - Docstring exists but incomplete. Manual fix required for {filepath}.")
        return False
    else:
        new_content = header + "\n" + content
        with Path(filepath).open("w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  - Inserted header for {filepath}")
        return True


def run_audit_checks(tree, source, errors):
    docstring = ast.get_docstring(tree)
    check_header(docstring, errors)
    check_boolean_logic(tree, source, errors)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                errors.append("Strategy class must inherit AuditedStrategyMixin")


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open(encoding="utf-8") as f:
            source = f.read()
    except Exception as exc:
        print(f"FAIL: Could not read {filepath}: {exc}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []
    run_audit_checks(tree, source, errors)

    if errors:
        for err in errors:
            print(f"  - {err}")

        if fix and "Missing module docstring" in "".join(errors):
            fix_file_header(filepath, tree)

        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Audit strategy files.")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix errors (Header only)")
    args = parser.parse_args()

    target = Path(args.path)
    failed = False

    if target.is_file():
        if not audit_file(str(target), args.fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if not audit_file(str(Path(root) / file), args.fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
