#!/usr/bin/env python3
import argparse
import ast
import sys


class StrategyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.has_docstring = False

    def visit_Module(self, node):
        if ast.get_docstring(node):
            self.has_docstring = True
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for datetime.now() without tz
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
                if node.func.attr == "now":
                    # Check arguments for timezone
                    # If args is empty and keywords empty, it's unsafe
                    if not node.args and not node.keywords:
                        self.errors.append(
                            f"Line {node.lineno}: datetime.now() called without timezone. Use datetime.now(timezone.utc)"
                        )

            # Check for requests.*
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "requests":
                self.errors.append(f"Line {node.lineno}: Network call detected (requests).")
            # Check for urllib.*
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "urllib":
                self.errors.append(f"Line {node.lineno}: Network call detected (urllib).")

        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in ["requests", "urllib", "socket", "http"]:
                self.errors.append(
                    f"Line {node.lineno}: Forbidden import '{alias.name}'. Strategies should not make network calls."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in ["requests", "urllib", "socket", "http"]:
            self.errors.append(f"Line {node.lineno}: Forbidden import from '{node.module}'.")
        self.generic_visit(node)


def audit_strategy(filepath):
    print(f"Auditing {filepath}...")
    try:
        with open(filepath, "r") as f:
            source = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Syntax Error: {e}")
        return False

    visitor = StrategyVisitor()
    visitor.visit(tree)

    success = True
    if not visitor.has_docstring:
        print("FAIL: Missing module docstring (Header block).")
        success = False

    if visitor.errors:
        success = False
        for err in visitor.errors:
            print(f"FAIL: {err}")

    # Heuristic for "process_only_new_candles" or comment
    if "process_only_new_candles" not in source and "startup_candle_count" not in source:
        print(
            "WARN: Could not find 'process_only_new_candles' or 'startup_candle_count'. Ensure explicit handling."
        )

    if success:
        print("PASS: Strategy passed audit.")
    else:
        print("FAIL: Strategy failed audit.")

    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)

    args = parser.parse_args()

    if audit_strategy(args.file):
        sys.exit(0)
    else:
        sys.exit(1)
