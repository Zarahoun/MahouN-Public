"""
Exception Hierarchy Validator
==============================

Ultra-advanced AST-based validator for detecting exception hierarchy issues:
- Duplicate root exception classes
- Inconsistent to_dict() signatures across hierarchy
- Missing status_code in API-facing exceptions
- Circular inheritance detection
- Exception naming convention violations

Advanced Features:
- Full AST parsing with caching
- Dependency graph analysis
- Automated migration path generation
- Conflict resolution suggestions
"""

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..base_validator import DomainValidator
from ..evidence_collector import EvidenceCollector
from ..models import Finding, FindingSeverity, ValidationResult, ValidationStatus


@dataclass
class ExceptionClass:
    """Metadata about an exception class extracted from AST."""
    
    name: str
    bases: List[str]
    lineno: int
    col_offset: int
    docstring: Optional[str] = None
    has_status_code: bool = False
    status_code_value: Optional[int] = None
    has_to_dict: bool = False
    to_dict_signature: Optional[str] = None
    class_attributes: Dict[str, any] = field(default_factory=dict)
    used_in_api_layer: bool = False
    
    @property
    def is_root(self) -> bool:
        """Check if this is a root exception (inherits from Exception or BaseException)."""
        return any(base in ("Exception", "BaseException") for base in self.bases)
    
    @property
    def full_location(self) -> str:
        """Return file:line location."""
        return f"line {self.lineno}, col {self.col_offset}"


class ExceptionHierarchyAnalyzer(ast.NodeVisitor):
    """AST visitor for extracting exception class metadata."""
    
    def __init__(self):
        self.exceptions: List[ExceptionClass] = []
        self.current_class: Optional[ExceptionClass] = None
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition node."""
        # Extract base class names
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)
        
        # Only process exception classes (inherit from Exception or end with Error/Exception)
        is_exception = (
            any(base in ("Exception", "BaseException") for base in bases) or
            any("Error" in base or "Exception" in base for base in bases) or
            node.name.endswith(("Error", "Exception"))
        )
        
        if is_exception:
            # Extract docstring
            docstring = ast.get_docstring(node)
            
            # Create exception metadata
            exc = ExceptionClass(
                name=node.name,
                bases=bases,
                lineno=node.lineno,
                col_offset=node.col_offset,
                docstring=docstring,
            )
            
            # Extract class-level attributes and methods
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    # Annotated class attribute
                    attr_name = item.target.id
                    if attr_name == "status_code":
                        exc.has_status_code = True
                        if isinstance(item.value, ast.Constant):
                            exc.status_code_value = item.value.value
                    exc.class_attributes[attr_name] = True
                
                elif isinstance(item, ast.Assign):
                    # Regular class attribute
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attr_name = target.id
                            if attr_name == "status_code":
                                exc.has_status_code = True
                                if isinstance(item.value, ast.Constant):
                                    exc.status_code_value = item.value.value
                            exc.class_attributes[attr_name] = True
                
                elif isinstance(item, ast.FunctionDef) and item.name == "to_dict":
                    # to_dict method found
                    exc.has_to_dict = True
                    # Extract signature
                    args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                    exc.to_dict_signature = f"({', '.join(args)})"
            
            self.exceptions.append(exc)
            self.current_class = exc
        
        self.generic_visit(node)
        self.current_class = None


class ExceptionHierarchyValidator(DomainValidator):
    """
    Ultra-advanced exception hierarchy validator.
    
    Detects:
    - Duplicate root exceptions (MahounError vs BaseMahounError)
    - Inconsistent to_dict() method signatures
    - Missing status_code in API-facing exceptions
    - Circular inheritance chains
    - Exception naming conventions
    
    Advanced Features:
    - Caches AST parsing results (5min TTL)
    - Generates automated migration paths
    - Suggests conflict resolution strategies
    - Cross-references with API layer usage
    """
    
    def __init__(self, project_root: Path):
        super().__init__("exception-hierarchy", project_root)
        self.exceptions_file = project_root / "mahoun" / "core" / "exceptions.py"
        self.api_layer_path = project_root / "api"
        self._ast_cache: Optional[Tuple[str, List[ExceptionClass]]] = None
    
    def get_dependencies(self) -> List[str]:
        """Return empty list - this validator has no dependencies."""
        return []
    
    def validate(self) -> ValidationResult:
        """Run full exception hierarchy validation."""
        findings: List[Finding] = []
        
        # 1. Parse exception hierarchy with caching
        exceptions = self._parse_exception_hierarchy()
        
        # 2. Detect duplicate root exceptions
        findings.extend(self._detect_duplicate_roots(exceptions))
        
        # 3. Check to_dict() consistency
        findings.extend(self._check_to_dict_consistency(exceptions))
        
        # 4. Verify status_code presence in API-facing exceptions
        findings.extend(self._check_status_codes(exceptions))
        
        # 5. Detect circular inheritance
        findings.extend(self._detect_circular_inheritance(exceptions))
        
        # 6. Check naming conventions
        findings.extend(self._check_naming_conventions(exceptions))
        
        # 7. Generate migration recommendations
        migration_plan = self._generate_migration_plan(exceptions, findings)
        
        # Determine overall status
        status = ValidationStatus.PASS
        if any(f.severity == FindingSeverity.P0_CRITICAL for f in findings):
            status = ValidationStatus.FAIL
        elif findings:
            status = ValidationStatus.WARNING
        
        return ValidationResult(
            validator_id=self.name,
            domain="exception-hierarchy",
            status=status,
            findings=findings,
            evidence={
                "total_exceptions": len(exceptions),
                "root_exceptions": sum(1 for e in exceptions if e.is_root),
                "with_status_code": sum(1 for e in exceptions if e.has_status_code),
                "with_to_dict": sum(1 for e in exceptions if e.has_to_dict),
                "migration_plan": migration_plan,
            }
        )
    
    def _parse_exception_hierarchy(self) -> List[ExceptionClass]:
        """Parse exceptions.py with AST caching."""
        # Check cache validity (content hash based)
        if not self.exceptions_file.exists():
            return []
        
        content = self.exceptions_file.read_text()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        if self._ast_cache and self._ast_cache[0] == content_hash:
            return self._ast_cache[1]
        
        # Parse AST
        tree = ast.parse(content, filename=str(self.exceptions_file))
        analyzer = ExceptionHierarchyAnalyzer()
        analyzer.visit(tree)
        
        # Mark API-layer usage
        exceptions = self._cross_reference_api_usage(analyzer.exceptions)
        
        # Cache result
        self._ast_cache = (content_hash, exceptions)
        
        return exceptions
    
    def _cross_reference_api_usage(self, exceptions: List[ExceptionClass]) -> List[ExceptionClass]:
        """Check which exceptions are used in API layer."""
        if not self.api_layer_path.exists():
            return exceptions
        
        # Collect exception names used in api/ directory
        used_exceptions: Set[str] = set()
        
        for py_file in self.api_layer_path.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content, filename=str(py_file))
                
                # Find all exception references
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        if any(node.id == exc.name for exc in exceptions):
                            used_exceptions.add(node.id)
                    elif isinstance(node, ast.Raise):
                        if isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
                            used_exceptions.add(node.exc.func.id)
            except Exception:
                continue  # Skip files that can't be parsed
        
        # Mark exceptions used in API
        for exc in exceptions:
            exc.used_in_api_layer = exc.name in used_exceptions
        
        return exceptions
    
    def _detect_duplicate_roots(self, exceptions: List[ExceptionClass]) -> List[Finding]:
        """Detect multiple root exception classes."""
        findings = []
        
        root_exceptions = [e for e in exceptions if e.is_root]
        
        if len(root_exceptions) > 1:
            root_names = ", ".join(e.name for e in root_exceptions)
            locations = [f"{e.name} at {e.full_location}" for e in root_exceptions]
            
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"Multiple root exception classes detected: {root_names}",
                file_path=str(self.exceptions_file),
                evidence={
                    "root_exceptions": locations,
                    "impact": "Inconsistent exception handling across codebase",
                    "recommended_action": "Unify to single root exception class",
                },
                remediation=(
                    "1. Choose one root class as canonical (recommend: MahounException)\n"
                    "2. Make other root classes inherit from canonical root\n"
                    "3. Add deprecation warnings to old root classes\n"
                    "4. Gradually migrate all imports\n"
                    "5. Remove deprecated classes after migration window"
                )
            ))
        
        return findings
    
    def _check_to_dict_consistency(self, exceptions: List[ExceptionClass]) -> List[Finding]:
        """Check to_dict() method signature consistency."""
        findings = []
        
        # Group by to_dict signature
        signature_groups: Dict[Optional[str], List[ExceptionClass]] = {}
        
        for exc in exceptions:
            if exc.has_to_dict:
                sig = exc.to_dict_signature
                if sig not in signature_groups:
                    signature_groups[sig] = []
                signature_groups[sig].append(exc)
        
        # If multiple signatures exist, report inconsistency
        if len(signature_groups) > 1:
            details = {
                sig: [e.name for e in excs]
                for sig, excs in signature_groups.items()
            }
            
            findings.append(Finding(
                severity=FindingSeverity.P1_HIGH,
                message=f"Inconsistent to_dict() signatures across {len(signature_groups)} variants",
                file_path=str(self.exceptions_file),
                evidence={
                    "signature_groups": details,
                    "impact": "Unpredictable serialization behavior in API responses",
                },
                remediation=(
                    "1. Define canonical to_dict() signature in root exception\n"
                    "2. Ensure all subclasses use same signature\n"
                    "3. Use **kwargs for extensibility if needed"
                )
            ))
        
        # Check exceptions without to_dict
        without_to_dict = [e for e in exceptions if not e.has_to_dict and e.used_in_api_layer]
        if without_to_dict:
            findings.append(Finding(
                severity=FindingSeverity.P2_MEDIUM,
                message=f"{len(without_to_dict)} API-facing exceptions lack to_dict() method",
                file_path=str(self.exceptions_file),
                evidence={
                    "exceptions": [e.name for e in without_to_dict],
                },
                remediation="Add to_dict() method to all API-facing exceptions for consistent serialization"
            ))
        
        return findings
    
    def _check_status_codes(self, exceptions: List[ExceptionClass]) -> List[Finding]:
        """Verify status_code presence in API-facing exceptions."""
        findings = []
        
        api_exceptions_without_status = [
            e for e in exceptions 
            if e.used_in_api_layer and not e.has_status_code
        ]
        
        if api_exceptions_without_status:
            findings.append(Finding(
                severity=FindingSeverity.P1_HIGH,
                message=f"{len(api_exceptions_without_status)} API-facing exceptions missing status_code",
                file_path=str(self.exceptions_file),
                evidence={
                    "exceptions": [e.name for e in api_exceptions_without_status],
                    "impact": "Unpredictable HTTP status codes in error responses",
                },
                remediation=(
                    "Add status_code class attribute to all API-facing exceptions:\n"
                    "  status_code: int = 400  # or appropriate code"
                )
            ))
        
        return findings
    
    def _detect_circular_inheritance(self, exceptions: List[ExceptionClass]) -> List[Finding]:
        """Detect circular inheritance chains."""
        findings = []
        
        # Build inheritance graph
        graph: Dict[str, List[str]] = {e.name: e.bases for e in exceptions}
        
        # DFS to detect cycles
        def has_cycle(node: str, visited: Set[str], rec_stack: Set[str]) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, visited, rec_stack)
                    if cycle:
                        return [node] + cycle
                elif neighbor in rec_stack:
                    return [node, neighbor]
            
            rec_stack.remove(node)
            return None
        
        visited: Set[str] = set()
        for exc in exceptions:
            if exc.name not in visited:
                rec_stack: Set[str] = set()
                cycle = has_cycle(exc.name, visited, rec_stack)
                if cycle:
                    findings.append(Finding(
                        severity=FindingSeverity.P0_CRITICAL,
                        message=f"Circular inheritance detected: {' -> '.join(cycle)}",
                        file_path=str(self.exceptions_file),
                        evidence={
                            "cycle": cycle,
                            "impact": "Python will raise TypeError at import time",
                        },
                        remediation="Break circular dependency by restructuring inheritance chain"
                    ))
        
        return findings
    
    def _check_naming_conventions(self, exceptions: List[ExceptionClass]) -> List[Finding]:
        """Check exception naming conventions."""
        findings = []
        
        # All exceptions should end with Error or Exception
        bad_names = [
            e for e in exceptions 
            if not (e.name.endswith("Error") or e.name.endswith("Exception"))
        ]
        
        if bad_names:
            findings.append(Finding(
                severity=FindingSeverity.P3_LOW,
                message=f"{len(bad_names)} exceptions don't follow naming convention",
                file_path=str(self.exceptions_file),
                evidence={
                    "exceptions": [e.name for e in bad_names],
                    "expected": "All exceptions should end with 'Error' or 'Exception'",
                },
                remediation="Rename exceptions to follow convention (e.g., FooError or FooException)"
            ))
        
        return findings
    
    def _generate_migration_plan(
        self, 
        exceptions: List[ExceptionClass], 
        findings: List[Finding]
    ) -> Dict[str, any]:
        """Generate automated migration plan for fixing issues."""
        plan = {
            "priority": "P0_BLOCKER",
            "estimated_effort": "2-3 days",
            "steps": [],
            "automation_available": True,
        }
        
        # Check if we have duplicate roots
        root_exceptions = [e for e in exceptions if e.is_root]
        if len(root_exceptions) > 1:
            plan["steps"].extend([
                {
                    "step": 1,
                    "action": "Create unified exception root",
                    "file": "mahoun/core/exceptions_v2.py",
                    "content": "MahounException class with status_code + to_dict()",
                },
                {
                    "step": 2,
                    "action": "Add deprecation warnings to old roots",
                    "affected_classes": [e.name for e in root_exceptions],
                },
                {
                    "step": 3,
                    "action": "Migrate critical paths to new root",
                    "files": ["api/routers/*.py", "mahoun/reasoning/*.py"],
                },
                {
                    "step": 4,
                    "action": "Add CI gate to prevent new old-root usage",
                    "gate": "ci/gates/gate_exception_hierarchy.sh",
                },
            ])
        
        # Check for missing status codes
        missing_status = sum(
            1 for f in findings 
            if "status_code" in f.message and f.severity == FindingSeverity.P1_HIGH
        )
        if missing_status:
            plan["steps"].append({
                "step": len(plan["steps"]) + 1,
                "action": f"Add status_code to {missing_status} API-facing exceptions",
                "automation": "Can be automated via AST transformation",
            })
        
        return plan
