#!/usr/bin/env python3
"""AST-Based Import Updater."""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


class ImportUpdater(ast.NodeTransformer):
    """Update import statements."""
    
    def __init__(self, old: str, new: str):
        self.old = old
        self.new = new
        self.changes: List[Tuple[int, str, str]] = []
    
    def visit_Import(self, node: ast.Import) -> ast.Import:
        for alias in node.names:
            if alias.name.startswith(self.old):
                old_name = alias.name
                new_name = alias.name.replace(self.old, self.new, 1)
                alias.name = new_name
                self.changes.append((node.lineno, old_name, new_name))
        return node
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        if node.module and node.module.startswith(self.old):
            old_mod = node.module
            new_mod = node.module.replace(self.old, self.new, 1)
            node.module = new_mod
            self.changes.append((node.lineno, old_mod, new_mod))
        return node


def update_file(path: Path, old: str, new: str, dry_run: bool) -> int:
    """Update imports in file."""
    try:
        content = path.read_text()
        tree = ast.parse(content)
    except Exception as e:
        print(f"Error parsing {path}: {e}")
        return 0
    
    updater = ImportUpdater(old, new)
    new_tree = updater.visit(tree)
    
    if not updater.changes:
        return 0
    
    print(f"\n{path}:")
    for line, old_imp, new_imp in updater.changes:
        print(f"  Line {line}: {old_imp} → {new_imp}")
    
    if not dry_run:
        new_content = ast.unparse(new_tree)
        path.write_text(new_content)
        print(f"  ✓ Updated")
    
    return len(updater.changes)


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update imports")
    parser.add_argument("old_module", help="Old module path")
    parser.add_argument("new_module", help="New module path")
    parser.add_argument("--path", default=".", help="Root path")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    
    args = parser.parse_args()
    
    root = Path(args.path)
    files = list(root.rglob("*.py"))
    
    print(f"Searching {len(files)} files...")
    
    total = 0
    for filepath in files:
        total += update_file(filepath, args.old_module, args.new_module, args.dry_run)
    
    print(f"\nTotal changes: {total}")
    
    if args.dry_run and total > 0:
        print("\nRun without --dry-run to apply")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
