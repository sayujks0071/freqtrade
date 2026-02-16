#!/usr/bin/env python3
import argparse
import ast
import os
import sys
from pathlib import Path

HEADER_TEMPLATE = '''"""
Strategy Clarity Enforcement:
- Symbols: ...
- Timeframe: ...
- Entry/Exit: ...
- Risk: ...
- Note: Closed candle only
"""
'''


class StrategyAuditor(ast.NodeVisitor):
    def __init__(self, filename, fix=False):
        self.filename = filename
        self.fix = fix
        self.errors = []
        self.has_mixin = False
        self.has_docstring = False
        self.imports = set()
        self.forbidden_calls = ["print", "sleep", "requests", "urllib"]

    def check(self):
        try:
            with Path(self.filename).open() as f:
                content = f.read()

            tree = ast.parse(content)

            # Check Docstring
            if ast.get_docstring(tree):
                self.has_docstring = True

            self.visit(tree)

            if not self.has_mixin:
                # Check if it inherits from IStrategy but NOT AuditedStrategyMixin
                self.errors.append("Class does not inherit AuditedStrategyMixin")

            if not self.has_docstring:
                self.errors.append("Missing module docstring")
                if self.fix:
                    print(f"Fixing missing docstring in {self.filename}")
                    with Path(self.filename).open("w") as f:
                        f.write(HEADER_TEMPLATE + content)
                    # We don't remove error here because re-run is needed to verify

        except Exception as e:
            self.errors.append(f"Parsing Error: {e}")

    def visit_ClassDef(self, node):
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "AuditedStrategyMixin":
                self.has_mixin = True
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
            if alias.name in ["requests", "urllib", "http"]:
                self.errors.append(f"Forbidden import: {alias.name}")

    def visit_ImportFrom(self, node):
        if node.module in ["requests", "urllib", "http"]:
            self.errors.append(f"Forbidden import from: {node.module}")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in self.forbidden_calls:
                self.errors.append(f"Forbidden call: {node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in self.forbidden_calls:
                self.errors.append(f"Forbidden call: {node.func.attr}")
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
                and node.func.attr == "now"
            ):
                if not node.args and not node.keywords:
                    # Check if tz is passed
                    self.errors.append("datetime.now() called without arguments (must be UTC)")

        self.generic_visit(node)


def audit_directory(path, fix=False):
    failed = False
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                filepath = Path(root) / file
                if "_base" in str(filepath):
                    continue

                print(f"Auditing {filepath}...")
                auditor = StrategyAuditor(str(filepath), fix=fix)
                auditor.check()

                if auditor.errors:
                    print(f"FAILED: {filepath}")
                    for err in auditor.errors:
                        print(f"  - {err}")
                    failed = True
                else:
                    print(f"PASSED: {filepath}")
    return failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    if audit_directory(args.directory, fix=args.fix):
        sys.exit(1)
    else:
        sys.exit(0)
