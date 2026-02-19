#!/usr/bin/env python3
"""
Strategy Auditor
Enforces strict clarity and correctness in strategies.
"""

import argparse
import ast
import sys
from pathlib import Path


REQUIRED_HEADER_FIELDS = [
    "Strategy Name",
    "Author",
    "Version",
    "Timeframes",
    "Supported Pair Format",
    "Timezone Rule",
    "Entry/Exit Definitions",
    "No Repainting",
]

DEFAULT_HEADER = """
    Strategy Name: {name}
    Author: Unknown
    Version: 1.0
    Timeframes: {timeframe}
    Supported Pair Format: Delta contract symbols (e.g., BTCUSDT) vs Freqtrade/CCXT
    futures pair format (base/quote:settle like BTC/USDT:USDT)
    Timezone Rule: all timestamps logged as UTC ISO-8601
    Entry/Exit Definitions:
      - Long entry conditions: Explain here
      - Long exit conditions: Explain here
      - Short entry conditions: Explain here (if enabled)
      - Short exit conditions: Explain here
    No Repainting: only act on closed candles (no incomplete candle usage)
"""


class StrategyAuditor(ast.NodeVisitor):
    def __init__(self, filepath, fix=False):
        self.filepath = filepath
        self.fix = fix
        self.errors = []
        self.source = ""
        self.source_lines = []
        self.tree = None
        self.has_changes = False

    def audit(self):
        print(f"Auditing {self.filepath}...")
        try:
            with Path(self.filepath).open("r", encoding="utf-8") as f:
                self.source = f.read()
            self.source_lines = self.source.splitlines()
            self.tree = ast.parse(self.source)
        except SyntaxError as exc:
            self.errors.append(f"Syntax Error: {exc}")
            return False
        except Exception as exc:
            self.errors.append(f"Error reading file: {exc}")
            return False

        self.visit(self.tree)
        self.check_header()
        self.check_complex_conditions()

        if self.fix and self.has_changes:
            with Path(self.filepath).open("w", encoding="utf-8") as f:
                f.write(self.source)
            print(f"FIXED: {self.filepath}")
            # Re-audit to verify
            self.errors = []
            self.audit()

        if self.errors:
            for e in self.errors:
                print(f"  FAIL: {e}")
            return False

        print("PASS")
        return True

    def check_header(self):
        docstring = ast.get_docstring(self.tree)
        if not docstring:
            if self.fix:
                self.insert_header()
            else:
                self.errors.append("Missing module docstring (Header block)")
            return

        missing_fields = []
        for field in REQUIRED_HEADER_FIELDS:
            if field + ":" not in docstring:
                missing_fields.append(field)

        if missing_fields:
            if self.fix:
                # If existing docstring, we don't auto-fix partial headers as it's complex
                self.errors.append(f"Missing header fields: {', '.join(missing_fields)}")
            else:
                self.errors.append(f"Missing header fields: {', '.join(missing_fields)}")

    def insert_header(self):
        # Infer strategy name and timeframe from class def
        class_name = "UnknownStrategy"
        timeframe = "1h"  # default

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                for body_item in node.body:
                    if isinstance(body_item, ast.Assign):
                        for target in body_item.targets:
                            if isinstance(target, ast.Name) and target.id == "timeframe":
                                if isinstance(body_item.value, ast.Constant):
                                    timeframe = body_item.value.value
                                # Python < 3.8
                                elif isinstance(body_item.value, ast.Str):
                                    timeframe = body_item.value.s

        header = '"""' + DEFAULT_HEADER.format(name=class_name, timeframe=timeframe) + '"""\n'

        # Handle shebang/encoding
        lines = self.source.splitlines(keepends=True)
        insert_idx = 0
        while insert_idx < len(lines):
            line = lines[insert_idx]
            if line.startswith("#!") or line.startswith("# -*-"):
                insert_idx += 1
            else:
                break

        lines.insert(insert_idx, header)
        self.source = "".join(lines)
        self.has_changes = True

    def visit_ClassDef(self, node):
        # Check for process_only_new_candles = True
        has_process_new = False
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                        if isinstance(item.value, ast.Constant) and item.value.value is True:
                            has_process_new = True
                        # Python < 3.8
                        elif isinstance(item.value, ast.NameConstant) and item.value.value is True:
                            has_process_new = True

        if not has_process_new:
            self.errors.append(f"Class {node.name} missing 'process_only_new_candles = True'")

        self.generic_visit(node)

    def check_complex_conditions(self):
        # Validate populate_entry_trend and populate_exit_trend
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name in [
                "populate_entry_trend",
                "populate_exit_trend",
            ]:
                self.check_function_conditions(node)
                self.check_function_comments(node)

    def is_clean_boolean_expression(self, node):
        """
        Recursively checks if a boolean expression is composed only of Names (variables)
        and basic boolean operators (And, Or, Not, BitAnd, BitOr, Invert),
        without inline comparisons or function calls.
        """
        if isinstance(node, ast.Name):
            return True
        elif isinstance(node, ast.UnaryOp):
            return self.is_clean_boolean_expression(node.operand)
        elif isinstance(node, ast.BinOp):
            # Allow BitAnd (&), BitOr (|)
            if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
                return self.is_clean_boolean_expression(
                    node.left
                ) and self.is_clean_boolean_expression(node.right)
            # Other BinOps like Add/Sub imply math, not boolean logic usually
            return False
        elif isinstance(node, ast.BoolOp):
            # Allow And, Or
            return all(self.is_clean_boolean_expression(v) for v in node.values)
        else:
            # Everything else (Compare, Call, Constant, Attribute, Subscript, etc.)
            # is disallowed inline
            return False

    def check_function_conditions(self, func_node):
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                # Check if assigning to dataframe loc/iloc
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        # Check if index is complex bool op
                        slice_node = target.slice
                        # Handle python < 3.9
                        if isinstance(slice_node, ast.Index):
                            slice_node = slice_node.value

                        nodes_to_check = []
                        if isinstance(slice_node, (ast.Tuple, ast.List)):
                            nodes_to_check.extend(slice_node.elts)
                        else:
                            nodes_to_check.append(slice_node)

                        for sub_node in nodes_to_check:
                            if isinstance(
                                sub_node, (ast.BinOp, ast.BoolOp, ast.Compare, ast.UnaryOp)
                            ):
                                if not self.is_clean_boolean_expression(sub_node):
                                    self.errors.append(
                                        f"Complex inline condition in {func_node.name} at "
                                        f"line {node.lineno}. Use named boolean variables."
                                    )

    def check_function_comments(self, func_node):
        # Heuristic: Check if the function body lines contain '#'
        if not hasattr(func_node, "lineno") or not hasattr(func_node, "end_lineno"):
            return  # Cannot check without line numbers

        start_line = func_node.lineno - 1
        end_line = func_node.end_lineno

        body_lines = self.source_lines[start_line:end_line]
        has_comment = False
        for line in body_lines:
            if "#" in line:
                has_comment = True
                break

        if not has_comment:
            self.errors.append(
                f"Method {func_node.name} missing comments explaining market thesis "
                f"(line {func_node.lineno})"
            )


def main():
    parser = argparse.ArgumentParser(description="Audit strategies for Delta Freqtrade stack.")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    target = Path(args.path)
    failed = False

    if target.is_file():
        auditor = StrategyAuditor(str(target), fix=args.fix)
        if not auditor.audit():
            failed = True
    else:
        for f in target.rglob("*.py"):
            if f.name.startswith("__"):
                continue
            auditor = StrategyAuditor(str(f), fix=args.fix)
            if not auditor.audit():
                failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
