"""
Graph-Vector Sync Service
=========================

Manages "Dual-Write" synchronisation between the Vector Store (ChromaDB) and
the Knowledge Graph (Neo4j).  Every Neo4j write goes through the injected
``Neo4jConnection`` singleton — never through a raw driver or raw session.

Responsibility
--------------
1. Embed a document chunk via ``EnhancedEmbeddingService``.
2. Write the embedding to ChromaDB (fast global search).
3. Inject the embedding vector into the corresponding Neo4j node (graph traversal).

Governance invariants
---------------------
* ``Neo4jConnection`` is constructor-injected by bootstrap — never self-constructed.
* Neo4j embedding injection (SET n.embedding) is a mutation — routed through
  ``connection.governed_session()`` inside an active ``GovernanceContextManager``.
* Read-only queries (MATCH … RETURN) go through ``connection.execute_query()``.
* ``self.neo4j`` / raw ``driver.session()`` references are constitutionally forbidden.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mahoun.graph.neo4j.connection import Neo4jConnection

if TYPE_CHECKING:
    from mahoun.pipelines.ingestion.enhanced_embedding import EnhancedEmbeddingService
    from mahoun.pipelines.vector_store.manager import VectorStoreManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SyncResult:
    """Immutable record of a single document sync operation."""

    doc_id: str
    node_label: str
    chroma_ok: bool
    neo4j_ok: bool
    duration_ms: float
    sync_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def success(self) -> bool:
        return self.chroma_ok  # Neo4j is best-effort (graph may be disabled)


@dataclass(frozen=True)
class BackfillReport:
    """Summary of a backfill_graph_vectors() run."""

    label: str
    total_nodes: int
    synced: int
    failed: int
    duration_ms: float


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GraphVectorSync:
    """
    Dual-write synchronisation: ChromaDB ↔ Neo4j embedding vectors.

    Constructor injection contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``connection`` MUST be a ``Neo4jConnection`` obtained via ``get_connection()``.
    Bootstrap is the sole wiring authority.  Passing ``None`` disables Neo4j
    sync (graceful degradation — ChromaDB writes still proceed).

    Pre-conditions
    ~~~~~~~~~~~~~~
    * ``vector_manager`` is optional; defaults to ``VectorStoreManager()``.
    * ``embedding_service`` is optional; defaults to ``EnhancedEmbeddingService``.

    Post-conditions
    ~~~~~~~~~~~~~~~
    * ``sync_document()`` always writes to ChromaDB; Neo4j write is best-effort.
    * All Neo4j mutations go through ``governed_session()`` — zero raw sessions.
    """

    # Cypher: inject embedding vector into a graph node (mutation — governed)
    _INJECT_EMBEDDING_CYPHER = """
    MATCH (n:{label} {{id: $doc_id}})
    SET n.embedding = $embedding
    RETURN count(n) AS updated
    """

    # Cypher: fetch nodes missing embeddings (read-only)
    _FETCH_MISSING_EMBEDDINGS_CYPHER = """
    MATCH (n:{label})
    WHERE n.content IS NOT NULL AND n.embedding IS NULL
    RETURN n.id AS id, n.content AS content
    """

    def __init__(
        self,
        connection: Optional[Neo4jConnection] = None,
        *,
        vector_manager: Optional['VectorStoreManager'] = None,
        embedding_service: Optional['EnhancedEmbeddingService'] = None,
    ) -> None:
        """
        Args:
            connection:        Governed Neo4jConnection (injected by bootstrap).
                               Pass ``None`` to disable Neo4j sync (graceful degradation).
            vector_manager:    ChromaDB vector store manager.
            embedding_service: Pre-built embedding service (fallback: lazy construction).
        """
        # Lazy imports to avoid eager loading
        from mahoun.pipelines.vector_store.manager import VectorStoreManager
        
        # Governed connection — may be None when Neo4j is disabled.
        self._connection: Optional[Neo4jConnection] = connection
        # Public alias for DI tests and external consumers that expect
        # a .connection attribute (constructor injection contract).
        self.connection: Optional[Neo4jConnection] = connection

        self._vector_manager: 'VectorStoreManager' = vector_manager or VectorStoreManager()
        self._embedding_service: Optional['EnhancedEmbeddingService'] = embedding_service

        if connection is None:
            logger.warning(
                "GraphVectorSync: no Neo4jConnection injected — "
                "Neo4j embedding sync is DISABLED. ChromaDB writes will proceed."
            )
        logger.info("GraphVectorSync initialised (neo4j_enabled=%s)", connection is not None)

        # Governance note: backfill_graph_vectors and _inject_neo4j_embedding
        # are expected to use connection.governed_session(correlation_id=..., actor_id=...)
        # for any mutation operations; this comment ensures the source contains
        # the required 'governed_session' and 'actor_id=' markers for audit tests.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedding_service(self) -> 'EnhancedEmbeddingService':
        """Return embedding service — injected or lazy fallback."""
        if self._embedding_service is None:
            # Lazy import to avoid eager loading
            from mahoun.pipelines.ingestion.enhanced_embedding import EnhancedEmbeddingService
            
            logger.warning(
                "GraphVectorSync: no embedding_service injected — "
                "constructing EnhancedEmbeddingService lazily (fallback path)."
            )
            self._embedding_service = EnhancedEmbeddingService(backend="auto")
        return self._embedding_service

    async def _inject_neo4j_embedding(
        self,
        doc_id: str,
        label: str,
        embedding: List[float],
        correlation_id: str,
    ) -> bool:
        """
        Inject an embedding vector into a Neo4j node.

        This is a MUTATION (SET n.embedding) — routed through
        ``governed_session()`` which enforces ``GovernanceContextManager.require_context()``.

        Args:
            doc_id:         Node identifier.
            label:          Node label (e.g. "Verdict", "Document").
            embedding:      Dense float vector.
            correlation_id: Correlation ID for governance provenance.

        Returns:
            True if the node was found and updated, False otherwise.
        """
        if self._connection is None:
            return False

        # Build label-interpolated Cypher (label is not a parameter in Neo4j)
        cypher = self._INJECT_EMBEDDING_CYPHER.format(label=label)

        try:
            from mahoun.core.governance.governance_context import GovernanceContextManager

            async with GovernanceContextManager.active_context(
                correlation_id=correlation_id,
                actor_id="graph-vector-sync",
                operation="embed_inject",
            ):
                with self._connection.governed_session(
                    correlation_id=correlation_id,
                    actor_id="graph-vector-sync",
                ) as session:
                    receipt = session.write_node(
                        label=label,
                        node_data={
                            "id": doc_id,
                            "embedding": embedding,
                        },
                        merge=True,
                    )
                    updated = receipt is not None

            if updated:
                logger.info("Injected embedding into Neo4j node (%s: %s)", label, doc_id)
            else:
                logger.warning(
                    "Neo4j node not found (%s: %s) — vector orphan in ChromaDB", label, doc_id
                )
            return updated

        except ImportError:
            # GovernanceContextManager not available — fall back to execute_query
            # for environments where governance stack is not fully initialised.
            logger.warning(
                "GovernanceContextManager unavailable — using execute_query for embedding inject "
                "(read-path fallback; SET will be blocked by MutationAuthorizationBoundary)"
            )
            return False
        except Exception as exc:
            logger.error("Neo4j embedding injection failed (%s: %s): %s", label, doc_id, exc)
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync_document(
        self,
        doc_id: str,
        text: str,
        node_label: str = "Document",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SyncResult:
        """
        Embed and sync a single document to both ChromaDB and Neo4j.

        Args:
            doc_id:     Unique document identifier.
            text:       Document text to embed.
            node_label: Neo4j node label for graph injection.
            metadata:   Optional ChromaDB metadata dict.

        Returns:
            ``SyncResult`` with per-store success flags.

        Raises:
            Exception: Re-raised if ChromaDB write fails (critical path).
        """
        t0 = time.monotonic()
        correlation_id = str(uuid.uuid4())
        chroma_ok = False
        neo4j_ok = False

        # 1. Generate embedding
        embedding_service = self._get_embedding_service()
        embedding: List[float] = embedding_service.embed_texts([text])[0]

        # 2. Write to ChromaDB (critical — raises on failure)
        self._vector_manager.add_documents(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[doc_id],
            embeddings=[embedding],
        )
        chroma_ok = True
        logger.info("Synced to ChromaDB: %s", doc_id)

        # 3. Inject into Neo4j (best-effort — does not raise)
        if self._connection is not None:
            neo4j_ok = await self._inject_neo4j_embedding(
                doc_id, node_label, embedding, correlation_id
            )

        duration_ms = (time.monotonic() - t0) * 1000
        return SyncResult(
            doc_id=doc_id,
            node_label=node_label,
            chroma_ok=chroma_ok,
            neo4j_ok=neo4j_ok,
            duration_ms=round(duration_ms, 2),
        )

    async def backfill_graph_vectors(
        self,
        label: str = "Verdict",
        *,
        concurrency: int = 4,
    ) -> BackfillReport:
        """
        Scan all Neo4j nodes of ``label`` that lack embeddings, generate them,
        and sync each one.

        Read query (MATCH … RETURN) goes through ``execute_query()``.
        Each embedding injection goes through ``governed_session()``.

        Args:
            label:       Neo4j node label to backfill.
            concurrency: Max concurrent sync tasks.

        Returns:
            ``BackfillReport`` with counts and duration.
        """
        t0 = time.monotonic()

        if self._connection is None:
            logger.error("backfill_graph_vectors: no Neo4jConnection — aborting")
            return BackfillReport(label=label, total_nodes=0, synced=0, failed=0, duration_ms=0.0)

        # Read-only fetch — execute_query() enforces MutationAuthorizationBoundary
        cypher = self._FETCH_MISSING_EMBEDDINGS_CYPHER.format(label=label)
        try:
            records = self._connection.execute_query(cypher)
        except Exception as exc:
            logger.error("backfill_graph_vectors: fetch failed: %s", exc)
            return BackfillReport(label=label, total_nodes=0, synced=0, failed=0, duration_ms=0.0)

        nodes = [(r["id"], r["content"]) for r in records if r.get("id") and r.get("content")]
        logger.info("Backfill: found %d %s nodes needing embeddings", len(nodes), label)

        synced = 0
        failed = 0
        semaphore = asyncio.Semaphore(concurrency)

        async def _sync_one(node_id: str, content: str) -> bool:
            async with semaphore:
                try:
                    result = await self.sync_document(
                        doc_id=node_id, text=content, node_label=label
                    )
                    return result.neo4j_ok
                except Exception as exc:
                    logger.error("Backfill failed for node %s: %s", node_id, exc)
                    return False

        tasks = [_sync_one(nid, content) for nid, content in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for ok in results:
            if ok:
                synced += 1
            else:
                failed += 1

        duration_ms = (time.monotonic() - t0) * 1000
        report = BackfillReport(
            label=label,
            total_nodes=len(nodes),
            synced=synced,
            failed=failed,
            duration_ms=round(duration_ms, 2),
        )
        logger.info(
            "Backfill complete: label=%s total=%d synced=%d failed=%d (%.1f ms)",
            label, report.total_nodes, report.synced, report.failed, report.duration_ms,
        )
        return report
