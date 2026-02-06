#!/usr/bin/env python3
import ast
import os
import sys
import argparse
from pathlib import Path

REQUIRED_HEADER_FIELDS = [
    "Strategy", "Author", "Version", "Timeframe",
    "Pair Format", "Timezone", "Entry/Exit", "Repainting"
]

HEADER_TEMPLATE = """
    # Strategy: {name}
    # Author: Unknown
    # Version: 1.0
    # Timeframe: 5m
    # Pair Format: BASE/QUOTE:SETTLE
    # Timezone: UTC
    # Entry/Exit: Limit/Limit
    # Repainting: No
"""

def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open() as f:
            source = f.read()
    except Exception as e:
        print(f"FAIL: Could not read file {filepath}: {e}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []

    # 1. Header Check
    docstring = ast.get_docstring(tree)
    if not docstring:
        if fix:
            print("Fixing: Adding missing header block...")
            new_source = f'"""{HEADER_TEMPLATE.format(name=Path(filepath).stem)}\n"""\n' + source
            with Path(filepath).open("w") as f:
                f.write(new_source)
            return audit_file(filepath, fix=False)
        else:
            errors.append("Missing module docstring (Header block)")
    else:
        missing_fields = [field for field in REQUIRED_HEADER_FIELDS if field not in docstring]
        if missing_fields:
            errors.append(f"Header missing fields: {', '.join(missing_fields)}")

    # 2. Unsafe Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http", "subprocess"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http", "subprocess"]:
                errors.append(f"Unsafe import from: {node.module}")

    # 3. Naive datetime.now() check
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                if not node.args and not node.keywords:
                     errors.append(f"Potential naive datetime.now() at line {node.lineno}. Use datetime.now(timezone.utc).")

    # 4. Mixin Inheritance
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases:
                if "AuditedStrategyMixin" not in bases:
                     errors.append(f"Strategy class '{node.name}' should inherit AuditedStrategyMixin")

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix simple issues (header)")
    args = parser.parse_args()

    target = Path(args.path)
    failed = False

    if target.is_file():
        if not audit_file(str(target), args.fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            # Skip _base directory or any directory starting with _
            if "_base" in root or any(part.startswith('_') for part in Path(root).parts):
                continue

            for file in files:
                if file.endswith(".py") and not file.startswith("__") and not file.startswith("_"):
                    if not audit_file(str(Path(root) / file), args.fix):
                        failed = True

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
