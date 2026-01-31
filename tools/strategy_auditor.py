#!/usr/bin/env python3
import ast
import sys
import os

def audit_file(filepath):
    print(f"Auditing {filepath}...")
    with open(filepath, 'r') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"FAIL: Syntax Error in {filepath}: {e}")
        return False

    errors = []

    # Check 1: Docstring (Header block)
    if not ast.get_docstring(tree):
        errors.append("Missing module docstring (Header block)")

    # Check 2: Unsafe Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ['requests', 'urllib', 'socket', 'http']:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ['requests', 'urllib', 'socket', 'http']:
                errors.append(f"Unsafe import from: {node.module}")

    # Check 3: datetime.now() usage (heuristic)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # check for .now()
                if node.func.attr == 'now':
                    # This is loose, matches any .now()
                    # Check if it has arguments (timezone)
                    if not node.args and not node.keywords:
                        errors.append(f"Potential naive datetime.now() usage at line {node.lineno}")

    # Check 4: Enforce AuditedStrategyMixin (heuristic)
    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            # Check bases
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if 'IStrategy' in bases and 'AuditedStrategyMixin' not in bases:
                 # It's okay if it inherits from a class that inherits mixin, but hard to check.
                 # Warn if it inherits directly from IStrategy but not Mixin
                 if filepath.endswith("DeltaSafeStrategy.py"): # Strict for our sample
                     errors.append("DeltaSafeStrategy must inherit AuditedStrategyMixin")

    if not has_class:
        # Might be a library file, skip strict checks?
        pass

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_auditor.py <file_or_dir>")
        sys.exit(1)

    target = sys.argv[1]
    failed = False

    if os.path.isfile(target):
        if not audit_file(target):
            failed = True
    else:
        for root, dirs, files in os.walk(target):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if not audit_file(os.path.join(root, file)):
                        failed = True

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
