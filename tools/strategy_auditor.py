#!/usr/bin/env python3
import ast
import os
import sys
from pathlib import Path


# Strategy Auditor: Checks for safety and code quality in strategies

BANNED_IMPORTS = ["os", "subprocess", "shutil", "requests", "urllib", "socket"]
BANNED_CALLS = ["eval", "exec", "input"]
REQUIRED_BASE = "IStrategy"  # Or AuditedStrategyMixin


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.errors = []
        self.warnings = []

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in BANNED_IMPORTS:
                self.errors.append(
                    f"Line {node.lineno}: Banned import '{alias.name}' detected."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in BANNED_IMPORTS:
            self.errors.append(
                f"Line {node.lineno}: Banned import from '{node.module}' detected."
            )
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in BANNED_CALLS:
                self.errors.append(f"Line {node.lineno}: Banned call '{node.func.id}' detected.")
        # Check for datetime.now() without UTC
        if isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "now"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                # Heuristic: check if arguments present (timezone)
                if not node.args and not node.keywords:
                    self.warnings.append(
                        f"Line {node.lineno}: datetime.now() called without timezone. "
                        f"Use datetime.now(timezone.utc)."
                    )
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Check inheritance
        # This is hard because we don't know the full mro, but we can check explicit bases
        # We want to encourage using AuditedStrategyMixin
        self.generic_visit(node)


def audit_file(filepath):
    try:
        with Path(filepath).open("r") as f:
            tree = ast.parse(f.read(), filename=filepath)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return False

    visitor = StrategyVisitor(filepath)
    visitor.visit(tree)

    if visitor.errors or visitor.warnings:
        print(f"\nAudit Report for {filepath}:")
        for err in visitor.errors:
            print(f"  [ERROR] {err}")
        for warn in visitor.warnings:
            print(f"  [WARN]  {warn}")

    if visitor.errors:
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_auditor.py <strategy_file_or_dir>")
        sys.exit(1)

    target = sys.argv[1]
    success = True

    if Path(target).is_dir():
        for root, dirs, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and file != "__init__.py":
                    if not audit_file(Path(root) / file):
                        success = False
    else:
        if not audit_file(target):
            success = False

    if not success:
        sys.exit(1)
    print("\nAudit passed.")


if __name__ == "__main__":
    main()
