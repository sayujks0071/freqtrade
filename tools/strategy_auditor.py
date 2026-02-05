#!/usr/bin/env python3
"""
Strategy Auditor Tool
Enforces coding standards, header requirements, and auditability for Freqtrade strategies.
"""

import argparse
import ast
import os
import sys
from pathlib import Path
from typing import List, Optional

HEADER_TEMPLATE = """\"\"\"
Strategy: {name}
Author: {author}
Version: {version}
Timeframe: {timeframe}

Description:
{description}

Pair Format:
- Delta futures contracts (e.g. BTCUSDT).
- Must match Freqtrade naming BASE/QUOTE:SETTLE (e.g. BTC/USDT:USDT).

Timezone:
- All timestamps logs are UTC ISO-8601.

Entry/Exit:
- Long Entry: {long_entry}
- Long Exit: {long_exit}
- Short Entry: {short_entry}
- Short Exit: {short_exit}

Repainting:
- Logic must strictly run on closed candles. No look-ahead or repainting.
\"\"\"
"""

REQUIRED_HEADER_FIELDS = [
    "Strategy:",
    "Author:",
    "Version:",
    "Timeframe:",
    "Pair Format:",
    "Timezone:",
    "Entry/Exit:",
    "Repainting:",
]


def check_header(tree: ast.Module, source: str) -> List[str]:
    errors = []
    docstring = ast.get_docstring(tree)
    if not docstring:
        return ["Missing module docstring (Header block). Use --fix to auto-generate."]

    for field in REQUIRED_HEADER_FIELDS:
        if field not in docstring:
            errors.append(f"Header missing required field: '{field}'")

    # Check specific content requirements
    if "UTC ISO-8601" not in docstring:
        errors.append("Header must specify 'All timestamps logs are UTC ISO-8601'")
    if "closed candles" not in docstring.lower():
        errors.append("Header must include 'No repainting' note about closed candles")

    return errors


def get_strategy_class_node(tree: ast.Module) -> Optional[ast.ClassDef]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Assumes the strategy is the first/main class in the file
            # or heuristics: inherits from IStrategy
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "IStrategy":
                    return node
    return None


def fix_header(filepath: str, tree: ast.Module):
    """
    Inserts or updates the header block.
    """
    path = Path(filepath)
    with path.open("r") as f:
        lines = f.readlines()

    # Extract existing info if possible or use defaults
    strategy_node = get_strategy_class_node(tree)
    strategy_name = strategy_node.name if strategy_node else "UnknownStrategy"

    # Try to find existing docstring range
    docstring = ast.get_docstring(tree)

    if docstring:
        # Finding the docstring in source is tricky without tokenizing,
        # but since we are replacing/prepending, let's try to be smart.
        # If the first statement is a string expression, it's the docstring.
        if isinstance(tree.body[0], ast.Expr) and isinstance(
            tree.body[0].value, (ast.Str, ast.Constant)
        ):
            # This is the docstring node
            pass
            # But we want to preserve imports if they are after?
            # Usually docstring is top.

    # Defaults
    name = strategy_name
    author = "Unknown"
    version = "1.0"
    timeframe = "1h"
    description = "Strategy for Delta Exchange."
    long_entry = "Trend following"
    long_exit = "Trend reversal"
    short_entry = "Trend following (if enabled)"
    short_exit = "Trend reversal (if enabled)"

    # Render template
    new_header = HEADER_TEMPLATE.format(
        name=name,
        author=author,
        version=version,
        timeframe=timeframe,
        description=description,
        long_entry=long_entry,
        long_exit=long_exit,
        short_entry=short_entry,
        short_exit=short_exit,
    )

    if docstring:
        # We replace the existing docstring.
        # Simple heuristic: Read file, find the lines corresponding to docstring.
        # AST lineno is 1-based.
        # We'll just read the file, skipping the lines of the old docstring?
        # Or simpler: Just prepend if missing, let user fix if incomplete?
        # The prompt says "auto-insert if missing".
        # If it exists but is invalid (missing fields), we should probably append the missing fields or suggest manual fix.
        # BUT the requirement says "Enforces a required header block (auto-insert if missing)".
        # It doesn't explicitly say "overwrite if invalid".
        # I'll implement: If missing, insert. If present but invalid, warn (auditor will fail).
        # Wait, I am implementing --fix.
        # If I want to be helpful, I should maybe rename the old docstring or comment it out and add the new one?
        # Or just tell the user to fix it.
        # Let's stick to: If NO docstring, insert.
        print(f"Docstring exists in {filepath}. Please update it manually to match requirements.")
        return

    # Insert at top
    new_content = new_header + "".join(lines)
    with path.open("w") as f:
        f.write(new_content)
    print(f"Inserted header into {filepath}")


def check_boolean_conditions(tree: ast.Module) -> List[str]:
    errors = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
        ]:
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    # Check for dataframe.loc assignment
                    # target is usually subscript
                    for target in child.targets:
                        if isinstance(target, ast.Subscript):
                            # Check if value is dataframe.loc
                            # usually target is df.loc[index, col]
                            # verify it is 'loc'
                            if (
                                isinstance(target.value, ast.Attribute)
                                and target.value.attr == "loc"
                            ):
                                # Check slice
                                sl = target.slice
                                # In Python 3.9+, slice is the node itself (often Tuple for loc)
                                index_node = None
                                if isinstance(sl, ast.Tuple):
                                    if len(sl.elts) > 0:
                                        index_node = sl.elts[0]
                                elif isinstance(sl, ast.Index):  # Python < 3.9
                                    index_node = sl.value
                                else:
                                    index_node = sl  # Could be just the index if 1D access (unlikely for loc assignment)

                                if index_node:
                                    # Logic: The condition inside loc[...] should be composed of named variables.
                                    # We allow BinOp/BoolOp/UnaryOp ONLY if their leaves are Names.
                                    # We reject Compare (e.g. df['x'] > 1) because that should be a named variable.

                                    def is_clean_condition(n):
                                        if isinstance(n, ast.Name):
                                            return True
                                        if isinstance(n, ast.UnaryOp):
                                            return is_clean_condition(n.operand)
                                        if isinstance(n, ast.BinOp):
                                            return is_clean_condition(
                                                n.left
                                            ) and is_clean_condition(n.right)
                                        if isinstance(n, ast.BoolOp):
                                            return all(is_clean_condition(v) for v in n.values)
                                        # Allow Tuple/List if needed (unlikely for boolean index)?
                                        # Allow Constant? (True/False)
                                        if isinstance(
                                            n, (ast.Constant, ast.NameConstant)
                                        ):  # NameConstant for py < 3.8
                                            return True
                                        return False

                                    if not is_clean_condition(index_node):
                                        # Identify what failed it
                                        # If it's complex, we flag it.
                                        errors.append(
                                            f"Inline boolean condition in {node.name} at line {child.lineno}. "
                                            "Use named boolean variables (no inline comparisons)."
                                        )
    return errors


def check_inheritance(tree: ast.Module, filepath: str) -> List[str]:
    errors = []
    strategy_node = get_strategy_class_node(tree)
    if strategy_node:
        bases = []
        for base in strategy_node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        if "AuditedStrategyMixin" not in bases:
            errors.append(f"Strategy class {strategy_node.name} must inherit AuditedStrategyMixin")

    return errors


def audit_file(filepath: str, fix: bool = False) -> bool:
    print(f"Auditing {filepath}...")
    path = Path(filepath)
    try:
        source = path.read_text()
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"FAIL: Syntax Error in {filepath}: {e}")
        return False

    errors = []

    # Check Header
    header_errors = check_header(tree, source)
    if header_errors:
        if fix and "Missing module docstring" in header_errors[0]:
            fix_header(filepath, tree)
            # Re-read and re-parse to verify? Or just pass for now and let next run verify.
            # But if there were other header errors (missing fields in existing), they remain.
            # Let's assuming fixing handles the missing docstring case.
            # If it was missing, we fixed it, so we can clear that error.
            # But we won't re-audit in this pass.
            errors.append("Header fixed (was missing). Please verify content.")
        else:
            errors.extend(header_errors)

    # Check Boolean Conditions
    errors.extend(check_boolean_conditions(tree))

    # Check Inheritance
    errors.extend(check_inheritance(tree, filepath))

    if errors:
        for e in errors:
            print(f"  - {e}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument(
        "path", nargs="?", default="user_data/strategies", help="File or directory to audit"
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: {target} does not exist")
        sys.exit(1)

    failed = False

    files = []
    if target.is_file():
        files.append(target)
    else:
        for root, _, filenames in os.walk(target):
            for f in filenames:
                if (
                    f.endswith(".py")
                    and not f.startswith("__")
                    and not f.startswith("AuditedStrategyMixin")
                ):
                    # Skip base dir if it's treated as strategy? No, _base is usually excluded by logic or explicitly.
                    # But `walk` goes into _base.
                    if "_base" in root:
                        continue
                    files.append(Path(root) / f)

    for f in files:
        if not audit_file(str(f), args.fix):
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
