#!/usr/bin/env python3
"""
Strategy Auditor Tool
Enforces clarity and correctness in strategies.
"""
import ast
import argparse
import sys
import tokenize
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

HEADER_TEMPLATE = """
    # Strategy Audit Header
    # ---------------------
    # Strategy Name: {strategy_name}
    # Author: [Author Name]
    # Version: 1.0
    # Supported Timeframes: [e.g., 5m, 1h]
    #
    # Pair Format Notes:
    # - Delta Contract: e.g., BTCUSDT
    # - Freqtrade Pair: e.g., BTC/USDT:USDT
    #
    # Timezone Rule:
    # - All timestamps logged as UTC ISO-8601
    #
    # Entry/Exit Definitions:
    # - Long Entry: [Describe logic]
    # - Long Exit: [Describe logic]
    # - Short Entry: [Describe logic]
    # - Short Exit: [Describe logic]
    #
    # Repainting Note:
    # - Only act on closed candles (no incomplete candle usage)
    # ---------------------
"""

REQUIRED_HEADER_FIELDS = [
    "Strategy Name:",
    "Author:",
    "Version:",
    "Supported Timeframes:",
    "Pair Format Notes:",
    "Timezone Rule:",
    "Entry/Exit Definitions:",
    "Repainting Note:"
]

class StrategyVisitor(ast.NodeVisitor):
    def __init__(self, comments: List[int]):
        self.errors = []
        self.has_header = False
        self.class_node = None
        self.strategy_name = "Unknown"
        self.comments = comments

    def visit_ClassDef(self, node):
        self.class_node = node
        self.strategy_name = node.name

        # Check docstring for header
        docstring = ast.get_docstring(node)
        if docstring:
            if all(field in docstring for field in REQUIRED_HEADER_FIELDS):
                self.has_header = True
            else:
                if "Strategy Audit Header" in docstring:
                     pass

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in ['populate_entry_trend', 'populate_exit_trend']:
            self._check_trend_function(node)
            self._check_comments(node)

    def _check_comments(self, node):
        # We need to see if there is at least one comment inside the function body
        start_line = node.lineno
        end_line = getattr(node, 'end_lineno', start_line)

        has_comment = any(
            start_line <= c_line <= end_line
            for c_line in self.comments
        )

        if not has_comment:
            self.errors.append(f"ERROR: {node.name} at line {start_line} must include comments explaining the market thesis.")

    def _check_trend_function(self, node):
        # We expect assignments to .loc with named variables as conditions
        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Subscript):
                        if isinstance(target.value, ast.Attribute) and target.value.attr == 'loc':
                            condition_node = None
                            if isinstance(target.slice, ast.Tuple): # python 3.9+
                                if len(target.slice.elts) > 0:
                                    condition_node = target.slice.elts[0]
                            elif isinstance(target.slice, ast.Index): # python < 3.9
                                if isinstance(target.slice.value, ast.Tuple):
                                    condition_node = target.slice.value.elts[0]
                                else:
                                    condition_node = target.slice.value
                            elif sys.version_info >= (3, 9):
                                condition_node = target.slice

                            if condition_node:
                                self._validate_condition(condition_node, node.name, child.lineno)

    def _validate_condition(self, node, func_name, lineno):
        def is_complex(n):
            if isinstance(n, ast.Compare):
                return True
            if isinstance(n, ast.Call):
                return True
            if isinstance(n, ast.BinOp):
                return is_complex(n.left) or is_complex(n.right)
            if isinstance(n, ast.BoolOp):
                return any(is_complex(val) for val in n.values)
            if isinstance(n, ast.UnaryOp):
                return is_complex(n.operand)
            return False

        if is_complex(node):
            self.errors.append(f"ERROR: Complex condition in {func_name} at line {lineno}. Use named boolean variables.")

def get_comments(source_code: str) -> List[int]:
    comments = []
    try:
        tokens = tokenize.tokenize(BytesIO(source_code.encode('utf-8')).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comments.append(token.start[0]) # Line number
    except tokenize.TokenError:
        pass
    return comments

def audit_file(filepath: Path, fix: bool) -> List[str]:
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()

    comments = get_comments(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"Syntax Error in {filepath}: {e}"]

    visitor = StrategyVisitor(comments)
    visitor.visit(tree)

    errors = visitor.errors

    if not visitor.has_header:
        msg = f"Missing Audit Header in {filepath}"
        if fix and visitor.class_node:
            lines = source.splitlines()
            class_lineno = visitor.class_node.lineno - 1

            body = visitor.class_node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, (ast.Str, ast.Constant)):
                errors.append(msg + " (Docstring exists but is missing required fields. Please update manually or delete it to auto-fix.)")
            else:
                indent = "    "
                header = '    """' + HEADER_TEMPLATE.format(strategy_name=visitor.strategy_name) + '    """'
                lines.insert(class_lineno + 1, header)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("\n".join(lines))

                print(f"FIXED: Added header to {filepath}")
        else:
            errors.append(msg)

    return errors

def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    strategies_dir = Path("user_data/strategies")
    files = list(strategies_dir.glob("*.py"))

    total_errors = 0

    for f in files:
        if f.name.startswith("__") or f.name.startswith("_base"):
            continue

        print(f"Auditing {f}...")
        errors = audit_file(f, args.fix)
        if errors:
            for e in errors:
                print(f"  {e}")
            total_errors += len(errors)
        else:
            print("  OK")

    if total_errors > 0:
        sys.exit(1)
    else:
        print("Audit passed.")

if __name__ == "__main__":
    main()
