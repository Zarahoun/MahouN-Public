"""
Pre-Production Validation Data Models
=====================================

Immutable, type-safe data structures for validation framework.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC


class ValidationStatus(str, Enum):
    """
    Validation execution status.
    
    State machine:
    PENDING → RUNNING → PASS/FAIL/WARNING/BLOCKED/SKIPPED
    """
    PENDING = "PENDING"      # Not yet executed
    RUNNING = "RUNNING"      # Currently executing
    PASS = "PASS"           # All checks passed
    FAIL = "FAIL"           # Critical checks failed (P0)
    WARNING = "WARNING"      # Non-critical issues found (P1-P3)
    BLOCKED = "BLOCKED"     # Cannot execute (dependency failed or validator crashed)
    SKIPPED = "SKIPPED"     # Intentionally skipped (e.g., disabled in manifest)


class FindingSeverity(str, Enum):
    """
    Finding severity levels - aligned with task priorities.
    """
    P0_CRITICAL = "P0_CRITICAL"   # Production-breaking, must fix
    P1_HIGH = "P1_HIGH"           # Security/governance risk
    P2_MEDIUM = "P2_MEDIUM"       # Best practice violation
    P3_LOW = "P3_LOW"             # Optimization opportunity
    INFO = "INFO"                 # Informational only


@dataclass(frozen=True)
class Finding:
    """
    Single validation finding with evidence.
    
    Immutable by design - findings are facts that must not change.
    """
    severity: FindingSeverity
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    remediation: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for reporting"""
        return {
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }
    
    @property
    def is_blocker(self) -> bool:
        """P0 findings are production blockers"""
        return self.severity == FindingSeverity.P0_CRITICAL


@dataclass(frozen=True)
class ValidationResult:
    """
    Result from a single domain validator.
    
    Contains all findings, evidence, and execution metadata.
    """
    validator_id: str
    domain: str
    status: ValidationStatus
    findings: List[Finding] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    error_message: Optional[str] = None  # If status=BLOCKED
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for reporting"""
        return {
            "validator_id": self.validator_id,
            "domain": self.domain,
            "status": self.status.value,
            "findings": [f.to_dict() for f in self.findings],
            "findings_count": {
                "P0": self.count_by_severity(FindingSeverity.P0_CRITICAL),
                "P1": self.count_by_severity(FindingSeverity.P1_HIGH),
                "P2": self.count_by_severity(FindingSeverity.P2_MEDIUM),
                "P3": self.count_by_severity(FindingSeverity.P3_LOW),
            },
            "evidence": self.evidence,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            "error_message": self.error_message,
        }
    
    def count_by_severity(self, severity: FindingSeverity) -> int:
        """Count findings of given severity"""
        return sum(1 for f in self.findings if f.severity == severity)
    
    @property
    def has_blockers(self) -> bool:
        """Does this result contain P0 findings?"""
        return any(f.is_blocker for f in self.findings)
    
    @property
    def worst_severity(self) -> Optional[FindingSeverity]:
        """Return worst severity found, or None if no findings"""
        if not self.findings:
            return None
        
        severity_order = [
            FindingSeverity.P0_CRITICAL,
            FindingSeverity.P1_HIGH,
            FindingSeverity.P2_MEDIUM,
            FindingSeverity.P3_LOW,
            FindingSeverity.INFO,
        ]
        
        for sev in severity_order:
            if any(f.severity == sev for f in self.findings):
                return sev
        return None


@dataclass(frozen=True)
class OrchestratorResult:
    """
    Aggregated result from full validation run.
    
    This is the top-level output that determines production readiness.
    """
    overall_status: ValidationStatus
    compliance_score: float  # 0.0 - 1.0
    results: List[ValidationResult] = field(default_factory=list)
    blockers: List[Finding] = field(default_factory=list)  # P0 only
    warnings: List[Finding] = field(default_factory=list)  # P1-P3
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    profile: str = "production"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for reporting"""
        return {
            "overall_status": self.overall_status.value,
            "compliance_score": round(self.compliance_score, 4),
            "production_ready": self.is_production_ready,
            "summary": {
                "total_validators": len(self.results),
                "passed": sum(1 for r in self.results if r.status == ValidationStatus.PASS),
                "failed": sum(1 for r in self.results if r.status == ValidationStatus.FAIL),
                "warnings": sum(1 for r in self.results if r.status == ValidationStatus.WARNING),
                "blocked": sum(1 for r in self.results if r.status == ValidationStatus.BLOCKED),
                "blockers_count": len(self.blockers),
                "warnings_count": len(self.warnings),
            },
            "results": [r.to_dict() for r in self.results],
            "blockers": [b.to_dict() for b in self.blockers],
            "warnings": [w.to_dict() for w in self.warnings],
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            "profile": self.profile,
        }
    
    @property
    def is_production_ready(self) -> bool:
        """
        Production ready criteria:
        - Compliance score ≥ 95%
        - Zero P0 blockers
        - Overall status is PASS or WARNING (not FAIL/BLOCKED)
        """
        return (
            self.compliance_score >= 0.95
            and len(self.blockers) == 0
            and self.overall_status in (ValidationStatus.PASS, ValidationStatus.WARNING)
        )
    
    def get_blockers_by_domain(self) -> Dict[str, List[Finding]]:
        """Group blockers by validation domain"""
        by_domain: Dict[str, List[Finding]] = {}
        for result in self.results:
            if result.has_blockers:
                by_domain[result.domain] = [f for f in result.findings if f.is_blocker]
        return by_domain


@dataclass(frozen=True)
class ValidatorConfig:
    """
    Configuration for a single validator (from manifest).
    """
    validator_id: str
    class_name: str
    domain: str
    enabled: bool = True
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 60
    fail_fast: bool = False  # Stop orchestrator on failure?
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationManifest:
    """
    Complete validation configuration loaded from YAML.
    """
    version: str
    profile: str
    validators: List[ValidatorConfig]
    thresholds: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def min_compliance_score(self) -> float:
        """Minimum compliance score for production"""
        return self.thresholds.get("min_compliance_score", 0.95)
    
    @property
    def allow_p0_blockers(self) -> bool:
        """Can we proceed with P0 blockers? (should always be False)"""
        return self.thresholds.get("allow_p0_blockers", False)
