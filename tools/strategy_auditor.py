#!/usr/bin/env python3
import argparse
import ast
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


# Required header template
HEADER_TEMPLATE = '''"""
Strategy: {class_name}
Author: (Audit Tool)
Date: {date}
"""
'''

class AuditVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.errors = []
        self.has_class = False
        self.class_name = None
        self.has_process_new_candles = False
        self.has_docstring = False
        self.bases = []

    def visit_Module(self, node):
        self.has_docstring = ast.get_docstring(node) is not None
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.has_class = True
        self.class_name = node.name

        # Check bases
        self.bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "IStrategy" in self.bases and "AuditedStrategyMixin" not in self.bases:
             self.errors.append(f"Class {node.name} does not inherit 'AuditedStrategyMixin'")

        # Check body for attributes
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "process_only_new_candles":
                             self.has_process_new_candles = True

        self.generic_visit(node)

    def visit_Import(self, node):
        for n in node.names:
            if n.name in ["requests", "urllib", "socket", "http"]:
                self.errors.append(f"Unsafe import: {n.name}")

    def visit_ImportFrom(self, node):
        if node.module in ["requests", "urllib", "socket", "http"]:
            self.errors.append(f"Unsafe import from: {node.module}")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":
                 # Check if it has arguments (timezone)
                if not node.args and not node.keywords:
                    self.errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")
        self.generic_visit(node)


class FixTransformer(ast.NodeTransformer):
    def __init__(self):
        self.modified = False

    def visit_ClassDef(self, node):
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "IStrategy" in bases and "AuditedStrategyMixin" not in bases:
            node.bases.append(ast.Name(id="AuditedStrategyMixin", ctx=ast.Load()))
            self.modified = True

        # Ensure process_only_new_candles = True
        has_proc = False
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "process_only_new_candles":
                        has_proc = True

        if not has_proc:
             assign = ast.Assign(
                 targets=[ast.Name(id="process_only_new_candles", ctx=ast.Store())],
                 value=ast.Constant(value=True),
                 lineno=node.lineno + 1
             )
             node.body.insert(0, assign)
             self.modified = True

        return node

def audit_file(filepath, fix=False):  # noqa: C901
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"FAIL: Could not read {filepath}: {e}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    visitor = AuditVisitor(filepath)
    visitor.visit(tree)

    # Check for closed candle comment (simple string check)
    if "closed candle" not in source.lower():
        visitor.errors.append("Missing 'closed candle' note/comment")

    if not visitor.has_docstring:
        visitor.errors.append("Missing module docstring (Header block)")

    if visitor.errors:
        print("Errors found:")
        for e in visitor.errors:
            print(f"  - {e}")

        if fix:
            print("Attempting fixes...")
            transformer = FixTransformer()
            new_tree = transformer.visit(tree)

            # Re-generate source code
            try:
                new_source = ast.unparse(new_tree)

                # Manual fixes (Imports & Header)
                lines = new_source.splitlines()

                # 1. Add Header if missing
                if not visitor.has_docstring and visitor.class_name:
                    header = HEADER_TEMPLATE.format(
                        class_name=visitor.class_name,
                        date=datetime.now(UTC).strftime("%Y-%m-%d")
                    )
                    new_source = header + "\n" + new_source

                # 2. Add Import if missing (and we added Mixin usage)
                # We need: sys.path.append(...) and from AuditedStrategyMixin ...
                # This is tricky to insert correctly.
                # We'll append it after imports? Or at top.
                if transformer.modified and "AuditedStrategyMixin" not in source:
                    # Very rough injection
                    import_block = (
                        "\nimport sys\n"
                        "from pathlib import Path\n"
                        "sys.path.append(str(Path(__file__).parent / '_base'))\n"
                        "from AuditedStrategyMixin import AuditedStrategyMixin\n\n"
                    )
                    # Find first import or class def
                    insert_idx = 0
                    lines = new_source.splitlines()
                    for i, line in enumerate(lines):
                         if line.startswith("import ") or line.startswith("from "):
                             insert_idx = i
                             break

                    lines.insert(insert_idx, import_block)
                    new_source = "\n".join(lines)

                # Write back
                with Path(filepath).open("w", encoding="utf-8") as f:
                    f.write(new_source)

                print(f"Fixed {filepath}. Please run 'ruff format' to restore style.")
                return True
            except Exception as e:
                print(f"Failed to apply fixes: {e}")
                return False
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    args = parser.parse_args()

    failed = False
    path = Path(args.path)

    if path.is_file():
        if not audit_file(str(path), args.fix):
            failed = True
    else:
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                     if "_base" in root or "strategies_vendor" in root:
                         continue
                     if not audit_file(str(Path(root) / file), args.fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
