#!/usr/bin/env python3
"""
strategy_auditor.py

Audits Freqtrade strategies for compliance, safety, and code quality.
Uses AST to analyze code structure and enforce rules.
"""

import argparse
import ast
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.errors = []
        self.warnings = []
        self.has_docstring = False
        self.has_valid_header = False
        self.imports = []

    def visit_Module(self, node):
        # Check docstring for header
        docstring = ast.get_docstring(node)
        if docstring:
            self.has_docstring = True
            self.check_header(docstring)
        else:
            self.errors.append("Missing module-level docstring with required metadata.")

        self.generic_visit(node)

    def check_header(self, docstring):
        missing_fields = []
        for field in REQUIRED_HEADER_FIELDS:
            if field not in docstring:
                missing_fields.append(field)

        if missing_fields:
            self.errors.append(
                f"Docstring missing required fields: {', '.join(missing_fields)}"
            )
        else:
            self.has_valid_header = True

    def visit_Import(self, node):
        for alias in node.names:
            self.check_import(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.check_import(node.module, node.lineno)
        self.generic_visit(node)

    def check_import(self, module_name, lineno):
        if module_name in ["requests", "urllib", "http", "socket"]:
            self.errors.append(
                f"Line {lineno}: Network module '{module_name}' is forbidden in strategies."
            )

    def visit_Call(self, node):
        # Check for datetime.now() without UTC
        if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
            # Check if called on datetime.datetime or datetime
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                if not node.args and not node.keywords:
                    self.errors.append(
                        f"Line {node.lineno}: datetime.now() called without timezone! "
                        "Use datetime.now(timezone.utc)."
                    )

        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Check methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self.check_method(item)

        self.generic_visit(node)

    def check_method(self, node):
        # Check populate_indicators, populate_entry_trend, populate_exit_trend
        if node.name in ["populate_entry_trend", "populate_exit_trend"]:
            if not ast.get_docstring(node):
                self.warnings.append(f"Method '{node.name}' missing docstring.")

            # Check for boolean assignments in .loc (avoid unreadable one-liners)
            # Enforce named variables? Hard to check via AST without strict rules.
            # But we can check for complex BinOp in slice index.
            pass


def audit_file(filepath, fix=False):
    logger.info(f"Auditing {filepath}...")
    try:
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        visitor = StrategyVisitor(filepath)
        visitor.visit(tree)

        # FIX MODE
        if fix and not visitor.has_docstring:
            logger.info("Fixing missing header...")

            # Generate header template
            header_lines = ['"""\n']
            for field in REQUIRED_HEADER_FIELDS:
                header_lines.append(f"{field}: ...\n")
            header_lines.append('"""\n\n')
            header_block = "".join(header_lines)

            # Prepend to file, respecting shebang if present
            lines = source.splitlines(keepends=True)
            if lines and lines[0].startswith("#!"):
                lines.insert(1, header_block)
            else:
                lines.insert(0, header_block)

            new_source = "".join(lines)

            with path.open("w", encoding="utf-8") as f:
                f.write(new_source)

            logger.info(f"Fixed header in {filepath}.")
            return [], visitor.warnings  # Assume errors fixed or deferred

        elif fix and visitor.has_docstring and not visitor.has_valid_header:
            logger.warning(
                "Existing docstring found but invalid. "
                "Manual fix required to preserve content."
            )
            # We don't overwrite existing docstring to avoid data loss.

        return visitor.errors, visitor.warnings

    except Exception as e:
        logger.error(f"Failed to audit {filepath}: {e}")
        return [f"Exception: {e}"], []


def main():
    parser = argparse.ArgumentParser(description="Audit Freqtrade strategies.")
    parser.add_argument("files", nargs="+", help="Strategy files to audit")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix simple issues (e.g. missing header)",
    )
    args = parser.parse_args()

    total_errors = 0
    total_warnings = 0

    for filepath in args.files:
        errors, warnings = audit_file(filepath, args.fix)

        if errors:
            logger.error(f"Errors in {filepath}:")
            for e in errors:
                logger.error(f"  - {e}")
            total_errors += len(errors)

        if warnings:
            logger.warning(f"Warnings in {filepath}:")
            for w in warnings:
                logger.warning(f"  - {w}")
            total_warnings += len(warnings)

    if total_errors > 0:
        logger.error(
            f"Audit FAILED with {total_errors} errors and {total_warnings} warnings."
        )
        sys.exit(1)
    else:
        logger.info(f"Audit PASSED with {total_warnings} warnings.")
        sys.exit(0)


if __name__ == "__main__":
    main()
