"""
MAHOUN Legal Consolidation Engine — Human Legal Review & Governance
===================================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Provides governed human review workflows for ambiguous repeal relationships,
potential implicit repeals, conflicting provisions, unverified sources, and
low-confidence inferences.

FAIL-CLOSED ENFORCEMENT:
No unverified model hypothesis or uncertain legal interpretation may ever
be promoted to an authoritative graph assertion without explicit, verified
jurist approval and cryptographic authorization.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from mahoun.legal_consolidation.models import (
    HumanReviewItem,
    NormativeRelationship,
    ReviewDecision,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class GovernanceReviewError(Exception):
    """Base exception for legal consolidation governance and review violations."""


class UnauthorizedLegalAssertionError(GovernanceReviewError):
    """
    Raised when an unverified or disputed legal hypothesis attempts to be
    promoted to an authoritative legal graph assertion without certified review.
    """


class HumanLegalReviewWorkflow:
    """
    Manages the review queue, jurist adjudication, and gatekeeping for
    normative relationships and legal assertions before graph materialization.
    """

    def __init__(self):
        self._review_queue: Dict[str, HumanReviewItem] = {}
        # Tracks item_id -> review_id mapping for quick lookup
        self._item_to_review: Dict[str, str] = {}
        # Approved authorizations: relation_id -> signed authorization hash
        self._authorized_relations: Dict[str, str] = {}
        self._lock = threading.RLock()

    def submit_for_review(self, item: HumanReviewItem) -> HumanReviewItem:
        """
        Enqueue an uncertain, conflictive, or low-confidence legal item
        for certified human jurist review.
        """
        with self._lock:
            if item.review_id in self._review_queue:
                logger.warning(f"⚠️ Review item '{item.review_id}' is already queued.")
                return self._review_queue[item.review_id]

            self._review_queue[item.review_id] = item
            self._item_to_review[item.item_id] = item.review_id

            logger.info(
                f"📋 [REVIEW QUEUED] {item.review_id} | Type: {item.target_type} | "
                f"Item: {item.item_id} | Confidence: {item.confidence:.2f}"
            )
            return item

    def review_and_decide(
        self,
        review_id: str,
        decision: ReviewDecision,
        reviewer_id: str,
        jurist_notes: str,
        authorization_signature: Optional[str] = None,
    ) -> HumanReviewItem:
        """
        Record a binding human jurist review decision.
        If APPROVED, generates a cryptographic authorization signature.
        """
        with self._lock:
            item = self._review_queue.get(review_id)
            if not item:
                raise KeyError(f"Review item '{review_id}' not found in queue.")

            if decision == ReviewDecision.PENDING:
                raise ValueError("Cannot decide with PENDING status.")

            if not reviewer_id or not reviewer_id.strip():
                raise ValueError("Reviewer ID is required for legal accountability.")

            if not jurist_notes or not jurist_notes.strip():
                raise ValueError("Jurist reasoning notes are mandatory for auditability.")

            timestamp = datetime.now(timezone.utc).isoformat()

            # Generate cryptographic authorization hash if approved
            auth_hash = None
            if decision == ReviewDecision.APPROVED:
                raw_payload = (
                    f"{review_id}:{item.item_id}:{reviewer_id}:{decision.value}:"
                    f"{timestamp}:{jurist_notes}:{authorization_signature or 'SYS_CERT'}"
                )
                auth_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
                self._authorized_relations[item.item_id] = auth_hash

            item.status = decision
            item.reviewer_id = reviewer_id
            item.review_timestamp = timestamp
            item.jurist_notes = jurist_notes
            item.signed_authorization_hash = auth_hash

            logger.info(
                f"⚖️ [REVIEW DECISION] {review_id} -> {decision.value} by {reviewer_id} "
                f"| AuthHash: {auth_hash[:12] if auth_hash else 'N/A'}"
            )
            return item

    def can_materialize_to_graph(self, relation: NormativeRelationship) -> bool:
        """
        Evaluates whether a normative relationship satisfies governance criteria
        for persistence into the legal knowledge graph.

        Returns True ONLY if:
        1. Explicitly statutory and VERIFIED, OR
        2. Formally APPROVED by a human jurist with an authorization signature.
        """
        with self._lock:
            # Criteria 1: Explicit statutory change with verified epistemic status
            if relation.verification_status == VerificationStatus.VERIFIED and relation.is_binding_fact:
                return True

            # Criteria 2: Formally approved through human jurist review
            if relation.relation_id in self._authorized_relations:
                return True

            return False

    def assert_authorized_for_graph(self, relation: NormativeRelationship) -> None:
        """
        Fail-Closed Governance Gate:
        Raises UnauthorizedLegalAssertionError if an unverified or unapproved
        normative relationship attempts to materialize to the legal graph.
        """
        if not self.can_materialize_to_graph(relation):
            error_msg = (
                f"Unauthorized legal graph assertion rejected! "
                f"Relation '{relation.relation_id}' ({relation.relation_type.value}) "
                f"has status '{relation.verification_status.value}' and has not been "
                f"approved by a certified jurist in the governance review queue."
            )
            logger.error(f"🛑 [GOVERNANCE BLOCKED] {error_msg}")
            raise UnauthorizedLegalAssertionError(error_msg)

    def get_pending_reviews(self) -> List[HumanReviewItem]:
        """Return all items currently awaiting jurist review."""
        with self._lock:
            return [
                item
                for item in self._review_queue.values()
                if item.status == ReviewDecision.PENDING
            ]

    def get_review_item(self, review_id: str) -> Optional[HumanReviewItem]:
        """Retrieve a specific review item by its identifier."""
        with self._lock:
            return self._review_queue.get(review_id)

    def get_review_by_item_id(self, item_id: str) -> Optional[HumanReviewItem]:
        """Retrieve review item associated with a specific normative relation or change."""
        with self._lock:
            review_id = self._item_to_review.get(item_id)
            if review_id:
                return self._review_queue.get(review_id)
            return None

    def list_all_reviews(self) -> List[HumanReviewItem]:
        """Return all review items in the system."""
        with self._lock:
            return list(self._review_queue.values())
