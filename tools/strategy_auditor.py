#!/usr/bin/env python3
import argparse
import ast
import sys
from pathlib import Path

REQUIRED_HEADER_FIELDS = [
    "Strategy",
    "Author",
    "Version",
    "Timeframes",
    "Pair format",
    "Timezone",
    "Entry",
    "Exit",
    "No repainting",
]


class StrategyAuditor:
    def __init__(self, fix=False):
        self.fix = fix
        self.errors = []
        self.source_lines = []

    def check_header(self, tree, source, filepath):
        docstring = ast.get_docstring(tree)
        if not docstring:
            if self.fix:
                self.fix_header(filepath, source)
                return True

            self.errors.append("Missing module docstring (Header block)")
            return False

        missing_fields = []
        for field in REQUIRED_HEADER_FIELDS:
            # Flexible check: "Field:" or just "Field" in text
            if f"{field}:" not in docstring and f"{field}" not in docstring:
                missing_fields.append(field)

        if missing_fields:
            if self.fix:
                self.fix_header(filepath, source, docstring)
                return True

            self.errors.append(f"Header missing fields: {', '.join(missing_fields)}")
            return False
        return True

    def fix_header(self, filepath, source, existing_docstring=None):
        print(f"Fixing header for {filepath}...")

        header_fields = [
            "Strategy: [Name]",
            "Author: [Author]",
            "Version: [Version]",
            "Timeframes: [Timeframes]",
            "Pair format: Delta contract symbols (e.g. BTCUSDT) vs "
            "Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT)",
            "Timezone: UTC ISO-8601",
            "Entry: Long entry conditions",
            "Exit: Long exit conditions",
            "No repainting: Only act on closed candles (no incomplete candle usage)",
        ]

        if not existing_docstring:
            new_header = '"""\n' + "\n".join(header_fields) + '\n"""\n'
            with Path(filepath).open("w") as f:
                f.write(new_header + source)
        else:
            tree = ast.parse(source)
            doc_node = tree.body[0]
            start_line = doc_node.lineno
            end_line = doc_node.end_lineno

            new_docstring_content = (
                existing_docstring.strip() + "\n\n" + "\n".join(header_fields)
            )
            new_docstring = f'"""\n{new_docstring_content}\n"""'

            new_source_lines = (
                self.source_lines[: start_line - 1]
                + [new_docstring]
                + self.source_lines[end_line:]
            )

            with Path(filepath).open("w") as f:
                f.write("\n".join(new_source_lines) + "\n")

    def check_populate_functions(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in [
                "populate_entry_trend",
                "populate_exit_trend",
                "populate_entry_trend_short",
                "populate_exit_trend_short",
            ]:
                self._check_function_conditions(node)
                self._check_function_comments(node)

    def _check_function_conditions(self, func_node):
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        sl = target.slice
                        if isinstance(sl, ast.Index):  # python < 3.9
                            sl = sl.value

                        row_indexer = None
                        if isinstance(sl, ast.Tuple):
                            if len(sl.elts) >= 1:
                                row_indexer = sl.elts[0]
                        else:
                            row_indexer = sl

                        if row_indexer:
                            if isinstance(
                                row_indexer, (ast.BoolOp, ast.BinOp, ast.Compare)
                            ):
                                self.errors.append(
                                    f"In {func_node.name} line {node.lineno}: "
                                    "Condition must be a named variable (found inline expression)."
                                )
                            elif isinstance(row_indexer, ast.Call):
                                self.errors.append(
                                    f"In {func_node.name} line {node.lineno}: "
                                    "Condition must be a named variable (found function call)."
                                )

    def _check_function_comments(self, func_node):
        if not hasattr(func_node, "end_lineno"):
            return

        start = func_node.lineno
        end = func_node.end_lineno
        body_lines = self.source_lines[start - 1 : end]

        has_comment = False
        for line in body_lines:
            if "#" in line:
                has_comment = True
                break

        if not has_comment:
            self.errors.append(f"Function {func_node.name} lacks comments explaining logic.")

    def _is_true_value(self, node_value):
        if isinstance(node_value, ast.Constant) and node_value.value is True:
            return True
        if isinstance(node_value, ast.NameConstant) and node_value.value is True:
            return True
        return False

    def _check_assign_node(self, node):
        if not isinstance(node, ast.Assign):
            return False
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "process_only_new_candles"
                and self._is_true_value(node.value)
            ):
                return True
        return False

    def check_process_only_new_candles(self, tree):
        found = False
        for node in ast.walk(tree):
            if self._check_assign_node(node):
                found = True
                break

            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if self._check_assign_node(item):
                        found = True
                        break
            if found:
                break

        if not found:
            self.errors.append(
                "Missing 'process_only_new_candles = True' (Required for 'No repainting')"
            )

    def check_unsafe_imports(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name in ["requests", "urllib", "socket", "http"]:
                        self.errors.append(f"Unsafe import: {n.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in ["requests", "urllib", "socket", "http"]:
                    self.errors.append(f"Unsafe import from: {node.module}")

    def check_naive_datetime(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "now":
                        if not node.args and not node.keywords:
                            self.errors.append(
                                f"Potential naive datetime.now() usage at line {node.lineno}. "
                                "Use datetime.now(UTC)."
                            )

    def audit(self, filepath):
        print(f"Auditing {filepath}...")
        self.errors = []
        with Path(filepath).open() as f:
            source = f.read()

        self.source_lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            print(f"FAIL: Syntax Error in {filepath}: {exc}")
            return False

        self.check_header(tree, source, filepath)
        self.check_unsafe_imports(tree)
        self.check_naive_datetime(tree)
        self.check_process_only_new_candles(tree)
        self.check_populate_functions(tree)

        if self.errors:
            for e in self.errors:
                print(f"  ERROR: {e}")
            return False

        print("PASS")
        return True


def main():
    parser = argparse.ArgumentParser(description="Strategy Auditor")
    parser.add_argument("path", help="File or directory to audit")
    parser.add_argument(
        "--fix", action="store_true", help="Attempt to fix simple issues (headers)"
    )
    args = parser.parse_args()

    auditor = StrategyAuditor(fix=args.fix)
    failed = False

    target = Path(args.path)
    if target.is_file():
        if not auditor.audit(target):
            failed = True
    else:
        for file in target.rglob("*.py"):
            if file.name.startswith("__"):
                continue
            if "_base" in str(file):
                continue
            if not auditor.audit(file):
                failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
