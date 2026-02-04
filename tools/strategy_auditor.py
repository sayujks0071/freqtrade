#!/usr/bin/env python3
import argparse
import ast
import re
import sys
from pathlib import Path


HEADER_TEMPLATE = """\"\"\"
Strategy Name: {name}
Author: {author}
Version: {version}
Supported Timeframes: {timeframes}

Supported Pair Format:
- Delta Contract: BTCUSDT (example)
- Freqtrade Pair: BTC/USDT:USDT (example)

Timezone Rule:
- All timestamps must be UTC ISO-8601.

Entry/Exit Definitions:
- Long Entry: {long_entry}
- Long Exit: {long_exit}
- Short Entry: {short_entry}
- Short Exit: {short_exit}

No Repainting:
- Logic must strictly rely on closed candles (process_only_new_candles=True).
\"\"\"
"""


def get_strategy_class_node(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from IStrategy (heuristic)
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "IStrategy":
                    return node
    return None


def check_header(source, tree, filepath, fix=False):
    docstring = ast.get_docstring(tree)
    name = Path(filepath).stem
    new_header = HEADER_TEMPLATE.format(
        name=name,
        author="Unknown",
        version="1.0",
        timeframes="Unknown",
        long_entry="Fill me",
        long_exit="Fill me",
        short_entry="Fill me",
        short_exit="Fill me",
    )

    if docstring:
        # Check if it contains required sections
        required = [
            "Strategy Name",
            "Supported Pair Format",
            "Timezone Rule",
            "Entry/Exit Definitions",
            "No Repainting",
        ]
        missing = [r for r in required if r not in docstring]
        if not missing:
            return True, source
        else:
            print(f"  [Header] Partial header found. Missing: {missing}")
            if fix:
                print("  [Header] Normalizing header (replacing existing).")
                # Try to replace existing docstring using regex to find it at start of file
                # Match first triple quoted string (double or single quotes)
                # We assume it's at the start
                # (ignoring shebang/encoding for simplicity or handle it)
                # simple regex: start of string, optional whitespace/comments, then docstring.
                match = re.match(r'(\s*?)(""".*?"""|\'\'\'.*?\'\'\')', source, re.DOTALL)
                if match:
                    # Keep the leading whitespace/comments if any, replace the docstring
                    prefix = match.group(1)
                    end = match.end()
                    return True, prefix + new_header.strip() + "\n" + source[end:]
                else:
                    # Could not match easily, maybe it's not a triple quoted string?
                    # (ast.get_docstring handles others)
                    # Fallback: Prepend
                    print(
                        "  [Header] Could not reliably locate old docstring to replace. Prepending."
                    )
                    return True, new_header + source
            return False, source
    else:
        print("  [Header] Missing header.")
        if fix:
            print("  [Header] Inserting header template.")
            # Insert at top
            return True, new_header + source
        return False, source


def check_logic(tree):  # noqa: C901
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
        ]:
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Assign):
                    # Check assignments to dataframe loc
                    # dataframe.loc[ MASK, 'col' ] = 1
                    for target in subnode.targets:
                        if isinstance(target, ast.Subscript):
                            # Check if target is dataframe.loc
                            is_loc = False
                            if (
                                isinstance(target.value, ast.Attribute)
                                and target.value.attr == "loc"
                            ):
                                is_loc = True

                            if is_loc:
                                # Check the slice (index)
                                sl = target.slice
                                # In Python < 3.9, it's ast.Index wrapping the content
                                if isinstance(sl, ast.Index):
                                    sl = sl.value

                                # If tuple (mask, column), take first element
                                condition = sl
                                if isinstance(sl, ast.Tuple):
                                    if len(sl.elts) > 0:
                                        condition = sl.elts[0]

                                # Check if condition is "complex"
                                # We enforce named boolean variable.
                                # So condition should be ast.Name.
                                # If it is BinOp (A & B) or BoolOp (A and B) or Compare,
                                # it is inline.
                                if isinstance(condition, (ast.BinOp, ast.BoolOp)):
                                    # Allow very simple ones?
                                    # Prompt: "named boolean sub-conditions
                                    # (no giant unreadable one-liners)"
                                    # Let's be strict: Must be Name.
                                    errors.append(
                                        f"Complex inline condition in {node.name} "
                                        f"at line {subnode.lineno}. Use named boolean variables."
                                    )
                                elif isinstance(condition, ast.Compare):
                                    # Single comparison might be OK? "dataframe['rsi'] < 30"
                                    # But "named boolean sub-conditions" suggests extracting
                                    # even that.
                                    pass
    return errors


def check_sanity(tree):
    errors = []
    for node in ast.walk(tree):
        # Unsafe imports
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")

        # Naive datetime.now()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                # Check args for timezone
                if not node.args and not node.keywords:
                    errors.append(
                        f"Potential naive datetime.now() at line {node.lineno}. "
                        "Use datetime.now(timezone.utc)."
                    )
    return errors


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    with Path(filepath).open("r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  [Error] Syntax error: {e}")
        return False

    # Header
    header_ok, new_source = check_header(source, tree, filepath, fix)
    if fix and source != new_source:
        with Path(filepath).open("w", encoding="utf-8") as f:
            f.write(new_source)
        # Re-parse
        tree = ast.parse(new_source)
        source = new_source

    header_failed = not header_ok

    # Logic
    logic_errors = check_logic(tree)
    for err in logic_errors:
        print(f"  [Logic] {err}")

    # Sanity
    sanity_errors = check_sanity(tree)
    for err in sanity_errors:
        print(f"  [Sanity] {err}")

    if header_failed or logic_errors or sanity_errors:
        return False

    print("  [OK] Passed.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="Path to strategy file or directory")
    parser.add_argument(
        "--fix", action="store_true", help="Auto-fix issues (e.g. insert header)"
    )
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Target {target} does not exist.")
        sys.exit(1)

    files = []
    if target.is_file():
        files.append(target)
    else:
        files.extend(target.glob("**/*.py"))

    failed = False
    for f in files:
        # Skip __init__.py and mixins (heuristic: starts with _)
        if f.name.startswith("__") or f.name.startswith("_") or "Mixin" in f.name:
            continue

        if not audit_file(str(f), fix=args.fix):
            failed = True

    if failed:
        sys.exit(1)
    else:
        print("All strategies passed audit.")
        sys.exit(0)


if __name__ == "__main__":
    main()
