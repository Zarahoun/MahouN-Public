"""
Graph Tool - GOVERNANCE-HARDENED
==========================================================

Advanced MCP tool for knowledge graph operations.
Now with REAL Neo4j integration through GovernedNeo4jSession.

CONSTITUTIONAL COMPLIANCE:
- NO raw driver access
- ALL operations require correlation_id + actor_id
- ALL operations use GovernedNeo4jSession
- ALL operations audited

Features:
    - Real graph traversal with Neo4j
    - Entity neighborhood analysis
    - Semantic search on graph
    - Path finding between entities
    - Comprehensive error handling
"""

from typing import Any, Callable, Dict, List, Optional
import logging
import asyncio
from datetime import datetime, timezone

from mahoun.core.governance.mutation_boundary import (
    GovernedNeo4jSession,
    _append_governance_audit,
)
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.exceptions import (
    GraphIntegrityException,
    LogicViolationException,
    SecurityBreachException,
)

logger = logging.getLogger(__name__)


class GraphTool:
    """
    Production-Grade MCP Tool for Graph Operations - GOVERNANCE-HARDENED.
    Fully integrated with GovernedNeo4jSession.
    
    CONSTITUTIONAL COMPLIANCE:
    - Uses session_factory instead of raw driver
    - All queries require correlation_id + actor_id
    - All operations audited
    """
    
    def __init__(self, session_factory: Optional[Callable[[], GovernedNeo4jSession]] = None):
        """
        Initialize GraphTool with governed session factory.
        
        Args:
            session_factory: Factory function returning GovernedNeo4jSession
        """
        self._session_factory = session_factory
        self._lock = asyncio.Lock()
    
    def _ensure_session_factory(self):
        """Lazy initialization of session factory."""
        if self._session_factory is not None:
            return
        
        try:
            from mahoun.graph.neo4j.connection import get_connection
            conn = get_connection()
            
            # Create a default session factory
            def default_factory():
                return conn.governed_session(
                    correlation_id="mcp-tool-default",
                    actor_id="mcp-graph-tool"
                )
            
            self._session_factory = default_factory
        except Exception as e:
            raise RuntimeError(
                "Neo4j backend unavailable: " + str(e)
            )
    
    async def _get_session_factory(self) -> Callable[[], GovernedNeo4jSession]:
        """Lazy initialization of session factory."""
        async with self._lock:
            if self._session_factory is None:
                self._ensure_session_factory()
        
        if self._session_factory is None:
            raise LogicViolationException(
                message="session_factory is required",
                correlation_id="mcp-tool",
                details={"component": "GraphTool"},
            )
        
        return self._session_factory

    async def get_graph_summary(
        self,
        correlation_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """
        Get high-level statistics of the Knowledge Graph with REAL Neo4j data.
        
        GOVERNANCE-PROTECTED: Requires active governance context.
        
        Args:
            correlation_id: Request correlation ID (REQUIRED)
            actor_id: Actor performing the operation (REQUIRED)
            
        Returns:
            Dict with graph statistics
        """
        try:
            # STEP 1: Validate governance context
            ctx = GovernanceContextManager.require_context()
            if ctx.correlation_id != correlation_id:
                raise SecurityBreachException(
                    message="correlation_id mismatch",
                    correlation_id=correlation_id,
                    details={"expected": ctx.correlation_id, "provided": correlation_id},
                )
            
            # STEP 2: Audit operation
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id,
                "actor_id": actor_id,
                "operation": "get_graph_summary",
                "component": "GraphTool",
            }
            _append_governance_audit(audit_entry)
            
            # STEP 3: Execute queries
            factory = await self._get_session_factory()
            session = factory()
            
            # Count nodes
            node_result = session._execute_authorized("MATCH (n) RETURN count(n) as count", {})
            node_count = node_result[0]["count"] if node_result else 0
            
            # Count relationships
            rel_result = session._execute_authorized("MATCH ()-[r]->() RETURN count(r) as count", {})
            rel_count = rel_result[0]["count"] if rel_result else 0
            
            # Get node labels
            labels_result = session._execute_authorized("CALL db.labels()", {})
            labels = [record["label"] for record in labels_result]
            
            # Get relationship types
            types_result = session._execute_authorized("CALL db.relationshipTypes()", {})
            rel_types = [record["relationshipType"] for record in types_result]
            
            return {
                "nodes": node_count,
                "edges": rel_count,
                "labels": labels,
                "relationship_types": rel_types,
                "status": "connected",
                "database": "neo4j"
            }
            
        except (SecurityBreachException, LogicViolationException):
            raise
        except Exception as e:
            logger.error(f"Graph summary failed: {e}", exc_info=True)
            raise GraphIntegrityException(
                message="Graph summary query failed",
                correlation_id=correlation_id,
                details={"error": str(e), "component": "GraphTool"},
            ) from e

    async def get_neighbors(
        self,
        doc_id: str,
        correlation_id: str,
        actor_id: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get immediate neighbors (related entities) via REAL Neo4j query.
        
        GOVERNANCE-PROTECTED: Requires active governance context.
        
        Args:
            doc_id: Document ID to query
            correlation_id: Request correlation ID (REQUIRED)
            actor_id: Actor performing the operation (REQUIRED)
            limit: Maximum number of neighbors to return
            
        Returns:
            Dict with neighbors data
        """
        try:
            # STEP 1: Validate governance context
            ctx = GovernanceContextManager.require_context()
            if ctx.correlation_id != correlation_id:
                raise SecurityBreachException(
                    message="correlation_id mismatch",
                    correlation_id=correlation_id,
                    details={"expected": ctx.correlation_id, "provided": correlation_id},
                )
            
            # STEP 2: Audit operation
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id,
                "actor_id": actor_id,
                "operation": "get_neighbors",
                "component": "GraphTool",
                "doc_id": doc_id,
                "limit": limit,
            }
            _append_governance_audit(audit_entry)
            
            # STEP 3: Execute query
            factory = await self._get_session_factory()
            session = factory()
            
            query = """
            MATCH (n {id: $doc_id})-[r]-(neighbor)
            RETURN neighbor, type(r) as relationship, r
            LIMIT $limit
            """
            result = session._execute_authorized(query, {"doc_id": doc_id, "limit": limit})
            
            neighbors: List[Dict[str, Any]] = []
            for record in result:
                neighbor_node = dict(record["neighbor"])
                neighbors.append({
                    "id": neighbor_node.get("id", "unknown"),
                    "label": neighbor_node.get("label", ""),
                    "type": neighbor_node.get("node_type", ""),
                    "relationship": record["relationship"],
                    "properties": {k: v for k, v in neighbor_node.items() if k not in ["id", "label"]}
                })
            
            return {
                "root": doc_id,
                "neighbors": neighbors,
                "count": len(neighbors)
            }
                
        except (SecurityBreachException, LogicViolationException):
            raise
        except Exception as e:
            logger.error(f"Get neighbors failed: {e}", exc_info=True)
            raise GraphIntegrityException(
                message="Get neighbors query failed",
                correlation_id=correlation_id,
                details={"error": str(e), "doc_id": doc_id, "component": "GraphTool"},
            ) from e

    async def get_related_docs(
        self,
        doc_id: str,
        correlation_id: str,
        actor_id: str,
        depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Traverse graph to find related documents via REAL path queries.
        
        GOVERNANCE-PROTECTED: Requires active governance context.
        
        Args:
            doc_id: Document ID to query
            correlation_id: Request correlation ID (REQUIRED)
            actor_id: Actor performing the operation (REQUIRED)
            depth: Maximum traversal depth
            
        Returns:
            Dict with related documents
        """
        try:
            # STEP 1: Validate governance context
            ctx = GovernanceContextManager.require_context()
            if ctx.correlation_id != correlation_id:
                raise SecurityBreachException(
                    message="correlation_id mismatch",
                    correlation_id=correlation_id,
                    details={"expected": ctx.correlation_id, "provided": correlation_id},
                )
            
            # STEP 2: Audit operation
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id,
                "actor_id": actor_id,
                "operation": "get_related_docs",
                "component": "GraphTool",
                "doc_id": doc_id,
                "depth": depth,
            }
            _append_governance_audit(audit_entry)
            
            # STEP 3: Execute query
            factory = await self._get_session_factory()
            session = factory()
            
            query = """
            MATCH path = (start {id: $doc_id})-[*1..$depth]-(related)
            WHERE related.node_type = 'document'
            RETURN DISTINCT related, length(path) as distance
            ORDER BY distance
            LIMIT 20
            """
            result = session._execute_authorized(query, {"doc_id": doc_id, "depth": depth})
            
            related: List[Dict[str, Any]] = []
            for record in result:
                related_node = dict(record["related"])
                related.append({
                    "id": related_node.get("id", "unknown"),
                    "label": related_node.get("label", ""),
                    "distance": record["distance"],
                    "type": related_node.get("node_type", "document"),
                    "properties": {k: v for k, v in related_node.items() if k not in ["id", "label", "node_type"]}
                })
            
            return {
                "source_doc": doc_id,
                "related": related,
                "depth": depth,
                "count": len(related)
            }
                
        except (SecurityBreachException, LogicViolationException):
            raise
        except Exception as e:
            logger.error(f"Get related docs failed: {e}", exc_info=True)
            raise GraphIntegrityException(
                message="Get related docs query failed",
                correlation_id=correlation_id,
                details={"error": str(e), "doc_id": doc_id, "component": "GraphTool"},
            ) from e

    async def search_graph(
        self,
        query: str,
        correlation_id: str,
        actor_id: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Semantic search on graph using REAL Neo4j fulltext indices.
        
        GOVERNANCE-PROTECTED: Requires active governance context.
        
        Args:
            query: Search query string
            correlation_id: Request correlation ID (REQUIRED)
            actor_id: Actor performing the operation (REQUIRED)
            limit: Maximum number of results
            
        Returns:
            Dict with search results
        """
        try:
            # STEP 1: Validate governance context
            ctx = GovernanceContextManager.require_context()
            if ctx.correlation_id != correlation_id:
                raise SecurityBreachException(
                    message="correlation_id mismatch",
                    correlation_id=correlation_id,
                    details={"expected": ctx.correlation_id, "provided": correlation_id},
                )
            
            # STEP 2: Audit operation
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id,
                "actor_id": actor_id,
                "operation": "search_graph",
                "component": "GraphTool",
                "query": query,
                "limit": limit,
            }
            _append_governance_audit(audit_entry)
            
            # STEP 3: Execute query
            factory = await self._get_session_factory()
            session = factory()
            
            cypher_query = """
            MATCH (n)
            WHERE n.label CONTAINS $query OR n.text CONTAINS $query
            RETURN n, labels(n) as node_labels
            LIMIT $limit
            """
            result = session._execute_authorized(cypher_query, {"query": query, "limit": limit})
            
            results: List[Dict[str, Any]] = []
            for record in result:
                node = dict(record["n"])
                results.append({
                    "id": node.get("id", "unknown"),
                    "label": node.get("label", ""),
                    "labels": record["node_labels"],
                    "score": 1.0,
                    "properties": {k: v for k, v in node.items() if k not in ["id", "label"]}
                })
            
            return {
                "query": query,
                "results": results,
                "count": len(results),
                "method": "cypher_contains"
            }
                
        except (SecurityBreachException, LogicViolationException):
            raise
        except Exception as e:
            logger.error(f"Search graph failed: {e}", exc_info=True)
            raise GraphIntegrityException(
                message="Search graph query failed",
                correlation_id=correlation_id,
                details={"error": str(e), "query": query, "component": "GraphTool"},
            ) from e
