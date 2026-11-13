"""
Legal Search Service
====================

Production search service that wraps LegalAwareRetrievalService
and provides the interface expected by the search API router.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from mahoun.core.exceptions import GraphResolutionFailure
from mahoun.core.governance.violations import (
    GovernanceViolation,
    MissingExecutionPolicyError,
    ViolationCategory,
    ViolationSeverity,
)
from mahoun.graph.graph_query_service import GraphQueryService
from mahoun.rag.hybrid_rag_service import HybridRAGService
from mahoun.rag.legal_aware_retrieval import LegalAwareRetrievalService, LegalQueryFilter
from mahoun.schemas.legal_aware_schema import CourtRank
from mahoun.core.runtime_config import get_runtime_settings

logger = logging.getLogger(__name__)


@dataclass
class LegalSearchFilters:
    """Filters for verdict search - API-facing filter model."""

    court_level: Optional[str] = None
    case_type: Optional[str] = None
    is_final: Optional[bool] = None
    article_no: Optional[str] = None
    law_name: Optional[str] = None
    tags: Optional[List[str]] = None

    def to_legal_query_filter(self) -> LegalQueryFilter:
        """Convert to internal LegalQueryFilter."""
        min_court_rank = None
        if self.court_level:
            if "دفع" in self.court_level or "supreme" in self.court_level.lower():
                min_court_rank = CourtRank.SUPREME_COURT
            elif "تجدیدنظر" in self.court_level or "appeal" in self.court_level.lower():
                min_court_rank = CourtRank.APPEALS_COURT
            elif "اول" in self.court_level or "first" in self.court_level.lower():
                min_court_rank = CourtRank.FIRST_INSTANCE

        return LegalQueryFilter(
            exclude_repealed=True,
            min_court_rank=min_court_rank,
            min_authority_score=0.5,
        )


@dataclass
class VerdictHit:
    """Single verdict search result matching API response model."""

    verdict_id: str
    score: float
    section: str
    chunk_text: str
    case_type: Optional[str] = None
    court_level: Optional[str] = None
    procedure_stage: Optional[str] = None
    is_final: Optional[bool] = None
    tags: List[str] = field(default_factory=list)
    law_articles: List[str] = field(default_factory=list)
    extra_metadata: dict = field(default_factory=dict)


class LegalSearchService:
    """
    Legal Search Service for verdicts.

    Wraps LegalAwareRetrievalService to provide the interface expected by
    the search API router (api/routers/search.py).
    """

    def __init__(self):
        """Initialize the search service with lazy loading."""
        self._base_service: Optional[HybridRAGService] = None
        self._legal_service: Optional[LegalAwareRetrievalService] = None
        self._graph_service: Optional[GraphQueryService] = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self.settings = get_runtime_settings()

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of the underlying services."""
        if self._initialized:
            return

        try:
            from mahoun.pipelines.vector_store.manager import VectorStoreManager

            vector_store = VectorStoreManager()
            await vector_store.initialize()

            graph_service = None
            if self.settings.graph_enabled and self.settings.retrieval_mode == "hybrid_graph":
                graph_service = GraphQueryService()

            self._graph_service = graph_service
            self._base_service = HybridRAGService(
                vector_store=vector_store,
                graph_retriever=graph_service,
                allow_graph_degraded_mode=False,
            )
            self._legal_service = LegalAwareRetrievalService(
                base_service=self._base_service,
                enable_legal_filtering=True,
                enable_authority_ranking=True,
                enable_temporal_resolution=True,
                enable_cross_system_sync=False,
            )
            self._initialized = True
            self._init_error = None
            logger.info("LegalSearchService initialized with LegalAwareRetrievalService")

        except Exception as e:
            logger.error(f"Failed to initialize LegalSearchService: {e}")
            self._init_error = str(e)
            raise RuntimeError("LegalSearchService initialization failed") from e

    async def search_verdicts(
        self,
        query: str,
        filters: Optional[LegalSearchFilters] = None,
        limit: int = 10,
        enrich_with_graph: bool = True,
    ) -> List[VerdictHit]:
        """
        Search for legal verdicts.

        Args:
            query: Natural language search query
            filters: Optional search filters
            limit: Maximum number of results
            enrich_with_graph: Whether to enrich with graph data (deprecated, kept for API compat)

        Returns:
            List of VerdictHit objects
        """
        await self._ensure_initialized()

        if not query or not query.strip():
            return []
        if filters is None:
            raise MissingExecutionPolicyError(
                GovernanceViolation(
                    category=ViolationCategory.BYPASS_ATTEMPT,
                    severity=ViolationSeverity.CRITICAL,
                    message="Search execution requires an explicit legal execution policy.",
                    details={"query": query[:120], "surface": "LegalSearchService.search_verdicts"},
                    source="LegalSearchService",
                )
            )

        try:
            legal_filter = filters.to_legal_query_filter()

            if self._legal_service:
                result = await self._legal_service.legal_retrieve(
                    query=query,
                    legal_filter=legal_filter,
                    top_k=limit,
                    mode="HYBRID_GRAPH_FIRST" if enrich_with_graph else "TEXT_ONLY",
                )
            else:
                raise RuntimeError(
                    self._init_error or "Legal-aware retrieval service is not initialized"
                )

            # Convert RetrievalResult -> VerdictHit
            hits = []
            for r in result.results:
                hit = VerdictHit(
                    verdict_id=r.doc_id,
                    score=r.score,
                    section=r.metadata.get("section", "unknown"),
                    chunk_text=r.content[:500] if r.content else "",
                    case_type=r.metadata.get("case_type"),
                    court_level=r.metadata.get("court_level"),
                    procedure_stage=r.metadata.get("procedure_stage"),
                    is_final=r.metadata.get("is_final"),
                    tags=r.metadata.get("tags", []),
                    law_articles=r.metadata.get("law_articles", []),
                    extra_metadata=r.metadata,
                )
                hits.append(hit)

            return hits

        except (MissingExecutionPolicyError, GraphResolutionFailure):
            raise
        except Exception as e:
            logger.error(f"Search failed for query='{query[:50]}...': {e}")
            raise

    async def _get_vector_manager(self):
        """Get vector manager for health check."""
        await self._ensure_initialized()
        if self._base_service and hasattr(self._base_service, 'vector_store'):
            return self._base_service.vector_store
        return None

    async def _get_graph_ops(self):
        """Get graph operations for health check."""
        await self._ensure_initialized()
        return self._graph_service

    def get_stats(self) -> dict:
        """Get service statistics."""
        stats = {"initialized": self._initialized}
        if self._init_error:
            stats["init_error"] = self._init_error
        if self._legal_service:
            stats["legal_service"] = getattr(self._legal_service, "stats", {})
        if self._base_service:
            stats["base_service"] = "HybridRAGService"
        if self._graph_service:
            stats["graph_service"] = type(self._graph_service).__name__
        return stats
