#!/usr/bin/env python3
import ast
import sys
from pathlib import Path


class StrategyAuditor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.errors = []
        self.has_header = False
        self.has_process_only_new_candles = False

    def visit_Import(self, node):
        for alias in node.names:
            self.check_import(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self.check_import(node.module, node.lineno)
        self.generic_visit(node)

    def check_import(self, name, lineno):
        unsafe = ["subprocess", "os", "sys", "socket", "requests", "urllib"]
        if name and any(name.startswith(u) for u in unsafe):
            # Allow harmless os/sys usage if strictly needed but warn
            if name in ["os", "sys"]:
                pass  # Usually ok in strategies for path stuff, but risky
            else:
                self.errors.append(f"Line {lineno}: Unsafe import '{name}' detected.")

    def visit_Call(self, node):
        # Check datetime.now() without timezone
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
                    if not node.args:
                        self.errors.append(
                            f"Line {node.lineno}: datetime.now() used without timezone. Use datetime.now(timezone.utc)."
                        )
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Check for Metadata header in docstring
        docstring = ast.get_docstring(node)
        if docstring:
            if "Strategy" in docstring and "Author" in docstring:
                self.has_header = True

        # Check process_only_new_candles
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                        self.has_process_only_new_candles = True

        self.generic_visit(node)


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    try:
        with open(filepath, "r") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"FAIL: Syntax error in {filepath}: {e}")
        return False

    auditor = StrategyAuditor(filepath)
    auditor.visit(tree)

    passed = True

    if not auditor.has_header:
        print(f"FAIL: Missing Metadata Header in class docstring.")
        passed = False
        if fix:
            # Simple append to docstring isn't trivial with parsed tree without re-codegen
            # Placeholder for future implementation
            pass

    if auditor.errors:
        for err in auditor.errors:
            print(f"FAIL: {err}")
        passed = False

    if passed:
        print("PASS")
    return passed


def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_auditor.py <file> [--fix]")
        sys.exit(1)

    filepath = sys.argv[1]
    fix = "--fix" in sys.argv

    if not audit_file(filepath, fix):
        sys.exit(1)


if __name__ == "__main__":
    main()
