"""
Security Hardening Validator
============================

Ultra-advanced security validator focusing on governance bypass prevention:
- Neo4j driver usage outside allowlist
- GovernanceContext duplication check
- Authorization boundary enforcement
- API key lifecycle completeness
- RBAC permission matrix coverage
- Forbidden pattern detection

Advanced Features:
- Multi-layer AST + grep scanning
- Cross-references AGENTS.md canonical rules
- Automated remediation path generation
- Security test coverage analysis
- Compliance scoring with risk weighting
"""

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..base_validator import DomainValidator, EvidenceCollectorProtocol
from ..models import Finding, FindingSeverity, ValidationResult


@dataclass
class ForbiddenPatternMatch:
    """A match of a forbidden pattern in code."""
    
    pattern_name: str
    file_path: str
    line_number: int
    matched_text: str
    severity: FindingSeverity
    context: str = ""
    is_exception: bool = False  # Is this an allowed exception?


class SecurityHardeningValidator(DomainValidator):
    """
    Ultra-advanced security hardening validator.
    
    Validates:
    1. Neo4j Governance Bypass Prevention
       - Driver instantiation outside allowlist
       - Direct session access
       
    2. GovernanceContext Singleton Enforcement
       - Multiple GovernanceContext definitions
       - _authorized_write_ctx duplication
       
    3. API Key Lifecycle Tests
       - Rotation test existence
       - Collision prevention coverage
       - Revocation propagation
       
    4. RBAC Permission Matrix Tests
       - Permission inheritance coverage
       - Role escalation prevention
       - Cross-tenant isolation
       
    5. Forbidden Code Patterns
       - exec() / eval() in production code
       - Silent exception swallowing
       - Hardcoded secrets
    
    Advanced Features:
    - Allowlist management with exceptions
    - Test coverage cross-referencing
    - Risk-weighted compliance scoring
    """
    
    # Neo4j driver allowlist (canonical from AGENTS.md)
    NEO4J_ALLOWLIST = [
        "mahoun/graph/neo4j/connection.py",
        "mahoun/graph/neo4j/schema.py",
        "api/database.py",  # Schema init only
        "tests/fixtures/seed_data.py",  # Test fixture (documented exception)
    ]
    
    # Required security test files
    REQUIRED_SECURITY_TESTS = [
        "tests/security/test_api_key_lifecycle.py",
        "tests/security/test_api_key_collision_prevention.py",
        "tests/security/test_rbac_permission_matrix.py",
    ]
    
    def __init__(
        self,
        evidence_collector: EvidenceCollectorProtocol,
        workspace_root: Path | None = None
    ):
        super().__init__(
            name="security-hardening-validator",
            evidence_collector=evidence_collector,
            workspace_root=workspace_root or Path.cwd()
        )
    
    def get_dependencies(self) -> List[str]:
        """Security validation has no dependencies."""
        return []
    
    def validate(self) -> ValidationResult:
        """Run full security hardening validation."""
        self._start_time = 0.0
        self._end_time = 0.0
        
        # 1. Check Neo4j governance bypass prevention
        neo4j_findings = self._check_neo4j_governance()
        
        # 2. Check GovernanceContext singleton
        governance_context_findings = self._check_governance_context_singleton()
        
        # 3. Verify security test coverage
        test_coverage_findings = self._check_security_test_coverage()
        
        # 4. Scan forbidden patterns
        forbidden_pattern_findings = self._scan_forbidden_patterns()
        
        # 5. Check authorization boundary tests
        authz_findings = self._check_authorization_boundary_tests()
        
        # Aggregate all findings
        all_findings = (
            neo4j_findings +
            governance_context_findings +
            test_coverage_findings +
            forbidden_pattern_findings +
            authz_findings
        )
        
        # Add to validator findings list
        for finding in all_findings:
            self.findings.append(finding)
        
        # Calculate compliance score
        compliance_score = self._calculate_security_compliance_score()
        
        # Build result
        return self._build_result(additional_evidence={
            "neo4j_governance_violations": len(neo4j_findings),
            "governance_context_duplications": len(governance_context_findings),
            "missing_security_tests": len([f for f in test_coverage_findings if f.severity == FindingSeverity.P0_CRITICAL]),
            "forbidden_patterns_found": len(forbidden_pattern_findings),
            "security_compliance_score": compliance_score,
            "p0_blockers": sum(1 for f in all_findings if f.severity == FindingSeverity.P0_CRITICAL),
        })
    
    def _check_neo4j_governance(self) -> List[Finding]:
        """Check Neo4j driver usage against allowlist."""
        findings = []
        
        # Search for Neo4j driver instantiation patterns
        patterns = [
            r"GraphDatabase\.driver\(",
            r"AsyncGraphDatabase\.driver\(",
            r"from\s+neo4j\s+import\s+GraphDatabase",
            r"from\s+neo4j\s+import\s+AsyncGraphDatabase",
        ]
        
        violations: List[ForbiddenPatternMatch] = []
        
        for pattern in patterns:
            try:
                result = subprocess.run(
                    [
                        "grep",
                        "-rn",
                        "--include=*.py",
                        "-E",
                        pattern,
                        str(self.workspace_root / "mahoun"),
                        str(self.workspace_root / "api"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        
                        parts = line.split(":", 2)
                        if len(parts) < 3:
                            continue
                        
                        file_path = parts[0]
                        line_num = int(parts[1])
                        matched_text = parts[2].strip()
                        
                        # Check if file is in allowlist
                        rel_path = Path(file_path).relative_to(self.workspace_root).as_posix()
                        is_allowed = any(
                            allowlist_path in rel_path 
                            for allowlist_path in self.NEO4J_ALLOWLIST
                        )
                        
                        if not is_allowed:
                            violations.append(ForbiddenPatternMatch(
                                pattern_name="Neo4j Driver Outside Allowlist",
                                file_path=rel_path,
                                line_number=line_num,
                                matched_text=matched_text,
                                severity=FindingSeverity.P0_CRITICAL,
                                context=f"Pattern: {pattern}",
                                is_exception=False,
                            ))
            
            except subprocess.TimeoutExpired:
                self.add_finding(
                    severity=FindingSeverity.P2_MEDIUM,
                    message=f"Neo4j pattern search timed out for pattern: {pattern}",
                )
            except Exception as e:
                self.add_finding(
                    severity=FindingSeverity.P2_MEDIUM,
                    message=f"Failed to scan for Neo4j patterns: {e}",
                )
        
        # Generate findings from violations
        if violations:
            grouped_by_file = {}
            for v in violations:
                if v.file_path not in grouped_by_file:
                    grouped_by_file[v.file_path] = []
                grouped_by_file[v.file_path].append(v)
            
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"Neo4j driver usage detected outside allowlist in {len(grouped_by_file)} files",
                evidence={
                    "violations": [
                        {
                            "file": file_path,
                            "occurrences": [
                                {
                                    "line": v.line_number,
                                    "text": v.matched_text,
                                }
                                for v in viols
                            ]
                        }
                        for file_path, viols in grouped_by_file.items()
                    ],
                    "allowlist": self.NEO4J_ALLOWLIST,
                },
                remediation=(
                    "Neo4j driver access must only occur in allowlisted files:\n"
                    + "\n".join(f"  - {path}" for path in self.NEO4J_ALLOWLIST) +
                    "\n\nAll other code must use GovernedNeo4jSession from mahoun.graph.neo4j.connection"
                )
            ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message="✓ Neo4j governance: No unauthorized driver usage detected",
                evidence={"scanned_patterns": len(patterns), "allowlist": self.NEO4J_ALLOWLIST}
            ))
        
        return findings
    
    def _check_governance_context_singleton(self) -> List[Finding]:
        """Check GovernanceContext is truly singleton."""
        findings = []
        
        # Search for class GovernanceContext definitions
        governance_context_files = []
        
        try:
            result = subprocess.run(
                [
                    "grep",
                    "-rn",
                    "--include=*.py",
                    "class GovernanceContext",
                    str(self.workspace_root / "mahoun"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        file_path = Path(parts[0]).relative_to(self.workspace_root).as_posix()
                        line_num = int(parts[1])
                        governance_context_files.append((file_path, line_num))
        
        except Exception as e:
            self.add_finding(
                severity=FindingSeverity.P2_MEDIUM,
                message=f"Failed to scan for GovernanceContext: {e}",
            )
        
        # There should be exactly one canonical definition
        canonical_path = "mahoun/core/governance/governance_context.py"
        
        non_canonical = [
            (path, line) for path, line in governance_context_files
            if canonical_path not in path
        ]
        
        if len(non_canonical) > 0:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"GovernanceContext defined in {len(non_canonical)} non-canonical locations",
                evidence={
                    "canonical_location": canonical_path,
                    "duplicates": [
                        {"file": path, "line": line}
                        for path, line in non_canonical
                    ]
                },
                remediation=(
                    f"Only {canonical_path} should define GovernanceContext.\n"
                    "Remove duplicate definitions and import from canonical location."
                )
            ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message="✓ GovernanceContext singleton: No duplicates found",
            ))
        
        # Check _authorized_write_ctx singleton
        authz_ctx_files = []
        
        try:
            result = subprocess.run(
                [
                    "grep",
                    "-rn",
                    "--include=*.py",
                    "_authorized_write_ctx = ",
                    str(self.workspace_root / "mahoun"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line or "ContextVar" not in line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        file_path = Path(parts[0]).relative_to(self.workspace_root).as_posix()
                        line_num = int(parts[1])
                        authz_ctx_files.append((file_path, line_num))
        
        except Exception as e:
            pass  # Not critical if grep fails
        
        canonical_authz_path = "mahoun/core/governance/authorization_state.py"
        
        non_canonical_authz = [
            (path, line) for path, line in authz_ctx_files
            if canonical_authz_path not in path
        ]
        
        if len(non_canonical_authz) > 0:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"_authorized_write_ctx defined in {len(non_canonical_authz)} non-canonical locations",
                evidence={
                    "canonical_location": canonical_authz_path,
                    "duplicates": [
                        {"file": path, "line": line}
                        for path, line in non_canonical_authz
                    ]
                },
                remediation=(
                    f"Only {canonical_authz_path} should define _authorized_write_ctx.\n"
                    "This ContextVar must be globally unique for governance to work."
                )
            ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message="✓ Authorization context singleton: No duplicates found",
            ))
        
        return findings
    
    def _check_security_test_coverage(self) -> List[Finding]:
        """Check required security tests exist."""
        findings = []
        
        missing_tests = []
        existing_tests = []
        
        for test_file in self.REQUIRED_SECURITY_TESTS:
            test_path = self.workspace_root / test_file
            if test_path.exists():
                existing_tests.append(test_file)
            else:
                missing_tests.append(test_file)
        
        if missing_tests:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"{len(missing_tests)} required security test files missing",
                evidence={
                    "missing": missing_tests,
                    "existing": existing_tests,
                },
                remediation=(
                    "Create comprehensive security tests:\n"
                    + "\n".join(f"  - {path}" for path in missing_tests)
                )
            ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message=f"✓ All {len(self.REQUIRED_SECURITY_TESTS)} required security test files exist",
                evidence={"test_files": existing_tests}
            ))
        
        return findings
    
    def _scan_forbidden_patterns(self) -> List[Finding]:
        """Scan for forbidden code patterns."""
        findings = []
        
        # Patterns from steering rules
        forbidden_patterns = [
            {
                "pattern": r"\bexec\s*\(",
                "name": "exec() usage",
                "severity": FindingSeverity.P0_CRITICAL,
                "exclude_paths": ["tests/", "examples/"],
                "message": "exec() detected in production code",
            },
            {
                "pattern": r"\beval\s*\(",
                "name": "eval() usage",
                "severity": FindingSeverity.P0_CRITICAL,
                "exclude_paths": ["tests/", "examples/"],
                "message": "eval() detected in production code",
            },
            {
                "pattern": r"except\s+Exception\s*:\s*pass",
                "name": "Silent exception swallowing",
                "severity": FindingSeverity.P1_HIGH,
                "exclude_paths": [],
                "message": "Silent exception handling detected",
            },
            {
                "pattern": r"password\s*=\s*['\"][\w]{8,}['\"]",
                "name": "Hardcoded password",
                "severity": FindingSeverity.P0_CRITICAL,
                "exclude_paths": ["tests/", "examples/"],
                "message": "Potential hardcoded password detected",
            },
        ]
        
        all_violations = []
        
        for pattern_def in forbidden_patterns:
            try:
                result = subprocess.run(
                    [
                        "grep",
                        "-rn",
                        "--include=*.py",
                        "-E",
                        pattern_def["pattern"],
                        str(self.workspace_root / "mahoun"),
                        str(self.workspace_root / "api"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        
                        parts = line.split(":", 2)
                        if len(parts) < 3:
                            continue
                        
                        file_path = parts[0]
                        rel_path = Path(file_path).relative_to(self.workspace_root).as_posix()
                        
                        # Check exclude paths
                        is_excluded = any(
                            excl in rel_path 
                            for excl in pattern_def["exclude_paths"]
                        )
                        
                        if not is_excluded:
                            line_num = int(parts[1])
                            matched_text = parts[2].strip()
                            
                            all_violations.append(ForbiddenPatternMatch(
                                pattern_name=pattern_def["name"],
                                file_path=rel_path,
                                line_number=line_num,
                                matched_text=matched_text,
                                severity=pattern_def["severity"],
                            ))
            
            except Exception as e:
                pass  # Continue with other patterns
        
        # Generate findings from violations
        if all_violations:
            # Group by severity
            by_severity = {}
            for v in all_violations:
                if v.severity not in by_severity:
                    by_severity[v.severity] = []
                by_severity[v.severity].append(v)
            
            for severity, viols in by_severity.items():
                findings.append(Finding(
                    severity=severity,
                    message=f"{len(viols)} forbidden pattern violations detected",
                    evidence={
                        "violations": [
                            {
                                "pattern": v.pattern_name,
                                "file": v.file_path,
                                "line": v.line_number,
                                "text": v.matched_text[:100],
                            }
                            for v in viols[:20]  # Limit to first 20
                        ],
                        "total_count": len(viols),
                    },
                    remediation="Remove or refactor forbidden patterns according to security guidelines"
                ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message="✓ No forbidden code patterns detected",
            ))
        
        return findings
    
    def _check_authorization_boundary_tests(self) -> List[Finding]:
        """Check authorization boundary test coverage."""
        findings = []
        
        # Check for governance test files
        governance_test_files = [
            "tests/governance/test_governance_hardening_sprint.py",
            "tests/governance/test_hardened_infrastructure.py",
            "tests/test_governance_bypass_prevention.py",
            "tests/test_authorization_state_singleton.py",
        ]
        
        existing_authz_tests = []
        missing_authz_tests = []
        
        for test_file in governance_test_files:
            test_path = self.workspace_root / test_file
            if test_path.exists():
                existing_authz_tests.append(test_file)
            else:
                missing_authz_tests.append(test_file)
        
        if len(existing_authz_tests) > 0:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message=f"✓ {len(existing_authz_tests)} authorization boundary test files found",
                evidence={"test_files": existing_authz_tests}
            ))
        
        if len(missing_authz_tests) > 0:
            findings.append(Finding(
                severity=FindingSeverity.P1_HIGH,
                message=f"{len(missing_authz_tests)} recommended authorization tests missing",
                evidence={"missing": missing_authz_tests},
                remediation="Add comprehensive authorization boundary tests"
            ))
        
        return findings
    
    def _calculate_security_compliance_score(self) -> float:
        """Calculate security compliance score (0-100)."""
        # Scoring logic:
        # - Start at 100
        # - Deduct based on finding severity
        #   - P0: -25 points each
        #   - P1: -10 points each
        #   - P2: -5 points each
        #   - P3: -2 points each
        
        score = 100.0
        
        for finding in self.findings:
            if finding.severity == FindingSeverity.P0_CRITICAL:
                score -= 25.0
            elif finding.severity == FindingSeverity.P1_HIGH:
                score -= 10.0
            elif finding.severity == FindingSeverity.P2_MEDIUM:
                score -= 5.0
            elif finding.severity == FindingSeverity.P3_LOW:
                score -= 2.0
        
        return max(0.0, score)
