"""
MAHOUN Legal Consolidation Engine
=================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Provides continuous, evidence-based monitoring, detection, analysis,
temporal validation, and governed review of changes in Iranian laws and regulations.
"""

from mahoun.legal_consolidation.change_detector import LegalChangeDetector
from mahoun.legal_consolidation.engine import LegalConsolidationEngine
from mahoun.legal_consolidation.models import (
    ArticleTemporalVersion,
    ChangeType,
    ConsolidationRunReceipt,
    DetectedLegalChange,
    HumanReviewItem,
    LegalStatus,
    MonitoredSourceDocument,
    NormativeRelationship,
    NormativeRelationType,
    ReviewDecision,
    SourceAuthorityType,
    VerificationStatus,
)
from mahoun.legal_consolidation.relationship_analyzer import (
    NormativeRelationshipAnalyzer,
)
from mahoun.legal_consolidation.review_workflow import (
    GovernanceReviewError,
    HumanLegalReviewWorkflow,
    UnauthorizedLegalAssertionError,
)
from mahoun.legal_consolidation.source_monitor import (
    LegalSourceMonitor,
    SourceIntegrityError,
    SourceVerificationError,
    UnverifiableSourceError,
)
from mahoun.legal_consolidation.temporal_engine import TemporalValidationEngine

__all__ = [
    # Models & Enums
    "SourceAuthorityType",
    "ChangeType",
    "NormativeRelationType",
    "LegalStatus",
    "VerificationStatus",
    "ReviewDecision",
    "MonitoredSourceDocument",
    "DetectedLegalChange",
    "NormativeRelationship",
    "ArticleTemporalVersion",
    "HumanReviewItem",
    "ConsolidationRunReceipt",
    # Core Components
    "LegalSourceMonitor",
    "LegalChangeDetector",
    "NormativeRelationshipAnalyzer",
    "TemporalValidationEngine",
    "HumanLegalReviewWorkflow",
    "LegalConsolidationEngine",
    # Exceptions
    "SourceVerificationError",
    "UnverifiableSourceError",
    "SourceIntegrityError",
    "GovernanceReviewError",
    "UnauthorizedLegalAssertionError",
]

