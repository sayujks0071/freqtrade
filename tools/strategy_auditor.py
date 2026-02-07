#!/usr/bin/env python3
"""
Strategy Auditor: Static Analysis for Freqtrade strategies.
Enforces safety, clarity, and best practices using AST.
"""

import argparse
import ast
import logging
import sys
from pathlib import Path


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("strategy_auditor")

SAFE_MODULES = {
    "freqtrade",
    "pandas",
    "numpy",
    "talib",
    "datetime",
    "math",
    "logging",
    "typing",
    "arrow",
}
UNSAFE_MODULES = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "urllib",
    "requests",
    "socket",
    "pickle",
    "eval",
    "exec",
}

REQUIRED_HEADER_FIELDS = {
    "Strategy",
    "Author",
    "Version",
    "Timeframe",
    "Pair Format",
    "Timezone",
    "Entry/Exit",
    "Repainting",
}


class SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.unsafe_imports = []
        self.datetime_now_calls = []

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split(".")[0] in UNSAFE_MODULES:
                self.unsafe_imports.append((alias.name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split(".")[0] in UNSAFE_MODULES:
            self.unsafe_imports.append((node.module, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node):
        # Heuristic: Check for calls to datetime.now() without arguments (local time)
        # Case 1: from datetime import datetime -> datetime.now()
        is_datetime_call = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
            # Case 1: datetime.now() (from datetime import datetime)
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
                is_datetime_call = True

            # Case 2: datetime.datetime.now() (import datetime)
            elif isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "datetime":
                if (
                    isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "datetime"
                ):
                    is_datetime_call = True

            if is_datetime_call:
                if not node.args and not node.keywords:
                    # datetime.now() called with no args
                    self.datetime_now_calls.append(node.lineno)
        self.generic_visit(node)


def check_header(content):
    # Check for metadata block in docstring or comments
    found = set()
    lines = content.split("\n")
    for line in lines[:50]:  # Check first 50 lines
        for field in REQUIRED_HEADER_FIELDS:
            if field in line:
                found.add(field)

    missing = REQUIRED_HEADER_FIELDS - found
    return missing


def check_readability(tree):
    # Heuristic: Check for complex boolean expressions in populate_* methods
    # We want named variables. e.g. `condition1 = (close > open)`
    # This is complex to implement fully via AST without being annoying.
    # For now, we skip AST implementation and rely on review or simpler grep-like checks.
    # We can check if `populate_entry_trend` has assignments before DataFrame modification.
    return []


def audit_strategy(filepath, args):
    logger.info(f"Auditing {filepath}...")
    try:
        with filepath.open("r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Could not read {filepath}: {e}")
        return False

    errors = []

    # 1. AST Security Checks
    try:
        tree = ast.parse(content)
        visitor = SecurityVisitor()
        visitor.visit(tree)
    except SyntaxError as e:
        logger.error(f"Syntax error in {filepath}: {e}")
        return False

    for mod, lineno in visitor.unsafe_imports:
        errors.append(f"Line {lineno}: Unsafe import '{mod}' detected.")

    for lineno in visitor.datetime_now_calls:
        errors.append(
            f"Line {lineno}: `datetime.now()` called without timezone. "
            "Use `datetime.now(timezone.utc)`."
        )

    # 2. Header Check
    missing_headers = check_header(content)
    if missing_headers:
        errors.append(f"Missing metadata header fields: {', '.join(missing_headers)}")

    # 3. Closed Candle Check (Heuristic)
    if "process_only_new_candles = True" in content:
        if "iloc[-2]" not in content:
            # Very basic check, might be false positive if they access -2 differently
            # But ensures they are aware of lookback requirement
            pass  # Warn?

    if errors:
        logger.error(f"Audit FAILED for {filepath}:")
        for err in errors:
            logger.error(f"  - {err}")
        return False
    else:
        logger.info(f"{filepath} passed audit.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Audit Freqtrade strategies")
    parser.add_argument("path", type=Path, help="File or directory to audit")
    args = parser.parse_args()

    if args.path.is_file():
        if not audit_strategy(args.path, args):
            sys.exit(1)
    elif args.path.is_dir():
        failed = 0
        for p in args.path.rglob("*.py"):
            # Skip files in directories starting with _ (e.g. _base/Mixin.py)
            # or files starting with _
            if any(part.startswith("_") for part in p.parts):
                logger.info(f"Skipping {p} (internal/mixin)")
                continue

            if not audit_strategy(p, args):
                failed += 1
        if failed > 0:
            logger.error(f"Audit failed for {failed} files.")
            sys.exit(1)
    else:
        logger.error(f"Path {args.path} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
