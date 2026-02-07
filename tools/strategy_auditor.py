#!/usr/bin/env python3
import argparse
import ast
import sys
from pathlib import Path


HEADER_TEMPLATE = """
Strategy: {strategy_name}
Author: {author}
Version: {version}
Timeframe: {timeframe}
Pair Format: Delta Futures (e.g. BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry/Exit: {entry_exit_rules}
Repainting: No repainting (process_only_new_candles=True)
"""

REQUIRED_HEADERS = [
    "Strategy",
    "Author",
    "Version",
    "Timeframe",
    "Pair Format",
    "Timezone",
    "Entry/Exit",
    "Repainting",
]


class AuditVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.errors = []
        self.has_mixin = False
        self.has_process_new_candles = False
        self.in_trend_function = False

    def visit_ClassDef(self, node):
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "AuditedStrategyMixin" in bases:
            self.has_mixin = True

        # Check class body for process_only_new_candles
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                        if isinstance(item.value, ast.Constant) and item.value.value is True:
                            self.has_process_new_candles = True

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in ["populate_entry_trend", "populate_exit_trend"]:
            self.in_trend_function = True
            self.check_trend_function(node)
            # Continue generic visit to check nested nodes if needed,
            # but we manually checked body so maybe not needed?
            # Actually generic_visit is safe.
            self.generic_visit(node)
            self.in_trend_function = False
        else:
            self.generic_visit(node)

    def check_trend_function(self, node):
        # iterate statements to check assignments
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    # Check if target is dataframe.loc[...]
                    if isinstance(target, ast.Subscript):
                        # It is likely a df assignment
                        # Verify if the condition (slice) contains raw comparisons
                        sl = target.slice
                        # In Python 3.9+, slice is just the node.
                        # In older, it might be Index.
                        if isinstance(sl, ast.Index):
                            sl = sl.value

                        if self.contains_compare(sl):
                            self.errors.append(
                                f"Line {stmt.lineno}: Complex logic inside .loc[]. "
                                "Use named boolean variables for conditions (no raw comparisons)."
                            )

    def contains_compare(self, node):
        """
        Returns True if the node contains a Compare node (e.g. a > b).
        This enforces extracting logic to variables.
        """
        for child in ast.walk(node):
            if isinstance(child, ast.Compare):
                return True
        return False


def check_comments_in_trend_funcs(source_lines):
    # Heuristic: Find def populate_... and ensure there are comments inside
    errors = []
    in_func = False
    func_name = ""
    comment_found = False

    for i, line in enumerate(source_lines):
        stripped = line.strip()
        if stripped.startswith("def populate_entry_trend") or stripped.startswith(
            "def populate_exit_trend"
        ):
            in_func = True
            func_name = stripped.split("(")[0].replace("def ", "")
            comment_found = False
            continue

        if in_func:
            if stripped.startswith("def ") or (stripped.startswith("class ") and line[0] != " "):
                # End of function (heuristic based on indentation or next def)
                if not comment_found:
                    errors.append(f"Missing comments in {func_name} explaining market thesis.")
                in_func = False
                continue

            if "#" in stripped:
                comment_found = True

    # Check last function
    if in_func and not comment_found:
        errors.append(f"Missing comments in {func_name} explaining market thesis.")

    return errors


def audit_file(filepath, fix=False):  # noqa: C901
    print(f"Auditing {filepath}...")
    path = Path(filepath)
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e_read:
        print(f"Error reading {filepath}: {e_read}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as e_syntax:
        print(f"Syntax Error in {filepath}: {e_syntax}")
        return False

    errors = []

    # 1. Header Check
    docstring = ast.get_docstring(tree)
    if not docstring:
        if fix:
            print(f"Fixing header for {filepath}...")
            strategy_name = path.stem
            new_header = HEADER_TEMPLATE.format(
                strategy_name=strategy_name,
                author="Unknown",
                version="1.0",
                timeframe="1h",
                entry_exit_rules="Define me",
            )
            source = f'"""{new_header}"""\n\n' + source
            path.write_text(source, encoding="utf-8")
            # Re-read and re-parse
            return audit_file(filepath, fix=False)
        else:
            errors.append("Missing module docstring (Header block). Use --fix to auto-insert.")
    else:
        # Validate content
        for req in REQUIRED_HEADERS:
            if f"{req}:" not in docstring:
                errors.append(f"Header missing required field: '{req}'")

    # 2. Logic & Mixin Check
    visitor = AuditVisitor(filepath)
    visitor.visit(tree)
    errors.extend(visitor.errors)

    # Check for AuditedStrategyMixin inheritance
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases:
                if "AuditedStrategyMixin" not in bases:
                    errors.append(f"Class {node.name} must inherit AuditedStrategyMixin.")

                # Check process_only_new_candles for the strategy class
                if not visitor.has_process_new_candles:
                    errors.append(
                        "Missing 'process_only_new_candles = True'. "
                        "Logic must run on closed candles."
                    )

    if not has_class:
        # Likely not a strategy file
        pass

    # 3. Comment Check
    source_lines = source.splitlines()
    comment_errors = check_comments_in_trend_funcs(source_lines)
    errors.extend(comment_errors)

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False

    print("  PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Path {target} does not exist.")
        sys.exit(1)

    failed = False
    if target.is_file():
        if not audit_file(target, args.fix):
            failed = True
    else:
        for file in target.rglob("*.py"):
            if file.name.startswith("__"):
                continue
            if "AuditedStrategyMixin.py" in str(file):
                continue
            if not audit_file(file, args.fix):
                failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
