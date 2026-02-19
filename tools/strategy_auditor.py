"""
Strategy Auditor
Performs AST-based static analysis on strategies to ensure compliance and safety.
"""
import argparse
import ast
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_HEADER_FIELDS = [
    "Strategy Name",
    "Author",
    "Version",
    "Timeframes",
    "Supported Pair Format",
    "Timezone Rule",
    "Entry/Exit Definitions",
    "No Repainting"
]

class StrategyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.has_process_only_new_candles = False
        self.has_timeframe = False
        self.has_minimal_roi = False
        self.has_stoploss = False
        self.unsafe_imports = []
        self.unsafe_calls = []
        self.class_name = None

    def visit_ClassDef(self, node):
        self.class_name = node.name
        # Check base classes
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "IStrategy" not in bases and "AuditedStrategyMixin" not in bases:
            self.errors.append(f"Class {node.name} does not inherit from IStrategy or AuditedStrategyMixin")

        # Check specific assignments in class body
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "process_only_new_candles":
                            if isinstance(item.value, ast.Constant) and item.value.value is True:
                                self.has_process_only_new_candles = True
                            else:
                                self.errors.append("process_only_new_candles must be True")
                        elif target.id == "timeframe":
                            self.has_timeframe = True
                        elif target.id == "minimal_roi":
                            self.has_minimal_roi = True
                        elif target.id == "stoploss":
                            self.has_stoploss = True

        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in ["requests", "urllib", "socket", "http"]:
                self.unsafe_imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in ["requests", "urllib", "socket", "http"]:
            self.unsafe_imports.append(node.module)
        if node.module == "datetime" and "datetime" in [n.name for n in node.names]:
            # This is fine, but check usage
            pass
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for datetime.now() usage without UTC
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
                    if not node.args:
                        self.unsafe_calls.append("datetime.now() without timezone (use datetime.now(timezone.utc))")
        self.generic_visit(node)

def audit_file(filepath: Path, fix: bool = False):
    logger.info(f"Auditing {filepath}...")
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
        visitor = StrategyVisitor()
        visitor.visit(tree)

        errors = visitor.errors

        # Check Header
        if '"""' not in content[:500]: # Simple heuristic
             errors.append("Missing docstring header")
        else:
            # Check fields
            for field in REQUIRED_HEADER_FIELDS:
                if field not in content:
                    errors.append(f"Header missing required field: {field}")

        if not visitor.has_process_only_new_candles:
             errors.append("process_only_new_candles = True is missing")

        if visitor.unsafe_imports:
             errors.append(f"Unsafe imports detected: {visitor.unsafe_imports}")

        if visitor.unsafe_calls:
             errors.append(f"Unsafe calls detected: {visitor.unsafe_calls}")

        if errors:
            logger.error(f"Audit Failed for {filepath}:")
            for e in errors:
                logger.error(f" - {e}")
            return False

        logger.info(f"Audit Passed for {filepath}.")
        return True

    except Exception as e:
        logger.error(f"Failed to audit {filepath}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("strategies", nargs="+", type=Path, help="Strategy files to audit")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues (not implemented fully)")
    args = parser.parse_args()

    failed = False
    for s in args.strategies:
        if not audit_file(s, args.fix):
            failed = True

    if failed:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
