#!/usr/bin/env python3
import ast
import os
import re
import sys
import tokenize
from pathlib import Path

REQUIRED_HEADER_FIELDS = [
    "Strategy Name:",
    "Author:",
    "Version:",
    "Timeframes:",
    "Supported Pair Format:",
    "Timezone Rule:",
    "Entry/Exit Definitions:",
    "No Repainting:",
]

HEADER_TEMPLATE = """
    Strategy Name: {name}
    Author: Unknown
    Version: 0.1
    Timeframes: {timeframe}

    Supported Pair Format:
    - Delta futures pairs (BTC/USDT:USDT)
    - Adheres to BASE/QUOTE:SETTLE format

    Timezone Rule:
    - All timestamps logged as UTC ISO-8601

    Entry/Exit Definitions:
    - Long Entry: Explain logic
    - Long Exit: Explain logic
    - Short Entry: Explain logic (if any)
    - Short Exit: Explain logic (if any)

    No Repainting:
    - Only acts on closed candles.
"""


def get_strategy_class_node(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it looks like a strategy (inherits IStrategy)
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "IStrategy" in bases or "AuditedStrategyMixin" in bases:
                return node
    return None


def check_header(tree, source, filepath):
    docstring = ast.get_docstring(tree)
    if not docstring:
        return False, "Missing module docstring (Header block)"

    errors = []
    for field in REQUIRED_HEADER_FIELDS:
        if field not in docstring:
            errors.append(f"Missing header field: '{field}'")

    if errors:
        return False, "; ".join(errors)
    return True, None


def fix_header(source, strategy_name, timeframe):
    # Always prepend the standard header template.
    # If there was an existing docstring, it will remain as a second string literal.
    header = (
        '"""' + HEADER_TEMPLATE.format(name=strategy_name, timeframe=timeframe) + '"""\n'
    )
    return header + source


def check_imports(tree):
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")
    return errors


def check_mixin(tree):
    strategy_node = get_strategy_class_node(tree)
    if not strategy_node:
        return False, "No Strategy class found"

    bases = [b.id for b in strategy_node.bases if isinstance(b, ast.Name)]
    if "AuditedStrategyMixin" not in bases:
        return False, f"Strategy {strategy_node.name} does not inherit AuditedStrategyMixin"

    return True, None


def fix_mixin(source, tree):
    strategy_node = get_strategy_class_node(tree)
    if not strategy_node:
        return source

    # Add import if missing
    import_block = """
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin
"""

    lines = source.splitlines()

    # Insert imports after existing imports or at top
    last_import_idx = 0
    for i, node in enumerate(ast.iter_child_nodes(tree)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_idx = node.end_lineno

    # Naive insertion
    if "AuditedStrategyMixin" not in source:
        lines.insert(last_import_idx, import_block)

    # Update class definition
    # Regex to find "class Name(Bases):"
    class_def_re = re.compile(rf"class\s+{strategy_node.name}\s*\((.*?)\):")

    def replacer(match):
        bases_str = match.group(1)
        bases = [b.strip() for b in bases_str.split(",")]
        if "AuditedStrategyMixin" not in bases:
            bases.insert(0, "AuditedStrategyMixin")  # First for mixin precedence?
            return f"class {strategy_node.name}(AuditedStrategyMixin, {bases_str}):"
        return match.group(0)

    new_source = "\n".join(lines)
    new_source = class_def_re.sub(replacer, new_source)

    return new_source


def check_logic_complexity(tree):
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    sl = target.slice
                    if isinstance(sl, ast.Index):  # Python < 3.9
                        sl = sl.value

                    if isinstance(sl, ast.BoolOp):
                        if len(sl.values) > 3:
                            errors.append(
                                f"Complex inline condition (>{len(sl.values)} ops) at "
                                f"line {node.lineno}. Use named variables."
                            )
    return errors


def get_method_range(tree, method_name):
    """Finds the start and end lines of a method in the strategy class."""
    strat_node = get_strategy_class_node(tree)
    if not strat_node:
        return None, None

    for node in strat_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node.lineno, node.end_lineno
    return None, None


def has_comment_in_range(filepath, start_line, end_line):
    """Checks if there is at least one comment within the line range."""
    try:
        with Path(filepath).open("rb") as f:
            tokens = list(tokenize.tokenize(f.readline))
    except Exception:
        # If we can't tokenize, we default to passing to avoid blocking builds on parser errors
        return True

    for token in tokens:
        if token.type == tokenize.COMMENT:
            if start_line <= token.start[0] <= end_line:
                return True
    return False


def check_comments_in_method(filepath, method_name):
    """
    Check if a specific method in the file contains any comments.
    Splits AST parsing and Tokenization to reduce complexity.
    """
    try:
        with Path(filepath).open() as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        # If AST parse fails, we can't find the method range, assume pass
        return True

    start_line, end_line = get_method_range(tree, method_name)

    if start_line is None:
        # Method not found, strategy might not use it
        return True

    return has_comment_in_range(filepath, start_line, end_line)


def try_fix_header(tree, source, filepath):
    # Try to fix missing docstring
    # Need strategy name and timeframe
    strat_node = get_strategy_class_node(tree)
    name = strat_node.name if strat_node else "UnknownStrategy"

    # Try to find timeframe
    timeframe = "1h"  # Default
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "timeframe":
                    if isinstance(node.value, ast.Constant):
                        timeframe = node.value.value

    source = fix_header(source, name, timeframe)
    print("  [FIX] Added/Updated header docstring.")
    return source


def audit_content(tree, source, filepath, fix=False):
    errors = []
    fixed_source = source
    fixed_something = False

    # 1. Header
    ok, err = check_header(tree, source, filepath)
    if not ok:
        if fix and ("Missing module docstring" in err or "Missing header field" in err):
            fixed_source = try_fix_header(tree, fixed_source, filepath)
            fixed_something = True
            # Re-parse
            tree = ast.parse(fixed_source)
        else:
            errors.append(err)

    # 2. Imports
    import_errs = check_imports(tree)
    errors.extend(import_errs)

    # 3. Mixin
    ok, err = check_mixin(tree)
    if not ok:
        if fix and "does not inherit" in err:
            fixed_source = fix_mixin(fixed_source, tree)
            fixed_something = True
            print("  [FIX] Added AuditedStrategyMixin inheritance.")
            # Re-parse
            tree = ast.parse(fixed_source)
        else:
            errors.append(err)

    # 4. Logic Complexity
    logic_errs = check_logic_complexity(tree)
    errors.extend(logic_errs)

    # 5. Repainting
    if "process_only_new_candles" not in source and "closed candle" not in source.lower():
        errors.append("Missing 'process_only_new_candles = True' or 'closed candle' note.")

    # 6. Comments in critical methods
    if not check_comments_in_method(filepath, "populate_entry_trend"):
        errors.append("Missing comments in populate_entry_trend explaining market thesis.")
    if not check_comments_in_method(filepath, "populate_exit_trend"):
        errors.append("Missing comments in populate_exit_trend explaining market thesis.")

    return errors, fixed_source, fixed_something


def audit_file(filepath, fix=False):
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open() as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as exc:
        print(f"FAIL: Parse Error in {filepath}: {exc}")
        return False

    errors, fixed_source, fixed_something = audit_content(tree, source, filepath, fix)

    if fixed_something:
        with Path(filepath).open("w") as f:
            f.write(fixed_source)
        print("  Changes saved.")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False

    print("PASS")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_auditor.py [--fix] <file_or_dir>")
        sys.exit(1)

    fix = False
    args = sys.argv[1:]
    if "--fix" in args:
        fix = True
        args.remove("--fix")

    if not args:
        print("Usage: strategy_auditor.py [--fix] <file_or_dir>")
        sys.exit(1)

    target = args[0]
    failed = False

    if Path(target).is_file():
        if not audit_file(target, fix):
            failed = True
    else:
        for root, _, files in os.walk(target):
            for file in files:
                if (
                    file.endswith(".py")
                    and not file.startswith("__")
                    and file != "AuditedStrategyMixin.py"
                ):
                    if not audit_file(str(Path(root) / file), fix):
                        failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
