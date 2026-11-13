#!/usr/bin/env python3
"""
Gate 0a: Intelligent Placeholder Pattern Scanner
=================================================
Enterprise-grade scanner that understands architectural patterns.

Recognizes LEGITIMATE patterns:
- @abstractmethod with pass/ellipsis (Template Method Pattern)
- Protocol classes with ellipsis (Python typing pattern)
- pass in except/finally/else blocks (Error handling)
- TODO/FIXME comments (Acceptable - warnings not errors)

Detects REAL issues:
- Standalone pass statements without context
- Empty function bodies without decorators
- NotImplementedError without proper context
"""

import ast
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

# Paths to scan
CORE_PATHS = ['mahoun', 'output', 'api', 'config']

# Paths to exclude
EXCLUDE_PATTERNS = {
    '__pycache__',
    '.pytest_cache',
    'venv',
    'venv.old.conda',
    '.git',
    'node_modules',
    'dist',
    'build',
    '*.pyc',
    '/archive/',  # Archived code
    '/tests/',    # Test files
    'test_',      # Test files
}


class IssueCategory(str, Enum):
    """Issue categorization"""
    LEGITIMATE = "legitimate"      # Architectural pattern - ignore
    ACCEPTABLE = "acceptable"      # TODO/FIXME - warning only
    NEEDS_FIX = "needs_fix"       # Real placeholder - error


class IssueSeverity(int, Enum):
    """Issue severity levels"""
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


@dataclass
class Issue:
    """Detected issue with context"""
    file_path: Path
    line_num: int
    line_content: str
    description: str
    category: IssueCategory
    severity: IssueSeverity
    context: Optional[str] = None  # Additional context for understanding


class IntelligentScanner:
    """
    AST-based scanner that understands Python architectural patterns.
    """
    
    def __init__(self):
        self.issues: List[Issue] = []
        self.stats = {
            "files_scanned": 0,
            "legitimate": 0,
            "acceptable": 0,
            "needs_fix": 0,
        }
    
    def should_exclude_path(self, path: Path) -> bool:
        """Check if path should be excluded"""
        path_str = str(path)
        
        for pattern in EXCLUDE_PATTERNS:
            if pattern in path_str:
                return True
        
        return False
    
    def scan_file(self, file_path: Path) -> None:
        """Scan a single file using AST analysis"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Parse AST
            try:
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError:
                # Skip files with syntax errors (they'll be caught by other gates)
                return
            
            # Analyze AST
            self._analyze_ast(tree, file_path, lines)
            
            # Also do regex-based scanning for comments
            self._scan_comments(file_path, lines)
            
            self.stats["files_scanned"] += 1
            
        except Exception as e:
            print(f"{YELLOW}Warning: Could not scan {file_path}: {e}{NC}", file=sys.stderr)
    
    def _analyze_ast(self, tree: ast.AST, file_path: Path, lines: List[str]) -> None:
        """Analyze AST for placeholder patterns"""
        
        for node in ast.walk(tree):
            # Check function definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function(node, file_path, lines)
            
            # Check class definitions
            elif isinstance(node, ast.ClassDef):
                self._check_class(node, file_path, lines)
    
    def _check_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check function for placeholder patterns"""
        
        # Skip if no body
        if not node.body:
            return
        
        # Check if function has only pass or ellipsis
        if len(node.body) == 1:
            stmt = node.body[0]
            
            # Check for pass statement
            if isinstance(stmt, ast.Pass):
                self._check_pass_statement(node, file_path, lines)
            
            # Check for ellipsis
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                if stmt.value.value == Ellipsis:
                    self._check_ellipsis_statement(node, file_path, lines)
            
            # Check for NotImplementedError
            elif isinstance(stmt, ast.Raise):
                if isinstance(stmt.exc, ast.Call):
                    if isinstance(stmt.exc.func, ast.Name):
                        if stmt.exc.func.id == 'NotImplementedError':
                            self._check_not_implemented(node, file_path, lines)
        
        # Check for empty returns
        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                self._check_return_statement(stmt, node, file_path, lines)
    
    def _check_pass_statement(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check if pass statement is legitimate"""
        
        # Check for @abstractmethod decorator
        has_abstractmethod = any(
            (isinstance(d, ast.Name) and d.id == 'abstractmethod') or
            (isinstance(d, ast.Attribute) and d.attr == 'abstractmethod')
            for d in node.decorator_list
        )
        
        if has_abstractmethod:
            # LEGITIMATE: Abstract method with pass
            self._add_issue(
                file_path=file_path,
                line_num=node.lineno,
                line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                description="Abstract method with pass (Template Method Pattern)",
                category=IssueCategory.LEGITIMATE,
                severity=IssueSeverity.INFO,
                context="@abstractmethod decorator present"
            )
            return
        
        # Check if it's in an except/finally block
        # (This is harder with AST, so we'll check the line content)
        if node.lineno > 1:
            prev_lines = lines[max(0, node.lineno - 3):node.lineno - 1]
            prev_text = '\n'.join(prev_lines)
            
            if re.search(r'\b(except|finally|else)\b.*:', prev_text):
                # LEGITIMATE: pass in exception handler
                self._add_issue(
                    file_path=file_path,
                    line_num=node.lineno,
                    line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                    description="Pass in except/finally/else block (Error handling)",
                    category=IssueCategory.LEGITIMATE,
                    severity=IssueSeverity.INFO,
                    context="Exception handling pattern"
                )
                return
        
        # Check if function name suggests it's intentionally empty
        empty_patterns = ['noop', 'no_op', 'placeholder', 'stub', '_impl']
        if any(pattern in node.name.lower() for pattern in empty_patterns):
            # ACCEPTABLE: Intentionally empty function
            self._add_issue(
                file_path=file_path,
                line_num=node.lineno,
                line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                description=f"Function '{node.name}' with only pass (may be intentional stub)",
                category=IssueCategory.ACCEPTABLE,
                severity=IssueSeverity.WARNING,
                context="Function name suggests intentional placeholder"
            )
            return
        
        # NEEDS_FIX: Standalone pass without context
        self._add_issue(
            file_path=file_path,
            line_num=node.lineno,
            line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
            description=f"Function '{node.name}' has only pass statement (likely incomplete)",
            category=IssueCategory.NEEDS_FIX,
            severity=IssueSeverity.ERROR,
            context="No @abstractmethod decorator or exception handling context"
        )
    
    def _check_ellipsis_statement(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check if ellipsis is legitimate"""
        
        # Check for @abstractmethod decorator
        has_abstractmethod = any(
            (isinstance(d, ast.Name) and d.id == 'abstractmethod') or
            (isinstance(d, ast.Attribute) and d.attr == 'abstractmethod')
            for d in node.decorator_list
        )
        
        if has_abstractmethod:
            # LEGITIMATE: Abstract method with ellipsis
            self._add_issue(
                file_path=file_path,
                line_num=node.lineno,
                line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                description="Abstract method with ellipsis (Template Method Pattern)",
                category=IssueCategory.LEGITIMATE,
                severity=IssueSeverity.INFO,
                context="@abstractmethod decorator present"
            )
            return
        
        # NEEDS_FIX: Ellipsis without @abstractmethod
        self._add_issue(
            file_path=file_path,
            line_num=node.lineno,
            line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
            description=f"Function '{node.name}' has only ellipsis (likely placeholder)",
            category=IssueCategory.NEEDS_FIX,
            severity=IssueSeverity.ERROR,
            context="No @abstractmethod decorator"
        )
    
    def _check_class(
        self,
        node: ast.ClassDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check if class is a Protocol"""
        
        # Check if class inherits from Protocol
        is_protocol = any(
            (isinstance(base, ast.Name) and base.id == 'Protocol') or
            (isinstance(base, ast.Attribute) and base.attr == 'Protocol')
            for base in node.bases
        )
        
        if is_protocol:
            # Check methods in Protocol class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if len(item.body) == 1:
                        stmt = item.body[0]
                        
                        # Ellipsis in Protocol method is LEGITIMATE
                        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                            if stmt.value.value == Ellipsis:
                                self._add_issue(
                                    file_path=file_path,
                                    line_num=item.lineno,
                                    line_content=lines[item.lineno - 1] if item.lineno <= len(lines) else "",
                                    description=f"Protocol method '{item.name}' with ellipsis (Python typing pattern)",
                                    category=IssueCategory.LEGITIMATE,
                                    severity=IssueSeverity.INFO,
                                    context=f"Protocol class '{node.name}'"
                                )
    
    def _check_not_implemented(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check NotImplementedError usage"""
        
        # Check for @abstractmethod decorator
        has_abstractmethod = any(
            (isinstance(d, ast.Name) and d.id == 'abstractmethod') or
            (isinstance(d, ast.Attribute) and d.attr == 'abstractmethod')
            for d in node.decorator_list
        )
        
        if has_abstractmethod:
            # LEGITIMATE: Abstract method with NotImplementedError
            self._add_issue(
                file_path=file_path,
                line_num=node.lineno,
                line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                description="Abstract method with NotImplementedError",
                category=IssueCategory.LEGITIMATE,
                severity=IssueSeverity.INFO,
                context="@abstractmethod decorator present"
            )
            return
        
        # Check if NotImplementedError has a message
        raise_node = node.body[0]
        if isinstance(raise_node, ast.Raise) and isinstance(raise_node.exc, ast.Call):
            if raise_node.exc.args:
                # Has message - ACCEPTABLE
                self._add_issue(
                    file_path=file_path,
                    line_num=node.lineno,
                    line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                    description=f"Function '{node.name}' raises NotImplementedError with message",
                    category=IssueCategory.ACCEPTABLE,
                    severity=IssueSeverity.WARNING,
                    context="Has descriptive error message"
                )
                return
        
        # NEEDS_FIX: NotImplementedError without context
        self._add_issue(
            file_path=file_path,
            line_num=node.lineno,
            line_content=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
            description=f"Function '{node.name}' raises NotImplementedError without message",
            category=IssueCategory.NEEDS_FIX,
            severity=IssueSeverity.ERROR,
            context="No @abstractmethod decorator or error message"
        )
    
    def _check_return_statement(
        self,
        stmt: ast.Return,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        lines: List[str]
    ) -> None:
        """Check for suspicious return statements"""
        
        if stmt.value is None:
            # Bare return - usually fine
            return
        
        # Check for empty dict/list returns
        if isinstance(stmt.value, (ast.Dict, ast.List, ast.Tuple)):
            if not stmt.value.keys if isinstance(stmt.value, ast.Dict) else not stmt.value.elts:
                # Empty collection return - ACCEPTABLE (may be intentional)
                self._add_issue(
                    file_path=file_path,
                    line_num=stmt.lineno,
                    line_content=lines[stmt.lineno - 1] if stmt.lineno <= len(lines) else "",
                    description=f"Function '{func_node.name}' returns empty collection",
                    category=IssueCategory.ACCEPTABLE,
                    severity=IssueSeverity.WARNING,
                    context="May be intentional default return"
                )
    
    def _scan_comments(self, file_path: Path, lines: List[str]) -> None:
        """Scan for TODO/FIXME/HACK comments"""
        
        comment_patterns = [
            (r'#\s*TODO\b', 'TODO comment'),
            (r'#\s*FIXME\b', 'FIXME comment'),
            (r'#\s*XXX\b', 'XXX comment'),
            (r'#\s*HACK\b', 'HACK comment'),
        ]
        
        for line_num, line in enumerate(lines, start=1):
            for pattern, desc in comment_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # ACCEPTABLE: Comments are warnings, not errors
                    self._add_issue(
                        file_path=file_path,
                        line_num=line_num,
                        line_content=line.strip(),
                        description=desc,
                        category=IssueCategory.ACCEPTABLE,
                        severity=IssueSeverity.WARNING,
                        context="Technical debt marker"
                    )
    
    def _add_issue(
        self,
        file_path: Path,
        line_num: int,
        line_content: str,
        description: str,
        category: IssueCategory,
        severity: IssueSeverity,
        context: Optional[str] = None
    ) -> None:
        """Add an issue to the list"""
        issue = Issue(
            file_path=file_path,
            line_num=line_num,
            line_content=line_content,
            description=description,
            category=category,
            severity=severity,
            context=context
        )
        self.issues.append(issue)
        self.stats[category.value] += 1
    
    def scan_directory(self, base_path: Path, scan_paths: List[str]) -> None:
        """Scan directories"""
        for scan_path in scan_paths:
            path = base_path / scan_path
            if not path.exists():
                continue
            
            for py_file in path.rglob('*.py'):
                if self.should_exclude_path(py_file):
                    continue
                
                self.scan_file(py_file)
    
    def print_results(self, verbose: bool = False, show_legitimate: bool = False) -> None:
        """Print scan results"""
        
        # Group issues by category
        by_category: Dict[IssueCategory, List[Issue]] = {
            IssueCategory.LEGITIMATE: [],
            IssueCategory.ACCEPTABLE: [],
            IssueCategory.NEEDS_FIX: [],
        }
        
        for issue in self.issues:
            by_category[issue.category].append(issue)
        
        # Print NEEDS_FIX (errors)
        if by_category[IssueCategory.NEEDS_FIX]:
            print(f"\n{RED}{'='*60}{NC}")
            print(f"{RED}❌ ISSUES THAT NEED FIXING ({len(by_category[IssueCategory.NEEDS_FIX])}){NC}")
            print(f"{RED}{'='*60}{NC}\n")
            
            for issue in sorted(by_category[IssueCategory.NEEDS_FIX], key=lambda x: (str(x.file_path), x.line_num)):
                rel_path = issue.file_path.relative_to(Path.cwd())
                print(f"{rel_path}:{issue.line_num}")
                print(f"  {RED}ERROR{NC}: {issue.description}")
                print(f"  {issue.line_content.strip()}")
                if issue.context:
                    print(f"  Context: {issue.context}")
                print()
        
        # Print ACCEPTABLE (warnings)
        if verbose and by_category[IssueCategory.ACCEPTABLE]:
            print(f"\n{YELLOW}{'='*60}{NC}")
            print(f"{YELLOW}⚠️  ACCEPTABLE ISSUES ({len(by_category[IssueCategory.ACCEPTABLE])}){NC}")
            print(f"{YELLOW}{'='*60}{NC}\n")
            
            for issue in sorted(by_category[IssueCategory.ACCEPTABLE], key=lambda x: (str(x.file_path), x.line_num)):
                rel_path = issue.file_path.relative_to(Path.cwd())
                print(f"{rel_path}:{issue.line_num}")
                print(f"  {YELLOW}WARNING{NC}: {issue.description}")
                print(f"  {issue.line_content.strip()}")
                if issue.context:
                    print(f"  Context: {issue.context}")
                print()
        
        # Print LEGITIMATE (info)
        if show_legitimate and by_category[IssueCategory.LEGITIMATE]:
            print(f"\n{BLUE}{'='*60}{NC}")
            print(f"{BLUE}✓ LEGITIMATE PATTERNS ({len(by_category[IssueCategory.LEGITIMATE])}){NC}")
            print(f"{BLUE}{'='*60}{NC}\n")
            
            for issue in sorted(by_category[IssueCategory.LEGITIMATE], key=lambda x: (str(x.file_path), x.line_num)):
                rel_path = issue.file_path.relative_to(Path.cwd())
                print(f"{rel_path}:{issue.line_num}")
                print(f"  {BLUE}INFO{NC}: {issue.description}")
                if issue.context:
                    print(f"  Context: {issue.context}")
                print()
    
    def print_summary(self) -> int:
        """Print summary and return exit code"""
        print(f"\n{'='*60}")
        print("📊 SCAN SUMMARY")
        print(f"{'='*60}\n")
        
        print(f"Files scanned: {self.stats['files_scanned']}")
        print(f"Total issues found: {len(self.issues)}\n")
        
        print(f"{BLUE}✓ Legitimate patterns:{NC} {self.stats['legitimate']}")
        print(f"  (Abstract methods, Protocols, Exception handling)")
        print()
        
        print(f"{YELLOW}⚠️  Acceptable issues:{NC} {self.stats['acceptable']}")
        print(f"  (TODO/FIXME comments, intentional stubs)")
        print()
        
        print(f"{RED}❌ Issues needing fixes:{NC} {self.stats['needs_fix']}")
        print(f"  (Incomplete implementations, missing context)")
        print()
        
        # Determine exit code
        if self.stats['needs_fix'] > 0:
            print(f"{RED}❌ FAILED: {self.stats['needs_fix']} issues need fixing{NC}\n")
            return 1
        elif self.stats['acceptable'] > 0:
            print(f"{YELLOW}⚠️  WARNING: {self.stats['acceptable']} acceptable issues found{NC}")
            print(f"{GREEN}✅ PASSED: No critical issues{NC}\n")
            return 0
        else:
            print(f"{GREEN}✅ PASSED: No placeholder issues detected{NC}\n")
            return 0


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Intelligent placeholder pattern scanner with architectural awareness'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show acceptable issues (warnings)'
    )
    parser.add_argument(
        '--show-legitimate',
        action='store_true',
        help='Show legitimate patterns (for verification)'
    )
    parser.add_argument(
        '--fail-on-warning',
        action='store_true',
        help='Exit with error code even for warnings'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 Gate 0a: Intelligent Placeholder Scanner")
    print("=" * 60)
    print()
    print("Recognizes architectural patterns:")
    print("  • @abstractmethod (Template Method Pattern)")
    print("  • Protocol classes (Python typing)")
    print("  • Exception handling (pass in except/finally)")
    print("  • TODO/FIXME comments (warnings only)")
    print()
    
    # Scan
    scanner = IntelligentScanner()
    scanner.scan_directory(Path.cwd(), CORE_PATHS)
    
    # Print results
    scanner.print_results(
        verbose=args.verbose,
        show_legitimate=args.show_legitimate
    )
    
    # Print summary and get exit code
    exit_code = scanner.print_summary()
    
    # Override exit code if --fail-on-warning
    if args.fail_on_warning and scanner.stats['acceptable'] > 0:
        print(f"{RED}❌ FAILED: --fail-on-warning set and warnings found{NC}\n")
        return 1
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
