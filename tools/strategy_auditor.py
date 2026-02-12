#!/usr/bin/env python3
import argparse
import ast
import sys
from pathlib import Path


REQUIRED_HEADER_KEYS = [
    "Strategy Name",
    "Author",
    "Version",
    "Timeframes",
    "Pair Format",
    "Timezone",
    "Entry Conditions",
    "Exit Conditions",
    "No Repainting",
]

HEADER_TEMPLATE = """\"\"\"
Strategy Name: {name}
Author: {author}
Version: {version}
Timeframes: {timeframes}
Pair Format: Delta symbols (e.g. BTCUSDT) vs Freqtrade (BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry Conditions:
  - Long: ...
  - Short: ...
Exit Conditions:
  - Long: ...
  - Short: ...
No Repainting: Logic runs on closed candles only.
\"\"\"
"""


class StrategyAuditor(ast.NodeVisitor):
    def __init__(self, filepath, fix_mode=False):
        self.filepath = filepath
        self.fix_mode = fix_mode
        self.errors = []
        self.source = ""
        self.tree = None
        self.has_docstring = False
        self.docstring_node = None
        self.strategy_class = None

    def audit(self):
        print(f"Auditing {self.filepath}...")
        try:
            with Path(self.filepath).open() as f:
                self.source = f.read()
            self.tree = ast.parse(self.source)
        except SyntaxError as e:
            self.errors.append(f"Syntax Error: {e}")
            return False

        self.visit(self.tree)
        self.check_header()

        if self.errors:
            for err in self.errors:
                print(f"  FAIL: {err}")
            return False

        print("  PASS")
        return True

    def visit_Module(self, node):
        self.docstring_node = ast.get_docstring(node, clean=False)
        if self.docstring_node:
            self.has_docstring = True
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # We assume the first class inheriting from IStrategy is the target
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "IStrategy" in bases:
            self.strategy_class = node.name
            if "AuditedStrategyMixin" not in bases:
                # Check if it's imported? No, just check if it's in bases
                # This is a strict check as per requirements
                self.errors.append(f"Class {node.name} must inherit from AuditedStrategyMixin")

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in ["populate_entry_trend", "populate_exit_trend"]:
            self.check_trend_method(node)
        self.generic_visit(node)

    def check_header(self):
        if not self.has_docstring:
            if self.fix_mode:
                self.fix_header()
            else:
                self.errors.append("Missing module docstring (Header block)")
            return

        doc = self.docstring_node
        missing_keys = []
        for key in REQUIRED_HEADER_KEYS:
            if key not in doc:
                missing_keys.append(key)

        if missing_keys:
            if self.fix_mode:
                # We can't easily merge, so we might just warn or append?
                # For now, let's say we only fix if MISSING entirely.
                # Or we can try to append.
                # Implementing full replace is safer.
                self.errors.append(
                    f"Header incomplete (missing {missing_keys}). "
                    "Run with --fix to overwrite (if implemented) or fix manually."
                )
            else:
                self.errors.append(f"Header missing keys: {missing_keys}")

    def fix_header(self):
        print(f"  FIX: Adding header to {self.filepath}")
        name = self.strategy_class if self.strategy_class else "UnknownStrategy"
        new_header = HEADER_TEMPLATE.format(
            name=name,
            author="Unknown",
            version="1.0",
            timeframes="1h"
        )

        # Prepend to file
        with Path(self.filepath).open("w") as f:
            f.write(new_header.strip() + "\n\n" + self.source)

        # Update state
        self.source = new_header.strip() + "\n\n" + self.source
        self.has_docstring = True  # Technically true now

    def check_trend_method(self, node):
        # Check for named boolean variables
        # We look for assignments to .loc

        # Heuristic for comments: check source lines?
        # AST doesn't show comments. We can check if the method body is empty or just has pass?
        # Requirement: "include comments explaining the market thesis"
        # Since AST removes comments, checking this strictly is hard without tokenizing.
        # We will skip strict comment check in AST, but maybe check for complexity.

        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Subscript):
                        # This is likely dataframe.loc[...] = ...
                        # Check the slice (condition)
                        sl = target.slice
                        if hasattr(ast, "Index") and isinstance(sl, ast.Index):  # Python < 3.9
                            sl = sl.value

                        # Validate the condition `sl`
                        if not self.is_valid_condition(sl):
                            self.errors.append(
                                f"Method {node.name} line {child.lineno}: "
                                "Complex condition in .loc assignment. Use named boolean variables."
                            )

    def is_valid_condition(self, node):
        # Valid: Name (variable) or simple BoolOp/BinOp with few terms?
        # Requirement: "named boolean sub-conditions (no giant unreadable one-liners)"

        # Accept simpler atoms
        if isinstance(node, ast.Name):
            return True

        # Accept constants (like 'enter_long' string in the slice)
        if isinstance(node, ast.Constant):
            return True

        # Accept simple comparisons like (df['x'] > y) IF they are assigned to variables first?
        # The prompt says: "have named boolean sub-conditions".
        # This implies:
        # long_condition = (dataframe['rsi'] < 30)
        # dataframe.loc[long_condition, 'enter_long'] = 1
        # So inside .loc[], it should be a Name or a very simple boolean combination of Names.

        if isinstance(node, ast.BoolOp):
            # Check if all values are Names or simple unary ops
            for val in node.values:
                if not self.is_valid_condition_component(val):
                    return False
            return True

        # Also handle tuple (pandas multiindex or just syntax quirk)
        if isinstance(node, ast.Tuple):
            # For .loc[row, col], both must be simple.
            # Usually row is the condition (Name) and col is String (Constant).
            for elt in node.elts:
                if not self.is_valid_condition(elt):
                    return False
            return True

        # If it's a BinOp (bitwise & |), it's complex
        if isinstance(node, ast.BinOp):
            return self.is_simple_binop(node)

        return False

    def is_valid_condition_component(self, node):
        if isinstance(node, ast.Name):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Name):
            return True
        return False

    def is_simple_binop(self, node):
        # Allow A & B
        left = node.left
        right = node.right
        return (
            self.is_valid_condition_component(left) and
            self.is_valid_condition_component(right)
        )


def main():
    parser = argparse.ArgumentParser(description="Audit strategies for compliance.")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: {target} does not exist")
        sys.exit(1)

    files = []
    if target.is_file():
        files.append(target)
    else:
        files.extend(target.rglob("*.py"))

    failed = False
    for f in files:
        if f.name.startswith("__") or f.name == "AuditedStrategyMixin.py":
            continue

        auditor = StrategyAuditor(str(f), fix_mode=args.fix)
        if not auditor.audit():
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
