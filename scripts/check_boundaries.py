#!/usr/bin/env python3
"""
Architecture Boundary Checker
==============================
Detects boundary violations where core modules import from non-core modules.

This script enforces the architectural rule:
    Core modules MUST NOT import from non-core modules.

Usage:
    python scripts/check_boundaries.py
    
Exit codes:
    0 - No violations found
    1 - Violations found
    2 - Error (missing manifests, etc.)
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
import yaml


class BoundaryViolation:
    """Represents a single boundary violation."""
    
    def __init__(
        self,
        file_path: str,
        line_number: int,
        core_module: str,
        imported_module: str,
        import_statement: str
    ):
        self.file_path = file_path
        self.line_number = line_number
        self.core_module = core_module
        self.imported_module = imported_module
        self.import_statement = import_statement
    
    def __str__(self) -> str:
        return (
            f"  {self.file_path}:{self.line_number}\n"
            f"    Core module '{self.core_module}' imports from non-core '{self.imported_module}'\n"
            f"    Statement: {self.import_statement}"
        )


class BoundaryChecker:
    """Checks for architectural boundary violations."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.core_modules: Set[str] = set()
        self.non_core_modules: Set[str] = set()
        self.violations: List[BoundaryViolation] = []
    
    def load_manifests(self) -> bool:
        """Load core and non-core manifests."""
        core_manifest_path = self.project_root / "core_manifest.yaml"
        non_core_manifest_path = self.project_root / "non_core_manifest.yaml"
        
        if not core_manifest_path.exists():
            print(f"❌ ERROR: core_manifest.yaml not found at {core_manifest_path}")
            return False
        
        if not non_core_manifest_path.exists():
            print(f"❌ ERROR: non_core_manifest.yaml not found at {non_core_manifest_path}")
            return False
        
        # Load core modules
        with open(core_manifest_path, 'r') as f:
            core_manifest = yaml.safe_load(f)
            for module_name in core_manifest.get('core_modules', {}).keys():
                self.core_modules.add(module_name)
        
        # Load non-core modules
        with open(non_core_manifest_path, 'r') as f:
            non_core_manifest = yaml.safe_load(f)
            for category in non_core_manifest.get('non_core_modules', {}).values():
                if isinstance(category, dict):
                    for module_name in category.keys():
                        self.non_core_modules.add(module_name)
        
        print(f"✅ Loaded {len(self.core_modules)} core modules: {sorted(self.core_modules)}")
        print(f"✅ Loaded {len(self.non_core_modules)} non-core modules")
        return True
    
    def extract_imports(self, file_path: Path) -> List[Tuple[int, str, str]]:
        """
        Extract import statements from a Python file.
        
        Returns:
            List of (line_number, module_name, import_statement) tuples
        """
        imports = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        import_stmt = f"import {alias.name}"
                        imports.append((node.lineno, module_name, import_stmt))
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split('.')[0]
                        names = ', '.join(alias.name for alias in node.names)
                        import_stmt = f"from {node.module} import {names}"
                        imports.append((node.lineno, module_name, import_stmt))
        
        except SyntaxError as e:
            print(f"⚠️  WARNING: Syntax error in {file_path}: {e}")
        except Exception as e:
            print(f"⚠️  WARNING: Error parsing {file_path}: {e}")
        
        return imports
    
    def check_file(self, file_path: Path, core_module: str) -> None:
        """Check a single file for boundary violations."""
        # Skip adapter files - they are explicitly designed for runtime imports
        if file_path.name.endswith('_adapter.py'):
            return
        
        imports = self.extract_imports(file_path)
        
        for line_number, imported_module, import_statement in imports:
            # Skip if not importing from mahoun
            if imported_module != 'mahoun':
                continue
            
            # Extract the actual module name from the import
            # e.g., "from mahoun.agents import X" -> "agents"
            parts = import_statement.split()
            if 'from' in parts:
                from_idx = parts.index('from')
                if from_idx + 1 < len(parts):
                    full_module = parts[from_idx + 1]
                    if full_module.startswith('mahoun.'):
                        actual_module = full_module.split('.')[1]
                        
                        # Check if importing from non-core
                        if actual_module in self.non_core_modules:
                            violation = BoundaryViolation(
                                file_path=str(file_path.relative_to(self.project_root)),
                                line_number=line_number,
                                core_module=core_module,
                                imported_module=actual_module,
                                import_statement=import_statement
                            )
                            self.violations.append(violation)
    
    def check_core_module(self, module_name: str) -> None:
        """Check all Python files in a core module."""
        module_path = self.project_root / "mahoun" / module_name
        
        if not module_path.exists():
            print(f"⚠️  WARNING: Core module path not found: {module_path}")
            return
        
        # Find all Python files
        python_files = list(module_path.rglob("*.py"))
        
        for py_file in python_files:
            # Skip __pycache__ and other generated files
            if '__pycache__' in str(py_file):
                continue
            
            self.check_file(py_file, module_name)
    
    def run(self) -> int:
        """
        Run the boundary checker.
        
        Returns:
            Exit code (0 = success, 1 = violations found, 2 = error)
        """
        print("=" * 80)
        print("Architecture Boundary Checker")
        print("=" * 80)
        print()
        
        # Load manifests
        if not self.load_manifests():
            return 2
        
        print()
        print("🔍 Scanning core modules for boundary violations...")
        print()
        
        # Check each core module
        for core_module in sorted(self.core_modules):
            print(f"  Checking {core_module}...", end=" ")
            initial_count = len(self.violations)
            self.check_core_module(core_module)
            new_violations = len(self.violations) - initial_count
            
            if new_violations > 0:
                print(f"❌ {new_violations} violation(s) found")
            else:
                print("✅ Clean")
        
        print()
        print("=" * 80)
        
        # Report results
        if self.violations:
            print(f"❌ BOUNDARY VIOLATIONS FOUND: {len(self.violations)}")
            print("=" * 80)
            print()
            
            # Group violations by core module
            violations_by_module: Dict[str, List[BoundaryViolation]] = {}
            for violation in self.violations:
                if violation.core_module not in violations_by_module:
                    violations_by_module[violation.core_module] = []
                violations_by_module[violation.core_module].append(violation)
            
            # Print violations grouped by module
            for core_module in sorted(violations_by_module.keys()):
                module_violations = violations_by_module[core_module]
                print(f"Core Module: {core_module} ({len(module_violations)} violation(s))")
                print("-" * 80)
                for violation in module_violations:
                    print(violation)
                    print()
            
            print("=" * 80)
            print()
            print("💡 How to fix:")
            print("  1. Use dependency injection with protocols (see core_manifest.yaml)")
            print("  2. Move the importing code to a non-core adapter module")
            print("  3. Refactor to remove the dependency")
            print()
            print("📖 See ARCHITECTURE_CRISIS_ANALYSIS.md for detailed guidance")
            print()
            
            return 1
        else:
            print("✅ NO BOUNDARY VIOLATIONS FOUND")
            print("=" * 80)
            print()
            print("🎉 All core modules respect architectural boundaries!")
            print()
            return 0


def main() -> int:
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    checker = BoundaryChecker(project_root)
    return checker.run()


if __name__ == "__main__":
    sys.exit(main())
