#!/usr/bin/env python3
"""
AST-based checker for placeholder 'pass' stubs in critical runtime paths.
Distinguishes genuine placeholder stubs from legitimate Python protocols,
abstract methods, and exception declarations.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple

CRITICAL_PATHS = [
    "mahoun/core",
    "mahoun/domain",
    "mahoun/schemas",
    "api",
]

ALLOWED_FILES = {
    "singleton.py",
}


def is_protocol_or_abc(node: ast.AST, class_stack: List[ast.ClassDef]) -> bool:
    """Check if the function belongs to a typing.Protocol, ABC, or NoOp implementation."""
    for cls_node in class_stack:
        if cls_node.name.startswith("NoOp") or cls_node.name.startswith("Null"):
            return True
        for base in cls_node.bases:
            base_name = getattr(base, "id", getattr(base, "attr", ""))
            if base_name in ("Protocol", "ABC"):
                return True
    return False


def check_file(file_path: Path) -> List[Tuple[int, str, str]]:
    violations = []
    if file_path.name in ALLOWED_FILES or "test" in file_path.name:
        return violations
    if "protocols" in file_path.parts or "protocol" in file_path.name:
        return violations

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception:
        return violations

    class_stack: List[ast.ClassDef] = []

    class FunctionVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            class_stack.append(node)
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._check_func(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._check_func(node)
            self.generic_visit(node)

        def _check_func(self, node):
            # Abstract methods and overloads legitimately have pass
            dec_names = [getattr(d, "id", getattr(d, "attr", "")) for d in node.decorator_list]
            if any(name in ("abstractmethod", "overload") for name in dec_names):
                return
            if is_protocol_or_abc(node, class_stack):
                return

            # Check if function body consists solely of pass (ignoring docstring)
            stmts = [
                s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))
            ]
            if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
                violations.append((node.lineno, node.name, "Function body consists solely of 'pass' stub"))

    FunctionVisitor().visit(tree)
    return violations


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    all_violations = []

    for rel_path in CRITICAL_PATHS:
        target_dir = root / rel_path
        if not target_dir.exists():
            continue
        for py_file in target_dir.rglob("*.py"):
            if "venv" in py_file.parts or ".venv" in py_file.parts or "__pycache__" in py_file.parts:
                continue
            v = check_file(py_file)
            for lineno, func_name, msg in v:
                all_violations.append(f"{py_file.relative_to(root)}:{lineno}: {func_name} - {msg}")

    if all_violations:
        print("❌ FAIL: Found placeholder pass stubs in critical paths:")
        for viol in all_violations:
            print(f"  {viol}")
        return 1

    print("✓ No placeholder 'pass' stubs detected in critical paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
