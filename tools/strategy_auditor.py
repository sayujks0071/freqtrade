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


class StrategyAuditor:
    REQUIRED_HEADER_FIELDS = [
        "Strategy Name",
        "Author",
        "Version",
        "Supported Timeframes",
        "Supported Pair Format Notes",
        "Timezone Rule",
        "Entry Definitions",
        "Exit Definitions",
        "No Repainting Note",
    ]

    TEMPLATE_HEADER = '''"""
Strategy Name: {name}
Author: {author}
Version: {version}
Supported Timeframes: {timeframes}

Supported Pair Format Notes:
    - Delta contract symbols (e.g. BTCUSDT)
    - Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT)

Timezone Rule:
    - All timestamps logged as UTC ISO-8601

Entry Definitions:
    - Long entry: (Add logic here)
    - Short entry: (Add logic here)

Exit Definitions:
    - Long exit: (Add logic here)
    - Short exit: (Add logic here)

No Repainting Note:
    - Only act on closed candles (no incomplete candle usage)
"""
'''

    def __init__(self, fix: bool = False):
        self.fix = fix

    def is_strategy_file(self, tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if "IStrategy" in bases:
                    return True
        return False

    def audit_file(self, filepath: str) -> bool:  # noqa: C901
        path = Path(filepath)
        try:
            with path.open("r", encoding="utf-8") as f:
                source = f.read()
        except Exception as e:
            logger.error(f"FAIL: Could not read {filepath}: {e}")
            return False

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.error(f"FAIL: Syntax Error in {filepath}: {exc}")
            return False

        # If not a strategy file, skip strategy-specific audits but check generic safety?
        # Requirement: "Parses every strategy ... Enforces ... header ... validates populate..."
        # So we should skip non-strategies.
        if not self.is_strategy_file(tree):
            # Only log if verbose? Or just silently skip?
            # User might pass a directory with utils.
            # logger.info(f"Skipping {filepath} (Not a strategy)")
            return True

        logger.info(f"Auditing {filepath}...")

        errors = []
        fixed_source = source

        # Check 1: Docstring (Header block)
        # Cast to Module to satisfy MyPy (ast.parse returns AST but specifically Module)
        if isinstance(tree, ast.Module):
            docstring_errors, new_source = self.check_docstring(tree, source, filepath)
        else:
            docstring_errors, new_source = [], None

        if docstring_errors:
            errors.extend(docstring_errors)
            if self.fix and new_source:
                fixed_source = new_source
                # Re-parse tree for subsequent checks if source changed
                try:
                    tree = ast.parse(fixed_source)
                except SyntaxError:
                    pass

        # Check 2: Unsafe Imports
        errors.extend(self.check_unsafe_imports(tree))

        # Check 3: datetime.now() usage
        errors.extend(self.check_datetime_now(tree))

        # Check 4: Enforce AuditedStrategyMixin
        errors.extend(self.check_mixin_inheritance(tree, filepath))

        # Check 5: "closed candle only" note
        if "closed candle" not in fixed_source.lower():
            if not self.fix:
                errors.append(
                    "Missing 'closed candle' note/comment (Logic must run on closed candles)"
                )

        # Check 6: Entry/Exit Logic (named variables and comments)
        errors.extend(self.check_entry_exit_logic(tree, source))

        if errors:
            for e in errors:
                logger.error(f"  - {e}")

            if self.fix and fixed_source != source:
                try:
                    with path.open("w", encoding="utf-8") as f:
                        f.write(fixed_source)
                    logger.info(f"  FIXED: Updated header in {filepath}")
                    # If we fixed, return True?
                    # Only if errors were only docstring errors.
                    # But checking that is complex. Return False to prompt re-check.
                except Exception as e:
                    logger.error(f"  FAIL: Could not write fix to {filepath}: {e}")

            return False

        logger.info("PASS")
        return True

    def check_docstring(
        self, tree: ast.AST, source: str, filepath: str
    ) -> tuple[list[str], str | None]:
        errors = []
        docstring = ast.get_docstring(tree)

        missing_fields = []
        if not docstring:
            missing_fields = self.REQUIRED_HEADER_FIELDS
            errors.append("Missing module docstring (Header block)")
        else:
            for field in self.REQUIRED_HEADER_FIELDS:
                if f"{field}:" not in docstring and f"{field}" not in docstring:
                    missing_fields.append(field)

            if missing_fields:
                errors.append(f"Missing header fields: {', '.join(missing_fields)}")

        new_source = None
        if (not docstring) and self.fix:
            name = Path(filepath).stem
            header = self.TEMPLATE_HEADER.format(
                name=name,
                author="Unknown",
                version="1.0",
                timeframes="1h (Check strategy)",
            )
            new_source = header + "\n" + source

        return errors, new_source

    def check_unsafe_imports(self, tree: ast.AST) -> list[str]:
        errors = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name in ["requests", "urllib", "socket", "http"]:
                        errors.append(f"Unsafe import: {n.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import from: {node.module}")
        return errors

    def check_datetime_now(self, tree: ast.AST) -> list[str]:
        errors = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "now":
                        if not node.args and not node.keywords:
                            errors.append(
                                f"Potential naive datetime.now() usage at line {node.lineno}"
                            )
        return errors

    def check_mixin_inheritance(self, tree: ast.AST, filepath: str) -> list[str]:
        errors = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
                    errors.append(f"Class {node.name} must inherit AuditedStrategyMixin")
        return errors

    def check_entry_exit_logic(self, tree: ast.AST, source: str) -> list[str]:  # noqa: C901
        errors = []
        target_methods = ["populate_entry_trend", "populate_exit_trend"]
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in target_methods:
                # 1. Check for comments explaining thesis
                has_comment = False
                if ast.get_docstring(node):
                    has_comment = True
                else:
                    start = node.lineno - 1
                    end = (
                        node.end_lineno if getattr(node, "end_lineno", None) else len(source_lines)
                    )
                    for i in range(start, min(end, len(source_lines))):
                        if "#" in source_lines[i]:
                            has_comment = True
                            break

                if not has_comment:
                    errors.append(f"Method {node.name} missing comments explaining market thesis")

                # 2. Check for named variables (no inline comparisons in .loc)
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Subscript):
                                sl = target.slice
                                if isinstance(sl, ast.Index):
                                    sl = sl.value

                                if self._has_inline_comparison(sl):
                                    errors.append(
                                        f"Inline comparison condition in {node.name} at line "
                                        f"{stmt.lineno}. Use named boolean variables for "
                                        "sub-conditions."
                                    )
        return errors

    def _has_inline_comparison(self, node: ast.AST) -> bool:
        """
        Returns True if the node contains comparison logic (>, <, ==, etc).
        """
        for child in ast.walk(node):
            if isinstance(child, ast.Compare):
                return True
        return False


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor for Freqtrade")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")

    args = parser.parse_args()

    auditor = StrategyAuditor(fix=args.fix)
    failed = False

    target = Path(args.path)
    if target.is_file():
        if not auditor.audit_file(str(target)):
            failed = True
    elif target.is_dir():
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if not auditor.audit_file(str(Path(root) / file)):
                        failed = True
    else:
        logger.error(f"Error: {target} is not a valid file or directory")
        sys.exit(1)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
