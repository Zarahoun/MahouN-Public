"""
MAHOUN Pre-Production Validation Framework
==========================================

Automated validation orchestrator for production readiness assessment.

This package provides:
- ValidationOrchestrator: Coordinates execution of domain validators
- DomainValidator base: Abstract base for all validators
- Evidence collection and finding aggregation
- Compliance scoring and reporting

Usage:
    from mahoun.preproduction import ValidationOrchestrator
    
    orchestrator = ValidationOrchestrator.from_manifest("preproduction_manifest.yaml")
    result = orchestrator.run_validation(profile="production")
    
    if result.compliance_score >= 0.95:
        print("Production ready!")
    else:
        print(f"Blockers: {result.blockers}")
"""

__version__ = "1.0.0"

from .models import (
    ValidationStatus,
    ValidationResult,
    Finding,
    FindingSeverity,
    OrchestratorResult,
)
from .base_validator import DomainValidator, EvidenceCollectorProtocol
from .orchestrator import ValidationOrchestrator

__all__ = [
    "ValidationStatus",
    "ValidationResult",
    "Finding",
    "FindingSeverity",
    "OrchestratorResult",
    "DomainValidator",
    "EvidenceCollectorProtocol",
    "ValidationOrchestrator",
]
