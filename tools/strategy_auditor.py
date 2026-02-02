#!/usr/bin/env python3
import argparse
import ast
import os
import sys
import tokenize
from io import BytesIO
from pathlib import Path

HEADER_TEMPLATE = """
    # Strategy Name: {name}
    # Author: {author}
    # Version: {version}
    # Supported Timeframes: {timeframes}
    # Supported Pair Format: {pair_format}
    # Timezone Rule: {timezone_rule}
    # Entry Conditions: {entry_conditions}
    # Exit Conditions: {exit_conditions}
    # No Repainting: {no_repainting}
"""

REQUIRED_FIELDS = [
    "Strategy Name",
    "Author",
    "Version",
    "Supported Timeframes",
    "Supported Pair Format",
    "Timezone Rule",
    "Entry Conditions",
    "Exit Conditions",
    "No Repainting",
]


def check_header(docstring):
    if not docstring:
        return False, ["Missing module docstring (Header block)"]

    missing = []
    for field in REQUIRED_FIELDS:
        if field not in docstring:
            missing.append(f"Missing header field: {field}")

    if "closed candle" not in docstring.lower() and "no repainting" not in docstring.lower():
        missing.append("Missing 'No Repainting' / 'closed candle' note in header")

    return (len(missing) == 0), missing


def fix_header(source, filepath):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    if ast.get_docstring(tree):
        pass
    else:
        print(f"Fixing header for {filepath}")
        name = Path(filepath).stem
        header = (
            '"""'
            + HEADER_TEMPLATE.format(
                name=name,
                author="Unknown",
                version="1.0",
                timeframes="1h",
                pair_format="Delta Futures (BTC/USDT:USDT)",
                timezone_rule="UTC ISO-8601",
                entry_conditions="Long on signal",
                exit_conditions="Short on signal",
                no_repainting="Only act on closed candles",
            )
            + '\n"""\n'
        )
        return header + source

    return source


def check_complex_conditions(node, errors):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                sl = target.slice
                if isinstance(sl, ast.Index):
                    sl = sl.value

                has_inline_logic = False
                for child in ast.walk(sl):
                    if isinstance(child, ast.Compare):
                        has_inline_logic = True
                        break

                if has_inline_logic:
                    errors.append(
                        f"Complex inline condition at line {node.lineno}. "
                        "Use named boolean variables (e.g., `long_cond = (df['rsi'] < 30)`)."
                    )


def check_comments_in_function(node, tokens, errors):
    start_line = node.lineno
    end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10

    has_comment = False
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            if start_line <= tok.start[0] <= end_line:
                has_comment = True
                break

    if not has_comment:
        errors.append(f"Missing comments explaining market thesis in {node.name}")


def check_imports(tree, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")


def check_datetime(tree, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                if not node.args and not node.keywords:
                    errors.append(
                        f"Naive datetime.now() usage at line {node.lineno}. "
                        "Use datetime.now(timezone.utc)"
                    )


def check_strategy_structure(tree, filepath, tokens, errors):
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                if filepath.endswith("DeltaSafeStrategy.py"):
                    errors.append("DeltaSafeStrategy must inherit AuditedStrategyMixin")

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name in [
                        "populate_entry_trend",
                        "populate_exit_trend",
                        "populate_entry_trend_short",
                        "populate_exit_trend_short",
                    ]:
                        check_comments_in_function(item, tokens, errors)
                        for stmt in item.body:
                            check_complex_conditions(stmt, errors)
    return has_class


def apply_fixes(filepath):
    with Path(filepath).open() as f:
        source = f.read()

    new_source = fix_header(source, filepath)
    if new_source != source:
        with Path(filepath).open("w") as f:
            f.write(new_source)
        print("  - Applied fixes (Header)")
        return new_source
    return source


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")

    if fix:
        source = apply_fixes(filepath)
    else:
        with Path(filepath).open() as f:
            source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []

    try:
        tokens = list(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
    except tokenize.TokenError:
        tokens = []

    docstring = ast.get_docstring(tree)
    _, header_errors = check_header(docstring)
    errors.extend(header_errors)

    check_imports(tree, errors)
    check_datetime(tree, errors)
    check_strategy_structure(tree, filepath, tokens, errors)

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues (missing header)")
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
