"""
Domain Validator Base Classes
=============================

Abstract base for all domain-specific validators.
"""

from abc import ABC, abstractmethod
from typing import List, Protocol, Dict, Any
from pathlib import Path
import time

from .models import (
    ValidationResult,
    ValidationStatus,
    Finding,
    FindingSeverity,
)
from .evidence_collector import EvidenceCollector


class EvidenceCollectorProtocol(Protocol):
    """
    Protocol for evidence collection.
    
    Validators use this interface to gather evidence.
    """
    def collect_file_lines(self, file_path: str, start_line: int, end_line: int) -> Dict[str, Any]:
        ...
    
    def collect_ast_analysis(self, file_path: str, node_type: str | None = None) -> Dict[str, Any]:
        ...
    
    def collect_command_output(self, command: List[str], timeout: int = 30) -> Dict[str, Any]:
        ...


class DomainValidator(ABC):
    """
    Abstract base class for all validators.
    
    Subclasses must implement:
    - validate(): Core validation logic
    - get_dependencies(): List of validator IDs this depends on
    
    Lifecycle:
    1. __init__(name, evidence_collector)
    2. validate() → ValidationResult
    3. Orchestrator aggregates results
    
    Design principles:
    - Idempotent: Multiple calls → same result
    - No side effects: Read-only operations
    - Fail-fast: Use fail_fast() for fatal errors
    - Evidence-based: Always provide evidence for findings
    """
    
    def __init__(
        self,
        name: str,
        evidence_collector: EvidenceCollectorProtocol,
        workspace_root: Path | None = None,
    ) -> None:
        self.name = name
        self.evidence_collector = evidence_collector
        self.workspace_root = workspace_root or Path.cwd()
        self.findings: List[Finding] = []
        self._status = ValidationStatus.PENDING
        self._start_time: float = 0.0
        self._end_time: float = 0.0
    
    @abstractmethod
    def validate(self) -> ValidationResult:
        """
        Execute domain-specific validation logic.
        
        MUST:
        - Be idempotent
        - Collect evidence for all findings
        - Set status based on worst finding severity
        - Complete within timeout (enforced by orchestrator)
        
        MUST NOT:
        - Modify system state
        - Depend on external services without fallback
        - Raise unhandled exceptions (use try/except)
        
        Returns:
            ValidationResult with findings and evidence
        """
        pass
    
    @abstractmethod
    def get_dependencies(self) -> List[str]:
        """
        Return list of validator IDs this validator depends on.
        
        Dependencies execute before this validator.
        If a dependency fails and fail_fast=True, this validator is SKIPPED.
        
        Returns:
            List of validator IDs (strings)
        
        Example:
            def get_dependencies(self) -> List[str]:
                return ["exception_validator", "test_classification_validator"]
        """
        pass
    
    def add_finding(
        self,
        severity: FindingSeverity,
        message: str,
        evidence: Dict[str, Any] | None = None,
        remediation: str | None = None,
        file_path: str | None = None,
        line_number: int | None = None,
    ) -> None:
        """
        Record a validation finding.
        
        Findings accumulate during validate() and are included in final result.
        
        Args:
            severity: Finding severity level
            message: Human-readable description
            evidence: Structured evidence data
            remediation: Suggested fix
            file_path: File where issue found
            line_number: Line number where issue found
        """
        finding = Finding(
            severity=severity,
            message=message,
            evidence=evidence or {},
            remediation=remediation,
            file_path=file_path,
            line_number=line_number,
        )
        self.findings.append(finding)
    
    def fail_fast(
        self,
        message: str,
        evidence: Dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Immediately fail validation and return BLOCKED result.
        
        Use for fatal errors (e.g., validator crashed, critical dependency missing).
        
        Args:
            message: Error description
            evidence: Additional context
        
        Returns:
            ValidationResult with status=BLOCKED
        """
        return ValidationResult(
            validator_id=self.name,
            domain=self.__class__.__name__,
            status=ValidationStatus.BLOCKED,
            findings=[
                Finding(
                    severity=FindingSeverity.P0_CRITICAL,
                    message=f"Validator failed: {message}",
                    evidence=evidence or {},
                )
            ],
            evidence=evidence or {},
            execution_time_ms=0.0,
            error_message=message,
        )
    
    def _compute_status(self) -> ValidationStatus:
        """
        Compute final status based on findings.
        
        Logic:
        - Any P0 → FAIL
        - Any P1-P3 → WARNING
        - No findings → PASS
        """
        if not self.findings:
            return ValidationStatus.PASS
        
        # Check for blockers
        if any(f.severity == FindingSeverity.P0_CRITICAL for f in self.findings):
            return ValidationStatus.FAIL
        
        # Check for warnings
        if any(f.severity in (FindingSeverity.P1_HIGH, FindingSeverity.P2_MEDIUM, FindingSeverity.P3_LOW) 
               for f in self.findings):
            return ValidationStatus.WARNING
        
        # Only INFO findings
        return ValidationStatus.PASS
    
    def _build_result(self, additional_evidence: Dict[str, Any] | None = None) -> ValidationResult:
        """
        Build final ValidationResult from accumulated findings.
        
        Called at end of validate() to construct result object.
        """
        execution_time = (self._end_time - self._start_time) * 1000  # Convert to ms
        
        return ValidationResult(
            validator_id=self.name,
            domain=self.__class__.__name__,
            status=self._compute_status(),
            findings=self.findings.copy(),
            evidence=additional_evidence or {},
            execution_time_ms=execution_time,
        )
    
    def run_with_timing(self) -> ValidationResult:
        """
        Execute validate() with timing instrumentation.
        
        This is called by the orchestrator, not by validator implementations.
        """
        self._start_time = time.time()
        self._status = ValidationStatus.RUNNING
        
        try:
            result = self.validate()
            self._end_time = time.time()
            return result
        except Exception as e:
            self._end_time = time.time()
            return self.fail_fast(
                message=f"Unexpected error: {e}",
                evidence={"exception_type": type(e).__name__, "exception_message": str(e)}
            )


class NoOpValidator(DomainValidator):
    """
    No-op validator for testing and examples.
    
    Always passes validation.
    """
    
    def validate(self) -> ValidationResult:
        """Always passes"""
        self._start_time = time.time()
        self._end_time = time.time()
        return self._build_result(additional_evidence={"note": "No-op validator"})
    
    def get_dependencies(self) -> List[str]:
        """No dependencies"""
        return []
