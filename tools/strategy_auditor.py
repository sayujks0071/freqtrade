#!/usr/bin/env python3
import argparse
import ast
import sys
from pathlib import Path


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

HEADER_TEMPLATE = '''"""
Strategy Name: {name}
Author: <Author>
Version: 1.0
Supported Timeframes: <Timeframes>
Supported Pair Format: Delta Futures (e.g. BTC/USDT:USDT)
Timezone: UTC (all timestamps in ISO-8601)

Entry Conditions:
  - Long: <Describe long entry conditions>
  - Short: <Describe short entry conditions>

Exit Conditions:
  - Long: <Describe long exit conditions>
  - Short: <Describe short exit conditions>

No Repainting: This strategy strictly acts on closed candles.
"""
'''


class StrategyAuditor(ast.NodeVisitor):
    def __init__(self, filepath, fix=False):
        self.filepath = filepath
        self.fix = fix
        self.errors = []
        self.has_header = False
        self.source_lines = []
        self.tree = None
        self.modified_source = None

    def audit(self):
        with Path(self.filepath).open("r", encoding="utf-8") as f:
            source = f.read()
            self.source_lines = source.splitlines(keepends=True)

        try:
            self.tree = ast.parse(source)
        except SyntaxError as e:
            self.errors.append(f"Syntax Error: {e}")
            return False

        # Check Header
        docstring = ast.get_docstring(self.tree)
        if docstring:
            self.check_header_content(docstring)
            self.has_header = True
        else:
            self.errors.append("Missing Strategy Header Docstring")
            if self.fix:
                self.insert_header()

        # Visit nodes
        self.visit(self.tree)

        return len(self.errors) == 0

    def check_header_content(self, docstring):
        missing = []
        for field in REQUIRED_HEADER_FIELDS:
            if field not in docstring:
                missing.append(field)

        if missing:
            self.errors.append(f"Header missing fields: {', '.join(missing)}")

    def insert_header(self):
        # Infer strategy name from filename
        name = Path(self.filepath).stem
        header = HEADER_TEMPLATE.format(name=name)

        # Check for shebang
        if self.source_lines and self.source_lines[0].startswith("#!"):
            # Insert after shebang
            self.modified_source = self.source_lines[0] + header + "".join(self.source_lines[1:])
        else:
            # Insert at the beginning
            self.modified_source = header + "".join(self.source_lines)

        with Path(self.filepath).open("w", encoding="utf-8") as f:
            f.write(self.modified_source)

        print(f"FIXED: Inserted header into {self.filepath}")

    def visit_FunctionDef(self, node):
        if node.name in ["populate_entry_trend", "populate_exit_trend"]:
            self.check_trend_method(node)
        self.generic_visit(node)

    def check_trend_method(self, node):
        self._check_comments_in_method(node)
        self._check_boolean_assignments(node)

    def _check_comments_in_method(self, node):
        has_comment = False

        start_line = node.lineno
        # approximate end line
        end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10

        # Simple heuristic: Check if there's any '#' in the source lines of the function
        func_source = "".join(self.source_lines[start_line - 1:end_line])
        if "#" in func_source:
            has_comment = True

        if not has_comment:
            # Check for docstring in function
            if ast.get_docstring(node):
                has_comment = True

        if not has_comment:
            self.errors.append(f"Method {node.name} missing comments explaining logic")

    def _check_boolean_assignments(self, node):
        # Check for named booleans
        # We look for dataframe.loc[CONDITION, ...] = ...
        # If CONDITION is a BoolOp (and/or) with multiple values, it's complex.
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Subscript):
                        # check if it is dataframe.loc
                        if self.is_dataframe_loc(target):
                            # The slice index
                            slice_node = target.slice
                            # In Python < 3.9, slice is ast.Index wrapping the expr
                            if isinstance(slice_node, ast.Index):
                                slice_node = slice_node.value

                            # If tuple (row, col), check row
                            if isinstance(slice_node, ast.Tuple):
                                condition = slice_node.elts[0]
                            else:
                                condition = slice_node

                            if self.is_complex_condition(condition):
                                self.errors.append(
                                    f"Method {node.name} uses complex inline boolean condition "
                                    f"at line {child.lineno}. Use named boolean variables."
                                )

    def is_dataframe_loc(self, node):
        # We expect node to be ast.Subscript
        # node.value should be Attribute (df.loc)
        # or Name (df) if users do df[mask] = ...
        # But Freqtrade standard is df.loc[...]
        if isinstance(node.value, ast.Attribute):
            if node.value.attr == "loc":
                return True
        return False

    def is_complex_condition(self, node):
        # Complex if it is a BoolOp (And/Or) or BinOp (&/|)
        # And if it's not just a single variable name.
        # We want to enforce `long_cond = (a > b) & (c < d); df.loc[long_cond, ...]`
        # So if the condition in .loc[...] is a BinOp with & or |, it's likely complex inline.

        if isinstance(node, ast.BinOp):
            if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
                return True
        if isinstance(node, ast.BoolOp):
            return True

        return False


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
    if target.is_dir():
        files = list(target.rglob("*.py"))
    else:
        files = [target]

    failed = False
    for file in files:
        # Skip __init__.py and mixins
        if file.name.startswith("__") or "Mixin" in file.name:
            continue

        print(f"Auditing {file}...")
        auditor = StrategyAuditor(str(file), fix=args.fix)
        if not auditor.audit():
            failed = True
            print("  FAIL:")
            for err in auditor.errors:
                print(f"    - {err}")
        else:
            print("  PASS")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
