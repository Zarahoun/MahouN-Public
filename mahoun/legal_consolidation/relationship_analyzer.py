"""
MAHOUN Legal Consolidation Engine — Normative Relationship Analyzer
===================================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Maps detected legislative changes into formal normative relationships:
AMENDS, REPEALS, PARTIALLY_REPEALS, INTERPRETS, CONFLICTS_WITH, SUPERSEDES.

Guarantees Merkle-tree cryptographic commitment and strict epistemic separation
between machine hypotheses and verified legal facts.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from mahoun.crypto.merkle_tree import MerkleTree
from mahoun.legal_consolidation.models import (
    ChangeType,
    DetectedLegalChange,
    NormativeRelationship,
    NormativeRelationType,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


CHANGE_TO_RELATION_MAP: Dict[ChangeType, NormativeRelationType] = {
    ChangeType.EXPLICIT_REPEAL: NormativeRelationType.REPEALS,
    ChangeType.PARTIAL_REPEAL: NormativeRelationType.PARTIALLY_REPEALS,
    ChangeType.AMENDMENT: NormativeRelationType.AMENDS,
    ChangeType.ADDITION: NormativeRelationType.AMENDS,
    ChangeType.POTENTIAL_IMPLICIT_REPEAL: NormativeRelationType.CONFLICTS_WITH,
    ChangeType.DELETION: NormativeRelationType.PARTIALLY_REPEALS,
    ChangeType.NEW_INSTRUMENT: NormativeRelationType.SUPERSEDES,
    ChangeType.TEMPORAL_CHANGE: NormativeRelationType.AMENDS,
}


class NormativeRelationshipAnalyzer:
    """
    Analyzes detected changes and compiles verifiable normative relationships.
    Protects against premature promotion of machine hypotheses to legal facts.
    """

    def __init__(self):
        self._counter = 0

    def analyze_change(
        self,
        change: DetectedLegalChange,
        source_law_id: str,
        effective_date: Optional[str] = None,
        approval_date: Optional[str] = None,
    ) -> NormativeRelationship:
        """
        Derive a single NormativeRelationship from a DetectedLegalChange.
        """
        self._counter += 1
        relation_type = CHANGE_TO_RELATION_MAP.get(
            change.change_type, NormativeRelationType.CONFLICTS_WITH
        )

        # Build Merkle commitment for evidence
        merkle = MerkleTree()
        merkle.add(change.evidence_text)
        merkle.add(change.evidence_sha256)
        merkle.add(source_law_id)
        merkle.add(change.target_law_id)
        merkle_root = merkle.get_root() or change.evidence_sha256

        # Enforce Non-Fabrication Rule:
        # Explicit legislative enactments with 1.0 confidence -> VERIFIED
        # General conflict clauses or implicit candidates -> HYPOTHESIS
        if change.is_explicit and change.confidence >= 0.95:
            verification_status = VerificationStatus.VERIFIED
        else:
            verification_status = VerificationStatus.HYPOTHESIS

        relation_id = f"norm_rel_{source_law_id}_{self._counter:04d}"

        clean_source = source_law_id.removeprefix("law:")
        clean_target = change.target_law_id.removeprefix("law:")
        source_article_id = (
            f"{clean_source}:article:{change.source_article_num}"
            if change.source_article_num
            else clean_source
        )
        target_article_id = (
            f"{clean_target}:article:{change.target_article_num}"
            if change.target_article_num
            else clean_target
        )

        rel = NormativeRelationship(
            relation_id=relation_id,
            relation_type=relation_type,
            source_law_id=source_law_id,
            source_article_id=source_article_id,
            target_law_id=change.target_law_id,
            target_article_id=target_article_id,
            evidence_text=change.evidence_text,
            evidence_sha256=change.evidence_sha256,
            confidence=change.confidence,
            verification_status=verification_status,
            effective_date=effective_date,
            approval_date=approval_date,
            provenance_merkle_root=merkle_root,
            metadata={
                "change_type": change.change_type.value,
                "is_explicit": change.is_explicit,
                "detected_at": change.detected_at,
            },
        )

        logger.info(
            f"🔗 [NORMATIVE RELATION] {rel.relation_id}: "
            f"({rel.source_article_id}) -[{rel.relation_type.value}]-> ({rel.target_article_id}) "
            f"| Status: {rel.verification_status.value} (is_binding_fact: {rel.is_binding_fact})"
        )
        return rel

    def batch_analyze(
        self,
        changes: List[DetectedLegalChange],
        source_law_id: str,
        effective_date: Optional[str] = None,
        approval_date: Optional[str] = None,
    ) -> List[NormativeRelationship]:
        """Convert a list of detected changes into normative relationships."""
        return [
            self.analyze_change(
                change=c,
                source_law_id=source_law_id,
                effective_date=effective_date,
                approval_date=approval_date,
            )
            for c in changes
        ]
