#!/usr/bin/env python3
"""
Neo4j Governance Compliance Validator
====================================
Comprehensive validation of governance architecture compliance.

Checks:
1. MutationAuthorizationBoundary.inspect() call locations
2. _raw_executor usage patterns
3. _authorized_write_ctx management
4. Direct driver creation violations
5. Raw session usage bypasses

Usage:
    python scripts/validate_governance_compliance.py
"""

import os
import re
import sys
import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum


class ViolationSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM" 
    LOW = "LOW"


@dataclass
class GovernanceViolation:
    file_path: str
    line_number: int
    severity: ViolationSeverity
    category: str
    description: str
    code_snippet: str


class GovernanceValidator:
    """Validates Neo4j governance architecture compliance"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.violations: List[GovernanceViolation] = []
        self._source_files: Optional[List[Path]] = None
        self._source_contents: Dict[str, str] = {}
        
        # Allowlist for direct Neo4j access
        self.neo4j_allowlist = {
            "mahoun/graph/neo4j/connection.py",
            "mahoun/graph/neo4j/schema.py", 
            "api/database.py",  # Now governance-compliant
        }
        
        # Test patterns (more lenient)
        self.test_patterns = {
            "tests/",
            "test_",
            "/fixtures/",
        }
        
        # Exclude patterns (ignore these completely)
        self.exclude_patterns = {
            "venv/",
            ".venv/",
            "venv_test/",      # Temporary test venv created by agents (untracked)
            "__pycache__/",
            ".git/",
            "node_modules/",
            ".pytest_cache/",
            "/examples/",  # Example files don't enforce governance
            "archived_modules/",  # Archived historical examples
            "ci/enforcement/",  # Static AST scanners that contain regex patterns
            "ci/gates/",  # CI gates
            ".kilo/worktrees/",  # Agent Manager worktree copies (legacy path)
            ".worktrees/",  # git worktree copies (current path)
            ".test_classification_backup/",  # Backup directories
            "data/",  # Runtime databases and generated corpus artifacts
            "datasets/",  # External datasets are not source code
            "training_data/",  # Generated/training artifacts are not source code
            "test_data/",  # Test fixtures are validated by their own suites
            ".kilo/",  # Agent workspace artifacts
            ".mypy_cache/",  # Type-checker cache
            "htmlcov/",  # Generated coverage output
            "logs/",  # Runtime logs
            "models/",  # Model artifacts
            "artifacts/",  # Generated evidence artifacts
            "reports/",  # Generated reports
            "architecture_reports/",  # Generated architecture reports
        }
    
    def validate_all(self) -> bool:
        """Run all governance validation checks"""
        print("🛡️  MAHOUN Governance Compliance Validation")
        print("=" * 50)
        
        self._check_mutation_boundary_usage()
        self._check_direct_driver_creation_ast()  # NEW: AST-based (more accurate)
        self._check_duplicate_cypher_classifier()  # NEW: Detect classifier duplicates
        self._check_raw_session_usage()
        self._check_governed_session_scope()  # NEW: Per-call scope analysis
        self._check_authorized_context_usage()
        self._check_mutation_bypasses()
        self._check_authorization_contextvar_singleton()

        return self._report_results()
    
    def _check_mutation_boundary_usage(self):
        """Verify MutationAuthorizationBoundary.inspect() is called correctly"""
        print("🔍 Checking MutationAuthorizationBoundary.inspect() usage...")
        
        inspect_calls = self._find_pattern(
            r'MutationAuthorizationBoundary\.inspect\(',
            include_patterns=['*.py']
        )
        
        if not inspect_calls:
            self.violations.append(GovernanceViolation(
                file_path="ARCHITECTURE",
                line_number=0,
                severity=ViolationSeverity.CRITICAL,
                category="MISSING_BOUNDARY",
                description="No MutationAuthorizationBoundary.inspect() calls found",
                code_snippet=""
            ))
        
        # Verify it's called in the right place (connection.py)
        connection_calls = [c for c in inspect_calls if 'connection.py' in c[0]]
        if not connection_calls:
            self.violations.append(GovernanceViolation(
                file_path="mahoun/graph/neo4j/connection.py",
                line_number=0,
                severity=ViolationSeverity.CRITICAL,
                category="MISSING_CHOKEPOINT",
                description="MutationAuthorizationBoundary.inspect() not called in connection chokepoint",
                code_snippet=""
            ))
    
    def _check_authorization_contextvar_singleton(self):
        """Verify the mutation-authorization ContextVar has exactly ONE definition.

        The canonical ContextVar lives in
        ``mahoun/core/governance_kernel/authorization_state.py`` and is re-exported
        through the shim ``mahoun/core/governance/authorization_state.py``. Any
        other ``.py`` file that creates a fresh ``ContextVar`` bound to the name
        ``_authorized_write_ctx`` reintroduces a split-brain bug — writing one
        var does not release the boundary enforced by the other.
        """
        print("🔍 Checking authorization ContextVar singleton...")

        # Files ALLOWED to assign (define) _authorized_write_ctx as a ContextVar.
        canonical_files = {
            "mahoun/core/governance_kernel/authorization_state.py",
        }
        # Files ALLOWED to import / re-export but NOT to construct a new ContextVar.
        allowlisted_reexport = {
            "mahoun/core/governance/authorization_state.py",
        }

        # Match: NAME = ContextVar(  or  NAME : ContextVar[...] = ContextVar(
        pattern = (
            r'_authorized_write_ctx\s*(?::\s*ContextVar[^=]*)?\s*=\s*'
            r'contextvars\.ContextVar\('
        )
        matches = self._find_pattern(pattern, include_patterns=['*.py'])

        for file_path, line_num, line_content in matches:
            rel = file_path.replace('\\', '/')
            if rel in canonical_files:
                continue
            if rel in allowlisted_reexport:
                # The shim must re-export only; a bare construction here would
                # itself be a redefinition (no construction expected).
                self.violations.append(GovernanceViolation(
                    file_path=file_path,
                    line_number=line_num,
                    severity=ViolationSeverity.CRITICAL,
                    category="DUPLICATE_AUTH_CONTEXTVAR",
                    description=(
                        "_authorized_write_ctx constructed outside the "
                        "canonical module governance_kernel/authorization_state.py"
                    ),
                    code_snippet=line_content.strip(),
                ))
                continue
            self.violations.append(GovernanceViolation(
                file_path=file_path,
                line_number=line_num,
                severity=ViolationSeverity.CRITICAL,
                category="DUPLICATE_AUTH_CONTEXTVAR",
                description=(
                    "Duplicate _authorized_write_ctx ContextVar construction. "
                    "Import the canonical from mahoun.core.governance_kernel."
                    "authorization_state instead."
                ),
                code_snippet=line_content.strip(),
            ))

    def _check_direct_driver_creation_ast(self):
        """
        Use AST parsing for precise driver creation detection.
        Comments and strings do not count as executable driver creation.
        """
        print("🚫 Checking direct Neo4j driver creation (AST-based)...")
        
        forbidden_calls = [
            ("GraphDatabase", "driver"),
            ("AsyncGraphDatabase", "driver"),
        ]
        
        allowlisted_seed_fixture = "tests/fixtures/seed_data.py"
        for file_path in self._python_source_files():
            rel_path = file_path.relative_to(self.repo_root).as_posix()
            if rel_path in self.neo4j_allowlist:
                continue

            is_test = any(test_pattern in rel_path for test_pattern in self.test_patterns)
            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(file_path))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue

            lines = content.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if not isinstance(node.func.value, ast.Name):
                    continue

                class_name = node.func.value.id
                method_name = node.func.attr
                if (class_name, method_name) not in forbidden_calls:
                    continue

                if (
                    rel_path == allowlisted_seed_fixture
                    and self._seed_driver_call_is_gated(tree, node)
                ):
                    continue

                line_content = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                severity = ViolationSeverity.HIGH if is_test else ViolationSeverity.CRITICAL
                category = "TEST_MISSING_GUARD" if is_test else "DIRECT_DRIVER_CREATION"
                self.violations.append(GovernanceViolation(
                    file_path=rel_path,
                    line_number=node.lineno,
                    severity=severity,
                    category=category,
                    description=f"FORBIDDEN: {class_name}.{method_name}() detected by AST",
                    code_snippet=line_content.strip(),
                ))

    def _python_source_files(self) -> List[Path]:
        """Return repository Python sources excluding configured generated trees."""
        if self._source_files is None:
            self._source_files = [
                path
                for path in self.repo_root.rglob("*.py")
                if not self._should_exclude_file(
                    path.relative_to(self.repo_root).as_posix()
                )
            ]
        return self._source_files

    @staticmethod
    def _seed_driver_call_is_gated(tree: ast.Module, driver_call: ast.Call) -> bool:
        """Allow the test seeder's driver only when its entrypoint checks both gates."""
        seed_function = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "seed_neo4j_knowledge_graph"
            ),
            None,
        )
        if seed_function is None:
            return False

        gate_calls = [
            node
            for node in ast.walk(seed_function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "enforce_governance_gates"
        ]
        return any(gate.lineno < driver_call.lineno for gate in gate_calls)
    
    def _check_governed_session_scope(self):
        """
        Verify that raw .session() calls are inside governed scope.
        
        Per AGENTS.md 1-B: "Neo4jConnection._raw_execute() is the ONLY method 
        permitted to execute Cypher. It invokes MutationAuthorizationBoundary.inspect()"
        
        This check verifies .session() calls are wrapped in governed context.
        """
        print("🔐 Checking governed session scope (per-call analysis)...")
        
        for root, dirs, files in os.walk(self.repo_root / "mahoun"):
            dirs[:] = [d for d in dirs if d not in {'__pycache__', '.pytest_cache'}]
            
            for file in files:
                if not file.endswith(".py"):
                    continue
                
                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(self.repo_root))
                
                # Skip canonical connection.py and validation script itself
                if "connection.py" in rel_path or "validate_governance_compliance.py" in rel_path:
                    continue
                
                # Skip test files
                if any(test_pattern in rel_path for test_pattern in self.test_patterns):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                except (UnicodeDecodeError, OSError):
                    continue
                
                lines = content.split('\n')
                
                # Find .session() calls
                for i, line in enumerate(lines, 1):
                    # Skip comments and docstrings
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('*') or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    
                    if re.search(r'\.session\s*\(', line) and 'driver' in line.lower():
                        # Check if inside GovernedNeo4jSession context in surrounding lines
                        context_start = max(0, i - 20)
                        context_end = min(len(lines), i + 10)
                        context = '\n'.join(lines[context_start:context_end])
                        
                        # Look for governed patterns
                        governed_patterns = [
                            r'GovernedNeo4jSession',
                            r'governed_session\(',
                            r'with.*authorized_write',
                            r'@authorized',
                        ]
                        
                        has_governance = any(re.search(p, context, re.IGNORECASE) for p in governed_patterns)
                        
                        if not has_governance:
                            self.violations.append(GovernanceViolation(
                                file_path=rel_path,
                                line_number=i,
                                severity=ViolationSeverity.HIGH,
                                category="UNGOVERNED_SESSION_CALL",
                                description=(
                                    "UNGOVERNED SESSION: .session() call without governed scope\n"
                                    "      Must be inside GovernedNeo4jSession or governed_session() context"
                                ),
                                code_snippet=line.strip()
                            ))
    
    def _check_raw_session_usage(self):
        """Check for raw session usage bypassing governance"""
        print("🔍 Checking raw session usage...")
        
        raw_session_pattern = r'\.session\(\)'
        matches = self._find_pattern(raw_session_pattern, include_patterns=['*.py'])
        
        for file_path, line_num, line_content in matches:
            # Skip if it's governed_session, comments, or in tests
            if ('governed_session' in line_content or 
                line_content.strip().startswith('#') or
                line_content.strip().startswith('*') or
                line_content.strip().startswith('//') or
                '"""' in line_content or
                "'" in line_content and line_content.count("'") >= 2):
                continue
            if any(test_pattern in file_path for test_pattern in self.test_patterns):
                continue
            
            # Check context - should use governed patterns
            file_content = self._read_file_content(file_path)
            if 'GovernedNeo4jSession' not in file_content and 'governed_session' not in file_content:
                self.violations.append(GovernanceViolation(
                    file_path=file_path,
                    line_number=line_num,
                    severity=ViolationSeverity.MEDIUM,
                    category="RAW_SESSION_USAGE",
                    description="Raw session usage without governance context",
                    code_snippet=line_content.strip()
                ))
    
    def _check_authorized_context_usage(self):
        """Check _authorized_write_ctx usage patterns"""
        print("🔐 Checking _authorized_write_ctx usage...")
        
        ctx_pattern = r'_authorized_write_ctx'
        matches = self._find_pattern(ctx_pattern, include_patterns=['*.py'])
        
        # Should be used in authorization_state.py (canonical location)
        expected_files = {
            'authorization_state.py',
        }
        
        # Also acceptable in kernel.py if it imports from authorization_state
        acceptable_files = {
            'authorization_state.py',
            'kernel.py',
            'mutation_boundary.py',
        }
        
        found_files = set()
        for file_path, line_num, line_content in matches:
            # Skip test files
            if any(test_pattern in file_path for test_pattern in self.test_patterns):
                continue
            found_files.add(Path(file_path).name)
        
        # Check that authorization_state.py exists and uses it
        if 'authorization_state.py' not in found_files:
            self.violations.append(GovernanceViolation(
                file_path="*authorization_state.py",
                line_number=0,
                severity=ViolationSeverity.HIGH,
                category="MISSING_CONTEXT_USAGE",
                description=f"_authorized_write_ctx not found in authorization_state.py (canonical location)",
                code_snippet=""
            ))
    
    def _is_cypher_mutation(self, file_path: str, line_content: str) -> bool:
        """Check if a line contains a Cypher mutation (not SQL or enum value)"""
        # Must be in a string
        if '"' not in line_content and "'" not in line_content:
            return False
        
        # Skip enum definitions
        if '= "' in line_content or "= '" in line_content:
            # Likely an enum value like: DELETE = "delete"
            return False
            
        # Check if file uses Neo4j (not PostgreSQL/Redis/other DBs)
        file_content = self._read_file_content(file_path)
        
        # SQL indicators (PostgreSQL, MySQL, etc.)
        sql_indicators = ['asyncpg', 'psycopg', 'sqlalchemy', 'DELETE FROM', 'SELECT FROM']
        if any(indicator in file_content for indicator in sql_indicators):
            return False
            
        # Neo4j indicators
        neo4j_indicators = ['neo4j', 'cypher', 'GraphDatabase', 'governed_session']
        return any(indicator in file_content for indicator in neo4j_indicators)
    
    def _is_test_assertion(self, file_path: str, line_num: int, line_content: str) -> bool:
        """Check if a line is inside a test assertion (false positive)"""
        # Check if in test file
        if not any(pattern in file_path for pattern in ['test_', 'tests/']):
            return False
            
        # Check for assertion context
        assertion_keywords = ['assert ', 'pytest', '@pytest', 'def test_', 'class Test']
        file_content = self._read_file_content(file_path)
        lines = file_content.split('\n')
        
        # Check if line is too close to start/end
        if line_num < 1 or line_num > len(lines):
            return False
        
        # Check surrounding lines (±5 lines) for assertion context
        start = max(0, line_num - 6)
        end = min(len(lines), line_num + 5)
        context = '\n'.join(lines[start:end])
        
        # If any assertion keyword is in context, it's likely a test assertion
        if any(keyword in context for keyword in assertion_keywords):
            return True
        
        # Check if line is inside a string literal (test data)
        line = lines[line_num - 1] if line_num - 1 < len(lines) else ""
        # Multi-line string or write_text call
        if '.write_text(' in context or '"""' in context or "'''" in context:
            return True
        
        # Pattern inventory (test data structures)
        if 'VIOLATION_INVENTORY' in context or '# (module_path, pattern, description)' in context:
            return True
            
        return False
    
    def _check_duplicate_cypher_classifier(self):
        """
        Verify there is one mutation classifier implementation.
        
        Per AGENTS.md Part 1-B: "There must be exactly one _authorized_write_ctx 
        object and exactly one Cypher classification function in the entire process."
        
        Canonical: mahoun/core/governance/mutation_boundary.py::classify_cypher()

        classify_query compatibility wrappers are permitted only when their
        body delegates directly; protocol declarations are not implementations.
        """
        print("🔍 Checking for duplicate Cypher classifiers...")
        classifier_implementations: List[Tuple[str, int, str]] = []
        classify_cypher_defs: List[Tuple[str, int, str]] = []
        classifier_classes: List[Tuple[str, int, str]] = []

        for path in self._python_source_files():
            rel_path = path.relative_to(self.repo_root).as_posix()
            if any(test_pattern in rel_path for test_pattern in self.test_patterns):
                continue

            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == "classify_cypher":
                        classify_cypher_defs.append(
                            (rel_path, node.lineno, ast.get_source_segment(source, node) or "")
                        )
                    elif node.name == "classify_query" and not self._is_classifier_wrapper(node):
                        classifier_implementations.append(
                            (rel_path, node.lineno, ast.get_source_segment(source, node) or "")
                        )
                elif isinstance(node, ast.ClassDef) and node.name in {
                    "CypherClassifier",
                    "QueryClassifier",
                }:
                    classifier_classes.append(
                        (rel_path, node.lineno, ast.get_source_segment(source, node) or "")
                    )

        canonical = "mahoun/core/governance/mutation_boundary.py"
        if len(classify_cypher_defs) != 1 or classify_cypher_defs[0][0] != canonical:
            locations = classify_cypher_defs or [("MULTIPLE", 0, "")]
            self._record_duplicate_classifier("classify_cypher", locations, canonical)

        for name, locations in (
            ("classify_query implementation", classifier_implementations),
            ("classifier class", classifier_classes),
        ):
            if len(locations) > 1:
                self._record_duplicate_classifier(name, locations, canonical)

    @staticmethod
    def _is_classifier_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Return whether a classify_query definition only delegates its input."""
        statements = [
            statement
            for statement in node.body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
            and not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        if len(statements) != 1 or not isinstance(statements[0], ast.Return):
            return False

        value = statements[0].value
        if not isinstance(value, ast.Call) or len(value.args) != 1 or value.keywords:
            return False
        arg = value.args[0]
        return (
            isinstance(arg, ast.Name)
            and bool(node.args.args)
            and arg.id == node.args.args[0].arg
        )

    def _record_duplicate_classifier(
        self,
        name: str,
        locations: List[Tuple[str, int, str]],
        canonical: str,
    ) -> None:
        location_list = "\n      ".join(
            f"{file_path}:{line_number}"
            for file_path, line_number, _ in locations
        )
        self.violations.append(GovernanceViolation(
            file_path="MULTIPLE",
            line_number=0,
            severity=ViolationSeverity.CRITICAL,
            category="DUPLICATE_CYPHER_CLASSIFIER",
            description=(
                f"Multiple {name} implementations found:\n      {location_list}\n"
                f"      Mutation-classification boundary: {canonical}"
            ),
            code_snippet="",
        ))
    
    def _check_mutation_bypasses(self):
        """Check for potential mutation bypasses"""
        print("⚠️  Checking for potential mutation bypasses...")
        
        mutation_patterns = [
            r'CREATE\s+\(',
            r'MERGE\s+\(',
            r'DELETE\s+',
            r'SET\s+\w+\.',
        ]
        
        for pattern in mutation_patterns:
            matches = self._find_pattern(pattern, include_patterns=['*.py'])
            
            for file_path, line_num, line_content in matches:
                # Skip test files
                if any(test_pattern in file_path for test_pattern in self.test_patterns):
                    continue
                
                # Skip test assertions
                if self._is_test_assertion(file_path, line_num, line_content):
                    continue
                
                # Only flag if it's actually a Cypher mutation
                if not self._is_cypher_mutation(file_path, line_content):
                    continue
                
                # Check if it's in a string (likely Cypher query)
                if '"' in line_content or "'" in line_content:
                    file_content = self._read_file_content(file_path)
                    if ('GovernedNeo4jSession' not in file_content and 
                        'governed_session' not in file_content):
                        self.violations.append(GovernanceViolation(
                            file_path=file_path,
                            line_number=line_num,
                            severity=ViolationSeverity.MEDIUM,
                            category="POTENTIAL_MUTATION_BYPASS",
                            description="Cypher mutation without governance context",
                            code_snippet=line_content.strip()
                        ))
    
    def _should_exclude_file(self, file_path: str) -> bool:
        """Check if file should be excluded from validation"""
        return any(exclude in file_path for exclude in self.exclude_patterns)
    
    def _find_pattern(self, pattern: str, include_patterns: List[str]) -> List[Tuple[str, int, str]]:
        """Find pattern occurrences in files"""
        matches = []

        for include_pattern in include_patterns:
            if include_pattern == '*.py':
                if self._source_files is None:
                    self._source_files = [
                        path
                        for path in self.repo_root.rglob("*.py")
                        if not self._should_exclude_file(
                            str(path.relative_to(self.repo_root))
                        )
                    ]
                files = self._source_files
            else:
                files = list(self.repo_root.rglob(include_pattern))
            
            for file_path in files:
                rel_path = str(file_path.relative_to(self.repo_root))
                
                # Skip excluded files
                if self._should_exclude_file(rel_path):
                    continue

                content = self._read_file_content(rel_path)
                for line_num, line in enumerate(content.split('\n'), 1):
                    if re.search(pattern, line):
                        matches.append((rel_path, line_num, line))
        
        return matches
    
    def _read_file_content(self, file_path: str) -> str:
        """Read file content safely"""
        if file_path in self._source_contents:
            return self._source_contents[file_path]

        try:
            full_path = self.repo_root / file_path
            content = full_path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            content = ""

        self._source_contents[file_path] = content
        return content
    
    def _report_results(self) -> bool:
        """Report validation results"""
        print("\n📊 GOVERNANCE COMPLIANCE REPORT")
        print("=" * 50)
        
        if not self.violations:
            print("✅ EXCELLENT: No governance violations detected!")
            print("🏰 Your MAHOUN fortress is perfectly secure!")
            return True
        
        # Group by severity
        by_severity = {}
        for violation in self.violations:
            sev = violation.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(violation)
        
        total = len(self.violations)
        print(f"❌ VIOLATIONS DETECTED: {total}")
        
        for severity in [ViolationSeverity.CRITICAL, ViolationSeverity.HIGH, 
                        ViolationSeverity.MEDIUM, ViolationSeverity.LOW]:
            sev_violations = by_severity.get(severity.value, [])
            if sev_violations:
                print(f"\n🚨 {severity.value} ({len(sev_violations)} violations):")
                for v in sev_violations[:5]:  # Show first 5 of each severity
                    print(f"   📁 {v.file_path}:{v.line_number}")
                    print(f"      {v.description}")
                    if v.code_snippet:
                        print(f"      Code: {v.code_snippet}")
                if len(sev_violations) > 5:
                    print(f"   ... and {len(sev_violations) - 5} more")
        
        print(f"\n🔧 REMEDIATION NEEDED:")
        print("   1. Fix CRITICAL violations immediately")
        print("   2. Replace direct drivers with governed connections")
        print("   3. Use connection.execute_query() for read-only queries")
        print("   4. All mutations must go through GovernedNeo4jSession")
        
        return False


def main():
    """Main entry point"""
    repo_root = Path(__file__).parent.parent
    validator = GovernanceValidator(repo_root)
    
    success = validator.validate_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()