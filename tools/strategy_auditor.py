#!/usr/bin/env python3
import argparse
import ast
import sys


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.has_mixin = False
        self.required_methods = {
            "populate_indicators",
            "populate_entry_trend",
            "populate_exit_trend",
        }
        self.found_methods = set()
        self.forbidden_calls = {"print", "datetime.now", "requests", "urllib", "socket"}

    def visit_ClassDef(self, node):
        # Check inheritance
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "AuditedStrategyMixin":
                self.has_mixin = True
            elif isinstance(base, ast.Attribute) and base.attr == "AuditedStrategyMixin":
                self.has_mixin = True

        # Check methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name in self.required_methods:
                    self.found_methods.add(item.name)

        self.generic_visit(node)

    def visit_Call(self, node):
        # Check forbidden calls
        if isinstance(node.func, ast.Name):
            if node.func.id in self.forbidden_calls:
                self.errors.append(f"Forbidden call: {node.func.id} at line {node.lineno}")
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if name in self.forbidden_calls:
                self.errors.append(f"Forbidden call: {name} at line {node.lineno}")
            # Check for datetime.now() specifically
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
                and name == "now"
            ):
                self.errors.append(
                    f"Forbidden call: datetime.now() at line {node.lineno}. Use datetime.now(timezone.utc)."
                )

        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in ["requests", "urllib", "socket"]:
                self.errors.append(f"Forbidden import: {alias.name} at line {node.lineno}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in ["requests", "urllib", "socket"]:
            self.errors.append(f"Forbidden import from: {node.module} at line {node.lineno}")
        self.generic_visit(node)


def audit_file(filepath):
    print(f"Auditing {filepath}...")
    try:
        with open(filepath, "r") as source:
            tree = ast.parse(source.read())
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return False

    visitor = StrategyVisitor()
    visitor.visit(tree)

    passed = True

    # Check Mixin
    # Only enforce if it's a strategy class (heuristic: name ends with Strategy or is in strategies folder)
    # But usually all files in strategies folder are strategies.
    if not visitor.has_mixin:
        print(f"FAIL: {filepath} does not inherit from AuditedStrategyMixin")
        passed = False

    # Check Methods
    missing = visitor.required_methods - visitor.found_methods
    if missing:
        print(f"FAIL: {filepath} missing methods: {missing}")
        passed = False

    # Check Forbidden
    if visitor.errors:
        for err in visitor.errors:
            print(f"FAIL: {err}")
        passed = False

    if passed:
        print(f"PASS: {filepath}")

    return passed


def main():
    parser = argparse.ArgumentParser(description="Audit Freqtrade Strategies")
    parser.add_argument("files", nargs="+", help="Strategy files to audit")
    args = parser.parse_args()

    exit_code = 0
    for f in args.files:
        if not audit_file(f):
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
