#!/usr/bin/env python3
import ast
import argparse
import os
import sys
import glob

REQUIRED_HEADER_TEMPLATE = """
    Strategy Name: {name}
    Author: <Author>
    Version: <Version>
    Supported Timeframes: <Timeframes>
    Supported Pair format: <Delta/Freqtrade/etc>
    Timezone: UTC (timestamps logged as UTC ISO-8601)

    Entry Conditions:
        Long: <Describe long entry>
        Short: <Describe short entry>

    Exit Conditions:
        Long: <Describe long exit>
        Short: <Describe short exit>

    No Repainting: This strategy only acts on closed candles.
"""

REQUIRED_SECTIONS = [
    "Strategy Name", "Author", "Version", "Supported Timeframes",
    "Supported Pair format", "Timezone", "Entry Conditions", "Exit Conditions", "No Repainting"
]

class StrategyVisitor(ast.NodeVisitor):
    def __init__(self, filepath, fix_mode=False):
        self.filepath = filepath
        self.fix_mode = fix_mode
        self.errors = []
        self.fixed_content = None
        self.source_code = ""
        self.has_strategy = False

    def visit_ClassDef(self, node):
        is_strategy = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == 'IStrategy':
                is_strategy = True
                break

        if not is_strategy:
            return

        self.has_strategy = True
        self.check_docstring(node)
        self.check_methods(node)

    def check_docstring(self, node):
        docstring = ast.get_docstring(node)

        if not docstring:
            if self.fix_mode:
                self.add_header(node)
            else:
                self.errors.append(f"Missing docstring in class {node.name}")
            return

        missing = []
        for section in REQUIRED_SECTIONS:
            if section not in docstring:
                missing.append(section)

        if missing:
            if self.fix_mode:
                 # If docstring exists but missing sections, we might append or replace.
                 # For simplicity in this task, if missing multiple, we append the template
                 # But ideally we should be smarter.
                 # Let's just append the template to the end if it looks significantly missing
                 self.append_header(node, docstring)
            else:
                self.errors.append(f"Missing header sections in class {node.name}: {', '.join(missing)}")

    def add_header(self, node):
        # We need to insert docstring.
        # This is hard to do with just AST visitation, we need to manipulate source.
        # We will mark it for fix.
        pass # Handle in main loop via string manipulation if possible, or here if we load source

    def append_header(self, node, existing_docstring):
        pass # logic handled in apply_fix

    def check_methods(self, node):
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name in ['populate_entry_trend', 'populate_exit_trend']:
                    self.check_trend_method(item)

    def check_trend_method(self, node):
        # Check for comments explaining logic (simple heuristic: function has comments?)
        # ast doesn't give comments easily. We rely on logic checks.

        for stmt in node.body:
            # check for assignments to dataframe.loc
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Subscript):
                        # dataframe.loc[...]
                        if isinstance(target.value, ast.Attribute) and target.value.attr == 'loc':
                            self.check_loc_assignment(target, stmt, node.name)

    def check_loc_assignment(self, target, stmt, method_name):
        # target.slice is the index.
        # format: dataframe.loc[ (condition), "column" ]
        # In python 3.9+, slice is usually a Tuple or ExtSlice?
        # Actually target.slice is the node inside [].

        slice_node = target.slice

        # Depending on python version, ast structure varies.
        # Assuming Tuple for [row_indexer, col_indexer]

        condition_node = None
        col_node = None

        if isinstance(slice_node, ast.Tuple):
            if len(slice_node.elts) == 2:
                condition_node = slice_node.elts[0]
                col_node = slice_node.elts[1]
        elif isinstance(slice_node, ast.Index): # Deprecated in 3.9
             if isinstance(slice_node.value, ast.Tuple):
                 if len(slice_node.value.elts) == 2:
                    condition_node = slice_node.value.elts[0]
                    col_node = slice_node.value.elts[1]

        if col_node and isinstance(col_node, ast.Constant) and col_node.value in ['enter_long', 'enter_short', 'exit_long', 'exit_short']:
            # We found the signal assignment.
            # Check condition_node.
            if not self.is_simple_condition(condition_node):
                self.errors.append(f"In {method_name}, assignment to '{col_node.value}' uses a complex condition. Use a named boolean variable instead.")

    def is_simple_condition(self, node):
        # Allow: Name, Attribute (df['col']), UnaryOp (specifically ~Name)
        if isinstance(node, ast.Name):
            return True
        if isinstance(node, ast.Attribute):
            return True # e.g. self.some_flag
        if isinstance(node, ast.Subscript):
             # dataframe['column']
             return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
             return self.is_simple_condition(node.operand)

        # Reject: BinOp (&, |), Call, BoolOp, Compare
        return False

def apply_fix(filepath, content):
    # Quick and dirty implementation to insert docstring if missing or incomplete
    # Parsing again to find insertion point
    tree = ast.parse(content)

    class Fixer(ast.NodeVisitor):
        def __init__(self):
            self.lines = content.splitlines()
            self.modified = False

        def visit_ClassDef(self, node):
            is_strategy = any(isinstance(b, ast.Name) and b.id == 'IStrategy' for b in node.bases)
            if not is_strategy:
                return

            docstring = ast.get_docstring(node)
            header = REQUIRED_HEADER_TEMPLATE.format(name=node.name)

            if not docstring:
                # Insert docstring after class definition line
                # We need to find the line number of the colon or start of body
                # simpler: insert at node.body[0].lineno - 1 if body exists
                indent = "    "
                new_doc = f'{indent}"""{header}{indent}"""'

                # Inserting at the beginning of the class body
                # node.lineno is class def start. node.body[0].lineno is first statement.
                insert_line = node.body[0].lineno - 1
                self.lines.insert(insert_line, new_doc)
                self.modified = True
            else:
                # Append to existing docstring?
                # This is tricky without messing up indentation.
                # For now, if "Strategy Name" is missing, we assume we need to inject the whole block
                if "Strategy Name" not in docstring:
                     # Replace docstring? Or prepend?
                     pass # Implementation complexity...
                     # Let's simplify: if docstring exists but invalid, we won't auto-fix perfectly in this script
                     # unless we replace the whole docstring.
                     # But let's just do the "Insert if missing" case robustly.
                     print(f"Docstring exists but is missing required fields in {node.name}. Auto-fix for existing docstring not fully implemented.")

    fixer = Fixer()
    fixer.visit(tree)
    if fixer.modified:
        return "\n".join(fixer.lines)
    return content


def audit_file(filepath, fix=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if fix:
        new_content = apply_fix(filepath, content)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Fixed header in {filepath}")
            # Re-read for validation
            content = new_content

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"Syntax Error in {filepath}: {e}")
        return False

    visitor = StrategyVisitor(filepath)
    visitor.source_code = content
    visitor.visit(tree)

    if visitor.errors:
        print(f"Errors in {filepath}:")
        for err in visitor.errors:
            print(f"  - {err}")
        return False

    if visitor.has_strategy:
        print(f"OK: {filepath}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Audit Freqtrade strategies.")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing headers")
    args = parser.parse_args()

    strategies_dir = "user_data/strategies"
    files = glob.glob(os.path.join(strategies_dir, "*.py"))

    success = True
    for fp in files:
        if fp.endswith("__init__.py") or "_base" in fp:
            continue
        if not audit_file(fp, fix=args.fix):
            success = False

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
