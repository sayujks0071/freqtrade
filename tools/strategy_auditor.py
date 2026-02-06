#!/usr/bin/env python3
import argparse
import ast
import re
import sys
from pathlib import Path


REQUIRED_HEADER_TEMPLATE = """
    Strategy Name: {name}
    Author: {author}
    Version: {version}
    Supported Timeframes: {timeframes}

    Supported Pair Format:
      - Delta Contract: BTCUSDT (Example)
      - Freqtrade/CCXT: BTC/USDT:USDT (Example)

    Timezone:
      - All timestamps logged as UTC ISO-8601

    Entry Conditions:
      - Long: {long_entry}
      - Short: {short_entry}

    Exit Conditions:
      - Long: {long_exit}
      - Short: {short_exit}

    No Repainting:
      - This strategy strictly acts on closed candles.
      - No logic is based on incomplete/current candle data.
"""


def get_header_info(docstring):
    """
    Parse existing docstring to extract info if possible.
    """
    info = {
        "name": "Unknown",
        "author": "Unknown",
        "version": "1.0",
        "timeframes": "Unknown",
        "long_entry": "TODO: Describe long entry",
        "short_entry": "TODO: Describe short entry (or N/A)",
        "long_exit": "TODO: Describe long exit",
        "short_exit": "TODO: Describe short exit (or N/A)",
    }
    if not docstring:
        return info

    # Simple regex extraction (can be improved)
    name_match = re.search(r"Strategy Name:\s*(.*)", docstring)
    if name_match:
        info["name"] = name_match.group(1).strip()

    author_match = re.search(r"Author:\s*(.*)", docstring)
    if author_match:
        info["author"] = author_match.group(1).strip()

    # If name is still unknown, try to infer from class name later (caller handles this)
    return info


def generate_header(info):
    return REQUIRED_HEADER_TEMPLATE.format(**info).strip()


def audit_file(filepath, fix=False):  # noqa: C901
    print(f"Auditing {filepath}...")
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            source = f.read()
    except Exception as read_err:
        print(f"FAIL: Could not read {filepath}: {read_err}")
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"FAIL: Syntax Error in {filepath}: {exc}")
        return False

    errors = []
    fixed = False

    # --- Check 1: Header Block ---
    docstring = ast.get_docstring(tree)
    header_valid = False
    if docstring:
        # Check for key phrases
        checks = [
            "Strategy Name:",
            "Author:",
            "Supported Pair Format:",
            "Timezone:",
            "Entry Conditions:",
            "Exit Conditions:",
            "No Repainting:",
        ]
        if all(c in docstring for c in checks):
            header_valid = True
        else:
            errors.append("Header block missing required sections.")
    else:
        errors.append("Missing module docstring (Header block).")

    if not header_valid and fix:
        print("  - Fixing Header Block...")
        # Infer strategy name from class def if possible
        strategy_name = "Unknown"
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if any(b.id == "IStrategy" for b in node.bases if isinstance(b, ast.Name)):
                    strategy_name = node.name
                    break

        info = get_header_info(docstring)
        if info["name"] == "Unknown":
            info["name"] = strategy_name

        new_header = generate_header(info)

        # Insert or replace docstring
        if docstring:
            # Replace existing docstring
            # This is tricky with string manipulation, relying on ast.get_docstring isn't enough
            # to replace.
            # We will use regex to replace the first string literal if it's at the top.
            # But simple append to top if missing is safer, or replace if we can find it.

            # Simple approach: If docstring exists, we assume it's the first statement.
            # We will prepend the NEW header to the old docstring or replace it?
            # Instructions say "Enforce a required header block (auto-insert if missing)".
            # If it's partial, we might want to append?
            # Let's just prepend the standardized block to the file content if missing.
            # If docstring exists, we replace it.

            # Finding the docstring range
            module_body = tree.body
            if (
                module_body
                and isinstance(module_body[0], ast.Expr)
                and isinstance(module_body[0].value, ast.Constant)
                and isinstance(module_body[0].value.value, str)
            ):
                # Found docstring
                # We can't easily replace ranges in source string without tokenizing.
                # Regex replace of the specific string content might work if unique.
                # We'll replace the first occurrence
                source = source.replace(docstring, new_header, 1)
                fixed = True
            else:
                # Should have been found by get_docstring...
                pass
        else:
            # Insert at top
            source = f'"""\n{new_header}\n"""\n\n' + source
            fixed = True

        # Re-parse to clear this error for subsequent checks (simulated)
        errors = [err for err in errors if "Header" not in err]

    # --- Check 2: Unsafe Imports ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name in ["requests", "urllib", "socket", "http"]:
                    errors.append(f"Unsafe import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in ["requests", "urllib", "socket", "http"]:
                errors.append(f"Unsafe import from: {node.module}")

    # --- Check 3: datetime.now() usage ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                # Check if it has arguments (timezone)
                if not node.args and not node.keywords:
                    errors.append(
                        f"Potential naive datetime.now() usage at line {node.lineno}. "
                        "Use datetime.now(timezone.utc)."
                    )

    # --- Check 4: Enforce AuditedStrategyMixin & Sanity Checks ---
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]

            if "IStrategy" in bases:
                if "AuditedStrategyMixin" not in bases:
                    if fix:
                        # We can't easily fix inheritance via AST in text without complex parsing.
                        # User must do this manually or we append mixin?
                        # Requirement says "Modify selected strategies...".
                        # I will do that manually in next steps.
                        # Here we just report.
                        errors.append("Strategy must inherit AuditedStrategyMixin")
                    else:
                        errors.append("Strategy must inherit AuditedStrategyMixin")

    # --- Check 5: Entry/Exit Trend Validation ---
    # Validate populate_entry_trend and populate_exit_trend
    # - named boolean sub-conditions
    # - comments explaining market thesis

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in [
            "populate_entry_trend",
            "populate_exit_trend",
        ]:
            # Check for comments (comments are not in AST, need tokenizing or third party lib,
            # or we check if there are string literals acting as comments?
            # No, python comments are ignored).
            # However, `ast` in recent python versions (3.8+) exposes type_ignores but not comments.
            # We can check for string literals used as comments? No, usually people use #.
            # To check for comments, we have to parse the source lines corresponding
            # to the function body.

            # Simple heuristic: Check if there are ANY comments in the function body lines.
            func_source = source.splitlines()[node.lineno - 1 : node.end_lineno]
            has_comment = any("#" in line for line in func_source)
            if not has_comment:
                errors.append(f"{node.name} missing comments explaining market thesis.")

            # Check for complex inline conditions in .loc assignments
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Assign):
                    for target in subnode.targets:
                        # Check if target is dataframe.loc[...]
                        if isinstance(target, ast.Subscript):
                            if (
                                isinstance(target.value, ast.Name)
                                and target.value.id == "dataframe"
                            ):  # Assuming dataframe is the name
                                # Check slice
                                sl = target.slice
                                # In Python < 3.9, it's ast.Index
                                if isinstance(sl, ast.Index):
                                    sl = sl.value

                                # Check if the index is a complex BoolOp
                                if isinstance(sl, ast.BoolOp):
                                    if (
                                        len(sl.values) > 2
                                    ):  # Allow (A) & (B), but (A) & (B) & (C) might be too much?
                                        # "named boolean sub-conditions" implies we shouldn't have
                                        # raw (df['x']>1) & (df['y']<2) inside loc.
                                        # Even 2 might be considered "inline".
                                        # Let's be strict: if it's a BoolOp, suggest named variable.
                                        errors.append(
                                            f"Complex inline condition in {node.name} at line "
                                            f"{subnode.lineno}. Use named variables."
                                        )
                                elif isinstance(sl, ast.Tuple):  # .loc[row, col]
                                    # Check row index
                                    row_idx = sl.elts[0]
                                    if isinstance(row_idx, ast.BoolOp):
                                        errors.append(
                                            f"Complex inline condition in {node.name} at line "
                                            f"{subnode.lineno}. Use named variables."
                                        )

    # Save changes if fixed
    if fixed and fix:
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                f.write(source)
            print(f"  - FIXED: Applied changes to {filepath}")
            # Re-run audit to verify? Or just warn about remaining issues.
            print("  - Rerunning audit on fixed file...")
            return audit_file(filepath, fix=False)
        except Exception as write_err:
            print(f"FAILED to write fix to {filepath}: {write_err}")
            return False

    if errors:
        for err in errors:
            print(f"  - ERROR: {err}")
        return False

    print("PASS")
    return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues (add headers)")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: {target} does not exist.")
        sys.exit(1)

    failed = False
    if target.is_file():
        if not audit_file(str(target), fix=args.fix):
            failed = True
    else:
        for file in target.rglob("*.py"):
            if not file.name.startswith("__"):
                if not audit_file(str(file), fix=args.fix):
                    failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
