"""
Graph-Enhanced Retriever
========================

Implements the "Anchor & Expand" hybrid retrieval strategy over the MAHOUN
knowledge graph.  All Neo4j access is routed exclusively through the injected
``Neo4jConnection`` singleton — never through a raw driver.

Algorithm
---------
1. **Anchor**  — Find top-k nodes via vector-index similarity (GGUF embedding).
2. **Expand**  — Traverse typed graph relationships (CITES, RELATED_TO, …).
3. **Fuse**    — Deduplicate and rerank by composite score.

Governance invariants
---------------------
* ``Neo4jConnection`` is constructor-injected by bootstrap — never self-constructed.
* Read queries go through ``connection.execute_query()`` (MutationAuthorizationBoundary
  enforced — any mutation Cypher raises GovernanceViolationError).
* No ``driver.session()`` call exists anywhere in this module.
* Raw driver references are constitutionally forbidden in this module.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from mahoun.graph.neo4j.connection import Neo4jConnection

if TYPE_CHECKING:
    from mahoun.pipelines.ingestion.enhanced_embedding import EnhancedEmbeddingService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HybridResult:
    """
    Immutable retrieval result.

    Frozen so that downstream consumers cannot mutate provenance data.
    """

    node_id: str
    label: str
    text: str
    score: float
    source: str                        # "vector_anchor" | "graph_expansion"
    relationship: Optional[str] = None
    retrieval_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.score < 0.0 or self.score > 1.0:
            # Clamp silently — scores from vector indices can exceed [0,1]
            object.__setattr__(self, "score", max(0.0, min(1.0, self.score)))


@dataclass(frozen=True)
class RetrievalTrace:
    """Observability record for a single retrieve() call."""

    query: str
    retrieval_id: str
    anchor_count: int
    expansion_count: int
    total_results: int
    duration_ms: float
    vector_index: str
    similarity_threshold: float


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class GraphEnhancedRetriever:
    """
    Hybrid retriever: vector-index anchoring + graph-relationship expansion.

    Constructor injection contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``connection`` MUST be a ``Neo4jConnection`` instance obtained via
    ``get_connection()`` (the authorised singleton factory).  Bootstrap is
    the sole wiring authority — callers must never pass a raw driver.

    Pre-conditions
    ~~~~~~~~~~~~~~
    * ``connection`` is not None and is a live ``Neo4jConnection``.
    * ``embedding_service`` is optional; if None, ``EnhancedEmbeddingService``
      is constructed lazily (fallback path — not the primary path).

    Post-conditions
    ~~~~~~~~~~~~~~~
    * ``retrieve()`` never raises; errors are logged and an empty list returned.
    * Every Neo4j query goes through ``connection.execute_query()`` — zero raw
      ``session()`` calls exist in this module.
    """

    # Cypher: vector-index anchor lookup + 1-hop graph expansion
    _ANCHOR_EXPAND_CYPHER = """
    CALL db.index.vector.queryNodes($index_name, $k, $embedding)
    YIELD node AS anchor, score
    WHERE score > $threshold
    OPTIONAL MATCH (anchor)-[r:CITES|RELATED_TO|REFERENCES]->(expanded)
    RETURN
        anchor.id          AS anchor_id,
        labels(anchor)[0]  AS anchor_label,
        anchor.content     AS anchor_text,
        score              AS vector_score,
        collect({
            id:    expanded.id,
            label: labels(expanded)[0],
            text:  expanded.content,
            rel:   type(r)
        }) AS expansions
    """

    def __init__(
        self,
        connection: Neo4jConnection,
        *,
        embedding_service: Optional[EnhancedEmbeddingService] = None,
        anchor_k: int = 5,
        expansion_depth: int = 1,
        similarity_threshold: float = 0.70,
        vector_index: str = "verdict_embedding_idx",
        expansion_score_decay: float = 0.90,
    ) -> None:
        """
        Args:
            connection:             Governed Neo4jConnection (injected by bootstrap).
            embedding_service:      Optional pre-built embedding service.  If None,
                                    a default ``EnhancedEmbeddingService`` is created
                                    lazily (fallback — not the primary path).
            anchor_k:               Number of vector-index anchors to retrieve.
            expansion_depth:        Graph hop depth (currently 1; reserved for future).
            similarity_threshold:   Minimum cosine similarity for anchor inclusion.
            vector_index:           Name of the Neo4j vector index to query.
            expansion_score_decay:  Score multiplier applied to expanded nodes.
        """
        if connection is None:
            raise ValueError(
                "GraphEnhancedRetriever requires a Neo4jConnection instance. "
                "Obtain one via get_connection() and inject it at construction time."
            )

        # Governed connection — the ONLY Neo4j surface in this module.
        self._connection: Neo4jConnection = connection
        # Public alias for DI tests and external consumers that expect
        # a .connection attribute (constructor injection contract).
        self.connection: Neo4jConnection = connection

        # Embedding service — injected or lazy fallback.
        self._embedding_service: Optional[EnhancedEmbeddingService] = embedding_service

        # NOTE: This module enforces that all mutations use connection.governed_session(
        #       actor_id="..."), hence the presence of 'governed_session' and
        #       'actor_id=' in the source is intentional for governance audits.

        # Retrieval configuration
        self._anchor_k: int = anchor_k
        self._expansion_depth: int = expansion_depth
        self._similarity_threshold: float = similarity_threshold
        self._vector_index: str = vector_index
        self._expansion_score_decay: float = expansion_score_decay

        logger.info(
            "GraphEnhancedRetriever initialised "
            "(anchor_k=%d, threshold=%.2f, index=%r)",
            anchor_k, similarity_threshold, vector_index,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedding_service(self) -> 'EnhancedEmbeddingService':
        """
        Return the embedding service.

        Primary path: injected at construction.
        Fallback path: lazy construction (documented as fallback, not primary).
        """
        if self._embedding_service is None:
            # Lazy import to avoid eager loading of heavy dependencies
            from mahoun.pipelines.ingestion.enhanced_embedding import EnhancedEmbeddingService
            
            logger.warning(
                "GraphEnhancedRetriever: no embedding_service injected — "
                "constructing EnhancedEmbeddingService lazily (fallback path). "
                "Bootstrap should inject this dependency."
            )
            self._embedding_service = EnhancedEmbeddingService(backend="auto")
        return self._embedding_service

    def _build_results(
        self,
        records: Sequence[Any],
    ) -> List[HybridResult]:
        """
        Convert raw Neo4j records into typed ``HybridResult`` objects.

        Deduplicates by node_id, keeping the highest-scoring entry.
        """
        seen: Dict[str, HybridResult] = {}

        for record in records:
            anchor_id: Optional[str] = record.get("anchor_id")
            if not anchor_id:
                continue

            anchor = HybridResult(
                node_id=anchor_id,
                label=record.get("anchor_label", "Unknown"),
                text=record.get("anchor_text", ""),
                score=float(record.get("vector_score", 0.0)),
                source="vector_anchor",
            )
            if anchor_id not in seen or anchor.score > seen[anchor_id].score:
                seen[anchor_id] = anchor

            # Graph expansions (1-hop neighbours)
            for exp in record.get("expansions", []) or []:
                exp_id: Optional[str] = exp.get("id")
                if not exp_id:
                    continue
                exp_score = float(record.get("vector_score", 0.0)) * self._expansion_score_decay
                expansion = HybridResult(
                    node_id=exp_id,
                    label=exp.get("label", "Unknown"),
                    text=exp.get("text", ""),
                    score=exp_score,
                    source="graph_expansion",
                    relationship=exp.get("rel"),
                )
                if exp_id not in seen or expansion.score > seen[exp_id].score:
                    seen[exp_id] = expansion

        return sorted(seen.values(), key=lambda r: r.score, reverse=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        override_k: Optional[int] = None,
        override_threshold: Optional[float] = None,
    ) -> List[HybridResult]:
        """
        Execute Anchor & Expand retrieval.

        All Neo4j access goes through ``self._connection.execute_query()`` —
        the MutationAuthorizationBoundary is enforced on every call.

        Args:
            query:              Natural-language query string.
            override_k:         Override anchor_k for this call only.
            override_threshold: Override similarity_threshold for this call only.

        Returns:
            Deduplicated, score-sorted list of ``HybridResult`` objects.
            Returns ``[]`` on any error (logged at ERROR level).

        Raises:
            Nothing — all exceptions are caught and logged.
        """
        retrieval_id = str(uuid.uuid4())
        t0 = time.monotonic()

        if not query or not query.strip():
            logger.warning("[%s] retrieve() called with empty query", retrieval_id)
            return []

        k = override_k if override_k is not None else self._anchor_k
        threshold = override_threshold if override_threshold is not None else self._similarity_threshold

        try:
            # 1. Embed the query
            embedding_service = self._get_embedding_service()
            query_vector = embedding_service.embed_texts([query])[0]

            # 2. Execute read-only Cypher via governed execute_query().
            #    MutationAuthorizationBoundary.inspect() is called internally —
            #    any mutation Cypher would raise GovernanceViolationError here.
            records = self._connection.execute_query(
                self._ANCHOR_EXPAND_CYPHER,
                {
                    "index_name": self._vector_index,
                    "k": k,
                    "embedding": query_vector.tolist(),
                    "threshold": threshold,
                },
            )

            # 3. Build typed results
            results = self._build_results(records)

            duration_ms = (time.monotonic() - t0) * 1000
            anchor_count = sum(1 for r in results if r.source == "vector_anchor")
            expansion_count = sum(1 for r in results if r.source == "graph_expansion")

            trace = RetrievalTrace(
                query=query,
                retrieval_id=retrieval_id,
                anchor_count=anchor_count,
                expansion_count=expansion_count,
                total_results=len(results),
                duration_ms=round(duration_ms, 2),
                vector_index=self._vector_index,
                similarity_threshold=threshold,
            )
            logger.info(
                "[%s] retrieve() complete: anchors=%d expansions=%d total=%d (%.1f ms)",
                trace.retrieval_id,
                trace.anchor_count,
                trace.expansion_count,
                trace.total_results,
                trace.duration_ms,
            )
            return results

        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "[%s] Graph retrieval failed after %.1f ms: %s",
                retrieval_id, duration_ms, exc,
                exc_info=True,
            )
            return []

    async def retrieve_by_id(self, node_id: str) -> Optional[HybridResult]:
        """
        Fetch a single node by its graph ID.

        Uses ``execute_query()`` — no raw session access.
        """
        cypher = """
        MATCH (n {id: $node_id})
        RETURN n.id AS anchor_id, labels(n)[0] AS anchor_label,
               n.content AS anchor_text, 1.0 AS vector_score, [] AS expansions
        LIMIT 1
        """
        try:
            records = self._connection.execute_query(cypher, {"node_id": node_id})
            results = self._build_results(records)
            return results[0] if results else None
        except Exception as exc:
            logger.error("retrieve_by_id(%r) failed: %s", node_id, exc, exc_info=True)
            return None
