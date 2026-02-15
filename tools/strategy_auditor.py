#!/usr/bin/env python3
import argparse
import ast
import os
import sys
from pathlib import Path


REQUIRED_HEADER_FIELDS = [
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

HEADER_TEMPLATE = """\"\"\"
Strategy Name: {name}
Author: {author}
Version: {version}
Supported Timeframes: {timeframes}

Supported Pair Format:
  - Delta contract symbols (e.g., BTCUSDT) vs Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT)

Timezone Rule:
  - All timestamps logged as UTC ISO-8601

Entry Conditions:
  - Long: {entry_long}
  - Short: {entry_short}

Exit Conditions:
  - Long: {exit_long}
  - Short: {exit_short}

No Repainting:
  - Only act on closed candles (no incomplete candle usage)
\"\"\"
"""


class LogicVisitor(ast.NodeVisitor):
    def __init__(self, source_lines):
        self.errors = []
        self.source_lines = source_lines

    def visit_FunctionDef(self, node):
        if node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
            "populate_entry_trend_short",
            "populate_exit_trend_short",
        ]:
            self.check_logic(node)
        self.generic_visit(node)

    def check_logic(self, node):
        self._check_comments(node)
        self._check_complex_conditions(node)

    def _check_comments(self, node):
        # Check for comments in the function body
        has_comment = False
        start_line = node.lineno - 1
        end_line = node.end_lineno
        function_body_lines = self.source_lines[start_line:end_line]

        for line in function_body_lines:
            if "#" in line:
                has_comment = True
                break

        if not has_comment:
            # Check for docstring as alternative
            if not ast.get_docstring(node):
                self.errors.append(
                    f"Function {node.name} at line {node.lineno} "
                    "missing comments explaining market thesis"
                )

    def _check_complex_conditions(self, node):
        # Check for complex inline conditions
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Subscript):  # df.loc[...]
                        self._analyze_subscript(target, child, node)

    def _analyze_subscript(self, target, assign_node, func_node):
        # check if it is assigning to a column
        sl = target.slice
        if sys.version_info < (3, 9) and isinstance(sl, ast.Index):
            sl = sl.value

        condition_node = None
        if isinstance(sl, ast.Tuple):  # df.loc[cond, col]
            if len(sl.elts) > 0:
                condition_node = sl.elts[0]
        else:
            # df.loc[cond] = ... (rare for column assignment but possible)
            condition_node = sl

        if condition_node and self.is_complex(condition_node):
            self.errors.append(
                f"Complex inline condition in {func_node.name} at line {assign_node.lineno}. "
                "Use named boolean variables."
            )

    def is_complex(self, node):
        # If it's a BoolOp or BinOp, it's considered complex
        # Exception: UnaryOp is fine (~cond)
        if isinstance(node, (ast.BoolOp, ast.BinOp)):
            return True
        return False


def check_header(tree):
    docstring = ast.get_docstring(tree)
    if not docstring:
        return ["Missing module docstring (Header block)"]

    missing = []
    lower_doc = docstring.lower()

    for label in REQUIRED_HEADER_FIELDS:
        # Check roughly if the label exists in docstring
        # Normalize label for search
        search_term = label.lower().split(":")[0]
        if search_term not in lower_doc:
            missing.append(f"Header missing section: {label}")

    return missing


def fix_header(source_lines, filepath):
    print(f"Fixing header in {filepath}...")
    new_header = HEADER_TEMPLATE.format(
        name=Path(filepath).stem,
        author="Unknown",
        version="1.0",
        timeframes="Unknown",
        entry_long="Fill me in",
        entry_short="Fill me in",
        exit_long="Fill me in",
        exit_short="Fill me in",
    )

    # Need to re-parse to find if there is an existing docstring
    # We can't use the tree passed to audit_file because we need line numbers relative
    # to source_lines
    source = "".join(source_lines)
    tree = ast.parse(source)

    # Check for existing docstring to replace
    doc_node = None
    if tree.body and isinstance(tree.body[0], ast.Expr):
        val = tree.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            doc_node = tree.body[0]
        elif isinstance(val, ast.Str):  # Python < 3.8
            doc_node = tree.body[0]

    if doc_node:
        # Replace existing docstring
        start = doc_node.lineno - 1
        end = doc_node.end_lineno
        source_lines[start:end] = [new_header]
    else:
        # Insert at top (after shebang)
        insert_idx = 0
        for i, line in enumerate(source_lines):
            if line.startswith("#!") or (line.startswith("#") and "coding" in line):
                insert_idx = i + 1
            else:
                break
        source_lines.insert(insert_idx, new_header)

    with Path(filepath).open("w") as f:
        f.writelines(source_lines)


def check_imports_and_usage(tree):
    errors = []
    # Check Unsafe Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")

    # Check datetime.now() usage
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":
                # Check if it has arguments (timezone)
                if not node.args and not node.keywords:
                    errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")
    return errors


def check_inheritance(tree):
    errors = []
    # Check Enforce AuditedStrategyMixin
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                errors.append("Strategy must inherit AuditedStrategyMixin")
    return errors


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    with Path(filepath).open() as f:
        source_lines = f.readlines()
    source = "".join(source_lines)

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []

    # Check 1: Header
    header_errors = check_header(tree)
    if header_errors:
        if fix:
            fix_header(source_lines, filepath)
            # Assume fixed
            header_errors = []
        errors.extend(header_errors)

    # Check 2 & 3: Imports and Usage
    errors.extend(check_imports_and_usage(tree))

    # Check 4: Enforce AuditedStrategyMixin
    errors.extend(check_inheritance(tree))

    # Check 5: "closed candle only" note
    if "closed candle" not in source.lower():
        errors.append("Missing 'closed candle' note/comment (Logic must run on closed candles)")

    # Check 6: Logic checks (Visitor)
    visitor = LogicVisitor(source_lines)
    visitor.visit(tree)
    errors.extend(visitor.errors)

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("target", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Automatically fix some issues")
    args = parser.parse_args()

    target = args.target
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
