"""
Governed Neo4j Persistence Adapter for Legal Consolidation Engine
================================================================

Classification: LEGAL CONSOLIDATION / NEO4J PERSISTENCE
Governed under MAHOUN V2 Constitutional Authority.

Enforces:
1. Strict routing through GovernedNeo4jSession (fail-closed).
2. Provenance generation for every persisted normative relationship.
3. Only binding statutory facts (VERIFIED) are materialized into the graph.
4. Updates target article status and validity intervals upon repeal or amendment.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.violations import (
    GovernanceViolation,
    GovernanceViolationError,
    ViolationCategory,
    ViolationSeverity,
)
from mahoun.graph.neo4j.connection import Neo4jConnection, get_connection
from mahoun.legal_consolidation.models import (
    ConsolidationRunReceipt,
    NormativeRelationship,
    NormativeRelationType,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class GovernedConsolidationPersistenceAdapter:
    """
    Adapter that materializes verified normative relationships and temporal lifecycle
    updates produced by the LegalConsolidationEngine into Neo4j via GovernedNeo4jSession.
    """

    def __init__(self, connection: Optional[Neo4jConnection] = None):
        self._connection = connection or get_connection()

    def persist_consolidation_receipt(
        self,
        receipt: ConsolidationRunReceipt,
        actor_id: str = "system:consolidation_engine",
    ) -> Dict[str, Any]:
        """
        Persist all verified relationships from a ConsolidationRunReceipt to Neo4j.
        Machine hypotheses and unverified items are NEVER materialized to the graph.
        """
        ctx = GovernanceContextManager.get_current_context()
        if ctx is None:
            raise GovernanceViolationError(
                GovernanceViolation(
                    category=ViolationCategory.GOVERNANCE_BYPASS,
                    severity=ViolationSeverity.CRITICAL,
                    message="Consolidation persistence requires an active governance context",
                    details={"receipt_id": receipt.receipt_id},
                    source="GovernedConsolidationPersistenceAdapter.persist_consolidation_receipt",
                )
            )

        persisted_count = 0
        status_updates_count = 0

        with self._connection.governed_session(
            correlation_id=receipt.receipt_id,
            actor_id=actor_id,
        ) as session:
            for rel in receipt.verified_relationships:
                # Constitutional invariant: Only verified binding facts reach Neo4j
                if not (rel.verification_status == VerificationStatus.VERIFIED and rel.is_binding_fact):
                    continue

                source_type = "LawArticle" if (":article:" in rel.source_article_id or ":art:" in rel.source_article_id) else "Document"
                target_type = "LawArticle" if (":article:" in rel.target_article_id or ":art:" in rel.target_article_id) else "Document"

                # 1. Ensure source node exists under governed session before writing relationship
                ensure_src_query = (
                    f"MERGE (s:{source_type} {{id: $source_id}}) "
                    f"ON CREATE SET s.created_at = datetime(), s.source_law_id = $source_law_id"
                )
                session.execute_cypher(
                    ensure_src_query,
                    {
                        "source_id": rel.source_article_id,
                        "source_law_id": rel.source_law_id,
                    },
                )

                # 2. Establish provenance metadata
                provenance_meta = GovernanceContextManager.require_provenance(
                    source=f"consolidation_engine:{receipt.receipt_id}",
                    author=actor_id,
                )
                prov_dict = provenance_meta.to_dict() if hasattr(provenance_meta, "to_dict") else provenance_meta

                rel_data = {
                    "relation_id": rel.relation_id,
                    "relation_type": rel.relation_type.value,
                    "effective_date": rel.effective_date or "",
                    "approval_date": rel.approval_date or "",
                    "evidence_text": rel.evidence_text[:500],
                    "evidence_sha256": rel.evidence_sha256,
                    "provenance_merkle_root": rel.provenance_merkle_root,
                    "is_binding_fact": True,
                    "verification_status": "VERIFIED",
                    "provenance": prov_dict,
                }

                # 3. Write governed relationship
                session.write_relationship(
                    source_type=source_type,
                    source_id=rel.source_article_id,
                    relationship_type=rel.relation_type.value,
                    target_type=target_type,
                    target_id=rel.target_article_id,
                    rel_data=rel_data,
                    merge=True,
                )

                # Verify relationship was created in graph using read query via connection
                verify_query = (
                    f"MATCH (a:{source_type} {{id: $__src}})-[r:{rel.relation_type.value}]->(b:{target_type} {{id: $__tgt}}) "
                    f"RETURN count(r) as rel_count"
                )
                v_res = self._connection.execute_query(
                    verify_query,
                    {"__src": rel.source_article_id, "__tgt": rel.target_article_id},
                )
                if v_res and v_res[0].get("rel_count", 0) > 0:
                    persisted_count += 1

                # 4. Update temporal lifecycle properties on target article
                if rel.relation_type == NormativeRelationType.REPEALS:
                    update_query = (
                        f"MATCH (a:{target_type} {{id: $target_id}}) "
                        f"SET a.status = 'REPEALED', a.valid_until = $effective_date, "
                        f"a.repealed_by = $source_id, a.updated_at = datetime() "
                        f"RETURN count(a) as matched_count"
                    )
                    res = session.execute_cypher(
                        update_query,
                        {
                            "target_id": rel.target_article_id,
                            "effective_date": rel.effective_date or "",
                            "source_id": rel.source_article_id,
                        },
                    )
                    if res and res[0].get("matched_count", 0) > 0:
                        status_updates_count += res[0]["matched_count"]
                elif rel.relation_type == NormativeRelationType.AMENDS:
                    update_query = (
                        f"MATCH (a:{target_type} {{id: $target_id}}) "
                        f"SET a.status = 'AMENDED', a.amended_by = $source_id, "
                        f"a.updated_at = datetime() "
                        f"RETURN count(a) as matched_count"
                    )
                    res = session.execute_cypher(
                        update_query,
                        {
                            "target_id": rel.target_article_id,
                            "source_id": rel.source_article_id,
                        },
                    )
                    if res and res[0].get("matched_count", 0) > 0:
                        status_updates_count += res[0]["matched_count"]

        logger.info(
            f"✅ [GOVERNED PERSISTENCE COMPLETE] Receipt: {receipt.receipt_id} | "
            f"Persisted Rels: {persisted_count} | Status Updates: {status_updates_count}"
        )

        return {
            "receipt_id": receipt.receipt_id,
            "persisted_relationships": persisted_count,
            "updated_articles": status_updates_count,
            "merkle_root": receipt.consolidation_merkle_root,
        }
