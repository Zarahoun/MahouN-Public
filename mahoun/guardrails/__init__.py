"""
MAHOUN Guardrails Module - Enterprise Edition (Ultra Only)
===========================================================

Ultra-advanced guardrails for generated content verification.

Components (Ultra Edition):
- UltraNLIVerifier: Advanced natural language inference validation
- UltraCitationAuditor: Enterprise-grade citation verification
- Note: Legacy basic modules removed - only Ultra modules available

Note: Some components require torch. Graceful degradation is provided.
"""
from typing import Any, Optional

__version__ = "2.0.0-enterprise"

import logging
logger = logging.getLogger(__name__)

# Ultra imports only
try:
    from .ultra_nli_verifier import UltraNLIVerifier, UltraNLIResult
except ImportError as e:
    logger.debug(f"Ultra NLI Verifier not available: {e}")
    UltraNLIVerifier: Optional[Any] = None
    UltraNLIResult: Optional[Any] = None
try:
    from .ultra_citation_auditor import UltraCitationAuditor, UltraCitationAuditResult
except ImportError as e:
    logger.debug(f"Ultra Citation Auditor not available: {e}")
    UltraCitationAuditor: Optional[Any] = None
    UltraCitationAuditResult: Optional[Any] = None
# Backward compatibility aliases (pointing to Ultra versions)
NLIVerifier = UltraNLIVerifier
NLIResult = UltraNLIResult
CitationAuditor = UltraCitationAuditor
CitationAuditResult = UltraCitationAuditResult

__all__ = [
    # Ultra modules
    "UltraNLIVerifier",
    "UltraNLIResult",
    "UltraCitationAuditor",
    "UltraCitationAuditResult",
    # Backward compatibility aliases
    "NLIVerifier",
    "NLIResult",
    "CitationAuditor",
    "CitationAuditResult",
]
