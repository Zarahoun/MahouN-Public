"""
MAHOUN Legal Consolidation Engine — Unified Orchestrator
========================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Integrates the five core pillars of the consolidation system:
1. Legal Source Monitoring (authenticity, source hashing, fail-closed access check)
2. Legal Change Detection (amendments, repeals, additions, deletions, conflict clauses)
3. Normative Relationship Analysis (AMENDS, REPEALS, CONFLICTS_WITH, Merkle roots)
4. Temporal Legal Validation (article version chains, point-in-time validity [valid_from, valid_until))
5. Human Legal Review & Governance (quarantine uncertain inferences, fail-closed gate)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mahoun.crypto.merkle_tree import MerkleTree
from mahoun.legal_consolidation.change_detector import LegalChangeDetector
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
    VerificationStatus,
)
from mahoun.legal_consolidation.relationship_analyzer import (
    NormativeRelationshipAnalyzer,
)
from mahoun.legal_consolidation.review_workflow import (
    HumanLegalReviewWorkflow,
    UnauthorizedLegalAssertionError,
)
from mahoun.legal_consolidation.source_monitor import LegalSourceMonitor
from mahoun.legal_consolidation.temporal_engine import TemporalValidationEngine

logger = logging.getLogger(__name__)


class LegalConsolidationEngine:
    """
    Unified orchestrator for continuous, evidence-based legal consolidation.
    Provides temporal validity queries, change detection, and governed graph mutations.
    """

    def __init__(
        self,
        monitor: Optional[LegalSourceMonitor] = None,
        change_detector: Optional[LegalChangeDetector] = None,
        relationship_analyzer: Optional[NormativeRelationshipAnalyzer] = None,
        temporal_engine: Optional[TemporalValidationEngine] = None,
        review_workflow: Optional[HumanLegalReviewWorkflow] = None,
    ):
        self.monitor = monitor or LegalSourceMonitor()
        self.change_detector = change_detector or LegalChangeDetector()
        self.relationship_analyzer = relationship_analyzer or NormativeRelationshipAnalyzer()
        self.temporal_engine = temporal_engine or TemporalValidationEngine()
        self.review_workflow = review_workflow or HumanLegalReviewWorkflow()
        self._run_counter = 0

    def process_enactment(
        self,
        source_doc: MonitoredSourceDocument,
        source_law_id: str,
        effective_date: Optional[str] = None,
        approval_date: Optional[str] = None,
        auto_apply_temporal: bool = True,
    ) -> ConsolidationRunReceipt:
        """
        Execute full consolidation pipeline for an ingested statutory enactment:
        1. Scan text for legislative modifications.
        2. Map changes to normative relationships with Merkle proofs.
        3. Segregate verified statutory facts from uncertain machine hypotheses.
        4. Enqueue uncertain hypotheses to the certified jurist review queue.
        5. Update temporal article lifecycles for verified changes (if registered).
        6. Produce an immutable ConsolidationRunReceipt.
        """
        self._run_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Detect legislative changes
        changes: List[DetectedLegalChange] = self.change_detector.detect_changes_in_document(source_doc)

        # Step 2: Derive normative relationships
        relationships: List[NormativeRelationship] = self.relationship_analyzer.batch_analyze(
            changes=changes,
            source_law_id=source_law_id,
            effective_date=effective_date,
            approval_date=approval_date,
        )

        verified_relations: List[NormativeRelationship] = []
        queued_items: List[HumanReviewItem] = []

        # Step 3 & 4: Epistemic segregation & review queue routing
        for rel in relationships:
            if rel.verification_status == VerificationStatus.VERIFIED and rel.is_binding_fact:
                verified_relations.append(rel)
                # If auto_apply_temporal and target article exists in temporal engine
                if auto_apply_temporal and effective_date:
                    target_art_id = rel.target_article_id
                    history = self.temporal_engine.get_full_version_history(target_art_id)
                    if not history:
                        if ":article:" in target_art_id:
                            alt = target_art_id.replace(":article:", ":art:")
                            if self.temporal_engine.get_full_version_history(alt):
                                target_art_id = alt
                                history = self.temporal_engine.get_full_version_history(target_art_id)
                        elif ":art:" in target_art_id:
                            alt = target_art_id.replace(":art:", ":article:")
                            if self.temporal_engine.get_full_version_history(alt):
                                target_art_id = alt
                                history = self.temporal_engine.get_full_version_history(target_art_id)
                    if history:
                        if rel.relation_type == NormativeRelationType.AMENDS:
                            # Amend with updated reference text
                            self.temporal_engine.apply_normative_amendment(
                                article_id=target_art_id,
                                new_text=f"متن اصلاحی طبق سند {source_law_id}: {rel.evidence_text}",
                                effective_date=effective_date,
                                relationship=rel,
                                approval_date=approval_date,
                            )
                        elif rel.relation_type == NormativeRelationType.REPEALS:
                            self.temporal_engine.apply_normative_repeal(
                                article_id=target_art_id,
                                effective_date=effective_date,
                                relationship=rel,
                                is_partial=False,
                            )
                        elif rel.relation_type == NormativeRelationType.PARTIALLY_REPEALS:
                            self.temporal_engine.apply_normative_repeal(
                                article_id=target_art_id,
                                effective_date=effective_date,
                                relationship=rel,
                                is_partial=True,
                                repealed_portion_text=rel.evidence_text,
                            )
            else:
                # Machine hypothesis or ambiguous repeal -> MUST NOT become legal fact without review
                review_item = HumanReviewItem(
                    review_id=f"rev_{source_law_id}_{len(queued_items) + 1:04d}",
                    target_type="RELATIONSHIP",
                    item_id=rel.relation_id,
                    original_evidence=rel.evidence_text,
                    evidence_sha256=rel.evidence_sha256,
                    proposed_assertion={
                        "relation_type": rel.relation_type.value,
                        "source_article": rel.source_article_id,
                        "target_article": rel.target_article_id,
                        "effective_date": rel.effective_date,
                    },
                    temporal_impact_summary=(
                        f"Potential normative effect on {rel.target_article_id} "
                        f"by {rel.source_article_id} via {rel.relation_type.value}"
                    ),
                    reasoning="Unverified machine extraction or general conflict clause; requires certified jurist adjudication.",
                    confidence=rel.confidence,
                    status=ReviewDecision.PENDING,
                )
                self.review_workflow.submit_for_review(review_item)
                queued_items.append(review_item)

        # Step 5: Merkle Tree commitment over run artifacts
        merkle = MerkleTree()
        merkle.add(source_doc.source_id)
        merkle.add(source_doc.content_sha256)
        for r in verified_relations:
            merkle.add(r.relation_id)
            merkle.add(r.provenance_merkle_root)
        for q in queued_items:
            merkle.add(q.review_id)
            merkle.add(q.evidence_sha256)

        run_merkle_root = merkle.get_root() or hashlib.sha256(now_iso.encode("utf-8")).hexdigest()

        receipt = ConsolidationRunReceipt(
            receipt_id=f"receipt_{source_law_id}_{self._run_counter:04d}",
            source_doc_id=source_doc.source_id,
            source_law_id=source_law_id,
            detected_changes_count=len(changes),
            verified_relationships=tuple(verified_relations),
            queued_for_review_items=tuple(queued_items),
            consolidation_merkle_root=run_merkle_root,
            processed_at=now_iso,
        )

        logger.info(
            f"✅ [CONSOLIDATION CYCLE COMPLETE] {receipt.receipt_id} | "
            f"Changes: {receipt.detected_changes_count} | Verified: {len(verified_relations)} | "
            f"Queued: {len(queued_items)} | Merkle: {run_merkle_root[:12]}..."
        )
        return receipt

    def query_point_in_time(
        self, article_id: str, as_of_date: str
    ) -> Optional[ArticleTemporalVersion]:
        """
        Query the temporally applicable version of an article at a specific historical date.
        """
        res = self.temporal_engine.get_article_at_date(article_id, as_of_date)
        if not res:
            if ":article:" in article_id:
                alt = article_id.replace(":article:", ":art:")
                res = self.temporal_engine.get_article_at_date(alt, as_of_date)
            elif ":art:" in article_id:
                alt = article_id.replace(":art:", ":article:")
                res = self.temporal_engine.get_article_at_date(alt, as_of_date)
        return res

    def query_status_at_date(self, article_id: str, as_of_date: str) -> LegalStatus:
        """
        Query the formal legal status (ACTIVE, AMENDED, EXPLICITLY_REPEALED, etc.)
        at a specific historical date.
        """
        res = self.temporal_engine.get_article_status_at_date(article_id, as_of_date)
        if res == LegalStatus.UNVERIFIED:
            if ":article:" in article_id:
                alt = article_id.replace(":article:", ":art:")
                res = self.temporal_engine.get_article_status_at_date(alt, as_of_date)
            elif ":art:" in article_id:
                alt = article_id.replace(":art:", ":article:")
                res = self.temporal_engine.get_article_status_at_date(alt, as_of_date)
        return res

    def compile_governed_mutation_payload(
        self,
        approved_relations: List[NormativeRelationship],
        author_id: str,
    ) -> Dict[str, Any]:
        """
        Compile Cypher mutations for persistence into the legal knowledge graph.

        FAIL-CLOSED GOVERNANCE ENFORCEMENT:
        Every relationship must satisfy `assert_authorized_for_graph`.
        If ANY relationship is unverified and not approved by a jurist,
        the entire compilation is rejected immediately.
        """
        for rel in approved_relations:
            self.review_workflow.assert_authorized_for_graph(rel)

        mutations = []
        for rel in approved_relations:
            cypher = (
                f"MATCH (a:Article {{id: $source_id}}) "
                f"MATCH (b:Article {{id: $target_id}}) "
                f"MERGE (a)-[r:{rel.relation_type.value}]->(b) "
                f"ON CREATE SET r.created_at = datetime() "
                f"SET r.relation_id = $relation_id, "
                f"r.evidence_sha256 = $evidence_sha256, "
                f"r.provenance_merkle_root = $merkle_root, "
                f"r.confidence = $confidence, "
                f"r.verification_status = $status, "
                f"r.effective_date = $effective_date, "
                f"r.author_id = $author_id, "
                f"r.updated_at = datetime()"
            )
            params = {
                "source_id": rel.source_article_id,
                "target_id": rel.target_article_id,
                "relation_id": rel.relation_id,
                "evidence_sha256": rel.evidence_sha256,
                "merkle_root": rel.provenance_merkle_root,
                "confidence": rel.confidence,
                "status": rel.verification_status.value,
                "effective_date": rel.effective_date,
                "author_id": author_id,
            }
            mutations.append({
                "relation_id": rel.relation_id,
                "relation_type": rel.relation_type.value,
                "source_id": rel.source_article_id,
                "target_id": rel.target_article_id,
                "query": cypher,
                "parameters": params,
            })

        payload_bytes = json.dumps(mutations, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        return {
            "author_id": author_id,
            "relations_count": len(mutations),
            "compiled_mutations": mutations,
            "payload_hash": payload_hash,
            "compiled_at": datetime.now(timezone.utc).isoformat(),
        }

    def apply_to_governed_session(
        self,
        session: Any,
        approved_relations: List[NormativeRelationship],
        author_id: str,
    ) -> List[Any]:
        """
        Persist approved normative relationships to the Neo4j graph strictly
        via the caller's active GovernedNeo4jSession.
        """
        for rel in approved_relations:
            self.review_workflow.assert_authorized_for_graph(rel)

        receipts = []
        for rel in approved_relations:
            receipt = session.write_relationship(
                source_type="Article",
                source_id=rel.source_article_id,
                relationship_type=rel.relation_type.value,
                target_type="Article",
                target_id=rel.target_article_id,
                relationship_data={
                    "relation_id": rel.relation_id,
                    "evidence_sha256": rel.evidence_sha256,
                    "provenance_merkle_root": rel.provenance_merkle_root,
                    "effective_date": rel.effective_date,
                    "confidence": rel.confidence,
                    "verification_status": rel.verification_status.value,
                    "author_id": author_id,
                },
                merge=True,
            )
            receipts.append(receipt)

        logger.info(f"💾 [GOVERNED PERSISTENCE] Persisted {len(receipts)} normative relationships.")
        return receipts
