#!/usr/bin/env python3
import argparse
import ast
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

HEADER_TEMPLATE = """\"\"\"
Strategy Name: {name}
Author: {author}
Version: {version}
Supported Timeframes: {timeframes}

Supported Pair Format Notes:
- Delta contract symbols (e.g., BTCUSDT) must be mapped to Freqtrade/CCXT futures pair format.
  (base/quote:settle like BTC/USDT:USDT).

Timezone Rule:
- All timestamps logged as UTC ISO-8601.

Entry/Exit Definitions:
- Long Entry: {long_entry}
- Long Exit: {long_exit}
- Short Entry: {short_entry}
- Short Exit: {short_exit}

No Repainting Note:
- Only act on closed candles (no incomplete candle usage).
\"\"\"
"""

REQUIRED_HEADER_FIELDS = [
    "Strategy Name",
    "Author",
    "Version",
    "Supported Timeframes",
    "Supported Pair Format Notes",
    "Timezone Rule",
    "Entry/Exit Definitions",
    "No Repainting Note",
]


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self, filepath, fix=False):
        self.filepath = filepath
        self.fix = fix
        self.errors = []
        self.has_docstring = False
        self.docstring_node = None
        self.populate_entry_trend_valid = True
        self.populate_exit_trend_valid = True
        self.inherits_mixin = False
        self.class_node = None

    def visit_Module(self, node):
        self.docstring_node = ast.get_docstring(node)
        if self.docstring_node:
            self.has_docstring = True
            self.check_docstring(self.docstring_node)
        else:
            self.errors.append("Missing module docstring (Header block)")

        self.generic_visit(node)

    def check_docstring(self, docstring):
        missing_fields = []
        for field in REQUIRED_HEADER_FIELDS:
            if field not in docstring:
                missing_fields.append(field)

        if missing_fields:
            self.errors.append(f"Header missing fields: {', '.join(missing_fields)}")

    def visit_ClassDef(self, node):
        self.class_node = node
        # Check inheritance
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
            self.errors.append(
                f"Strategy class '{node.name}' must inherit AuditedStrategyMixin"
            )
        elif "IStrategy" in bases:
            self.inherits_mixin = True

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in ["populate_entry_trend", "populate_exit_trend"]:
            self.check_populate_trend(node)
        self.generic_visit(node)

    def check_populate_trend(self, node):
        # Check for named boolean sub-conditions
        # We look for assignments to .loc where the index is complex but not a variable

        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    self._check_assignment_target(target, node, child.lineno)

    def _check_assignment_target(self, target, node, lineno):
        if not isinstance(target, ast.Subscript):
            return

        # dataframe.loc[index, col] = 1
        # We are interested in 'index'
        slice_node = target.slice
        # Python < 3.9 wraps slice in Index
        if isinstance(slice_node, ast.Index):
            slice_node = slice_node.value

        # If index is a tuple (row_indexer, col_indexer)
        row_indexer = slice_node
        if isinstance(slice_node, ast.Tuple):
            if len(slice_node.elts) >= 1:
                row_indexer = slice_node.elts[0]

        self._check_row_indexer(row_indexer, node, lineno)

    def _check_row_indexer(self, row_indexer, node, lineno):
        if isinstance(row_indexer, ast.BoolOp):
            # It is a boolean operation.
            # specifically, we want to see if the values are Variables (Names)
            # or complex expressions
            # E.g. (df['rsi'] < 30) & (df['volume'] > 0) is complex inline
            # condition1 & condition2 is named variables

            is_complex = False
            for val in row_indexer.values:
                if not isinstance(val, ast.Name):
                    is_complex = True
                    break

            if is_complex:
                self.errors.append(
                    f"Method '{node.name}' has complex inline condition at line {lineno}. "
                    "Use named boolean variables."
                )
        elif isinstance(row_indexer, ast.BinOp):
            # Bitwise operators like & |
            self._check_binop(row_indexer, node, lineno)

    def _check_binop(self, row_indexer, node, lineno):
        if not (
            isinstance(row_indexer.left, ast.Name) and isinstance(row_indexer.right, ast.Name)
        ):
            # It might be recursive, but let's flag if top level is not names
            # Actually, even (cond1 & cond2) is fine if cond1/2 are names.
            # But (df['x'] > 1) & (df['y'] < 2) is what we want to avoid.

            # Let's check if the leaves of the expression tree are Names
            # If we find a Compare node (e.g. df['x'] > 1), it's inline logic.

            for sub_node in ast.walk(row_indexer):
                if isinstance(sub_node, ast.Compare):
                    self.errors.append(
                        f"Method '{node.name}' has inline comparison at line {lineno}. "
                        "Use named boolean variables."
                    )
                    break


def check_comments(tree, source, visitor):
    # Check for comments in entry/exit methods (manual scan as AST drops comments)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
        ]:
            start = node.lineno
            end = (
                node.end_lineno
                if hasattr(node, "end_lineno")
                else start + len(node.body)
            )  # approximate

            has_comment = False
            for i in range(start - 1, end):  # lines are 1-indexed
                if i < len(lines):
                    line = lines[i].strip()
                    if "#" in line:
                        has_comment = True
                        break

            if not has_comment:
                visitor.errors.append(
                    f"Method '{node.name}' missing comments explaining market thesis."
                )


def apply_fix(filepath):
    # Auto-insert header
    logger.info("Auto-inserting missing header...")
    name = Path(filepath).stem

    header = HEADER_TEMPLATE.format(
        name=name,
        author="Unknown",
        version="1.0",
        timeframes="1h, 5m",
        long_entry="Describe long entry conditions here",
        long_exit="Describe long exit conditions here",
        short_entry="Describe short entry conditions here",
        short_exit="Describe short exit conditions here",
    )

    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            source = f.read()

        new_source = header + source
        with Path(filepath).open("w", encoding="utf-8") as f:
            f.write(new_source)
        logger.info("Header inserted. Please fill in the details.")
        return True
    except Exception as e:
        logger.error(f"Failed to write fix: {e}")
        return False


def audit_file(filepath, fix=False):
    logger.info(f"Auditing {filepath}...")
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        logger.error(f"FAIL: Could not read {filepath}: {e}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.error(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    visitor = StrategyVisitor(filepath, fix=fix)
    visitor.visit(tree)

    check_comments(tree, source, visitor)

    if fix and not visitor.has_docstring:
        if apply_fix(filepath):
            # Clear docstring error since we fixed it
            visitor.errors = [
                e for e in visitor.errors if "Missing module docstring" not in e
            ]

    if visitor.errors:
        for e in visitor.errors:
            logger.error(f"  - {e}")
        return False

    logger.info("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Audit strategies for compliance.")
    parser.add_argument(
        "path",
        nargs="?",
        default="user_data/strategies",
        help="Path to strategy file or directory",
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")

    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        logger.error(f"Target {target} does not exist.")
        sys.exit(1)

    failed = False

    if target.is_file():
        if not audit_file(str(target), fix=args.fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if (
                    file.endswith(".py")
                    and not file.startswith("__")
                    and file != "AuditedStrategyMixin.py"
                ):
                    if not audit_file(str(Path(root) / file), fix=args.fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
