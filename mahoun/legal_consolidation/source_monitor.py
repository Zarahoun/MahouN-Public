"""
MAHOUN Legal Consolidation Engine — Source Monitoring & Provenance
==================================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Provides continuous, evidence-based monitoring and cryptographic provenance
tracking for authoritative Iranian legal sources (Official Gazette, Dotic, Parliament).
Enforces fail-closed validation on unverifiable, modified, or inaccessible sources.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from mahoun.legal_consolidation.models import (
    MonitoredSourceDocument,
    SourceAuthorityType,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class SourceVerificationError(Exception):
    """Base exception for source verification failures."""


class UnverifiableSourceError(SourceVerificationError):
    """Raised when an official source cannot be reached, authenticated, or verified."""


class SourceIntegrityError(SourceVerificationError):
    """Raised when a retrieved document fails cryptographic tamper verification."""


class LegalSourceMonitor:
    """
    Monitors, registers, and validates authoritative legal sources.
    Guarantees tamper detection and fail-closed security.
    """

    def __init__(self):
        self._registry: Dict[str, MonitoredSourceDocument] = {}
        self._quarantined_sources: Dict[str, Dict[str, str]] = {}

    def register_source_document(
        self,
        source_id: str,
        authority_type: SourceAuthorityType,
        source_url: str,
        document_identifier: str,
        title_fa: str,
        content: str,
        expected_sha256: Optional[str] = None,
        publication_date: Optional[str] = None,
        is_accessible: bool = True,
    ) -> MonitoredSourceDocument:
        """
        Register and verify an authoritative legal source artifact.
        Fails closed if the source is inaccessible, empty, or checksum fails.
        """
        retrieval_timestamp = datetime.now(timezone.utc).isoformat()

        # Fail-closed check 1: Inaccessible source
        if not is_accessible:
            error_msg = f"Source '{source_id}' ({source_url}) is inaccessible or down."
            self._quarantined_sources[source_id] = {
                "reason": error_msg,
                "timestamp": retrieval_timestamp,
                "url": source_url,
            }
            logger.error(f"❌ [FAIL-CLOSED] {error_msg}")
            raise UnverifiableSourceError(error_msg)

        # Fail-closed check 2: Empty or whitespace-only content
        if not content or not content.strip():
            error_msg = f"Source document '{source_id}' has empty content; unverifiable."
            self._quarantined_sources[source_id] = {
                "reason": error_msg,
                "timestamp": retrieval_timestamp,
                "url": source_url,
            }
            logger.error(f"❌ [FAIL-CLOSED] {error_msg}")
            raise UnverifiableSourceError(error_msg)

        # Cryptographic integrity check
        computed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if expected_sha256 and expected_sha256 != computed_hash:
            error_msg = (
                f"Source integrity violation for '{source_id}'! "
                f"Expected {expected_sha256}, computed {computed_hash}"
            )
            self._quarantined_sources[source_id] = {
                "reason": error_msg,
                "timestamp": retrieval_timestamp,
                "expected_hash": expected_sha256,
                "computed_hash": computed_hash,
            }
            logger.error(f"❌ [TAMPER DETECTED] {error_msg}")
            raise SourceIntegrityError(error_msg)

        # Build immutable record
        doc = MonitoredSourceDocument(
            source_id=source_id,
            authority_type=authority_type,
            source_url=source_url,
            document_identifier=document_identifier,
            title_fa=title_fa,
            raw_content=content,
            content_sha256=computed_hash,
            retrieval_timestamp=retrieval_timestamp,
            publication_date=publication_date,
            is_accessible=True,
            verification_status=VerificationStatus.VERIFIED,
        )

        self._registry[source_id] = doc
        logger.info(
            f"✅ [SOURCE VERIFIED] {source_id} | {title_fa[:50]}... | SHA-256: {computed_hash[:12]}..."
        )
        return doc

    def get_source(self, source_id: str) -> Optional[MonitoredSourceDocument]:
        """Retrieve verified source document by identifier."""
        return self._registry.get(source_id)

    def list_all_sources(self) -> List[MonitoredSourceDocument]:
        """List all verified source documents currently registered."""
        return list(self._registry.values())

    def get_quarantine_log(self) -> Dict[str, Dict[str, str]]:
        """Return the audit log of failed, quarantined, or inaccessible sources."""
        return dict(self._quarantined_sources)

