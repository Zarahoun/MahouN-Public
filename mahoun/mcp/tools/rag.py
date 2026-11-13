"""
RAG Tool (HAJIX Production Grade)
==================================

Advanced MCP tool for Retrieval-Augmented Generation.
Connects directly to the production-grade HybridSearchV2 engine.

Features:
    - Hybrid Search (Dense + Sparse BM25)
    - Advanced RRF Fusion
    - Reranking support
    - Query expansion (internal)
"""

from typing import Any, Dict, List, Optional
import logging
import asyncio

# Connect to REAL production search engine
from mahoun.retrieval.hybrid_search_v2 import HybridSearchV2, RetrievalMethod, FusionMethod
from mahoun.pipelines.vector_store.manager_v2 import VectorStoreManagerV2

logger = logging.getLogger(__name__)


class RAGTool:
    """
    Production-Grade MCP Tool for RAG operations.
    Wrapper around HybridSearchV2.
    """
    
    def __init__(self):
        self._search_engine: Optional[HybridSearchV2] = None
        self._vector_store: Optional[VectorStoreManagerV2] = None
        self._lock = asyncio.Lock()
    
    async def _get_engine(self) -> HybridSearchV2:
        """Lazy initialization of the search engine."""
        async with self._lock:
            if self._search_engine is None:
                # Initialize Vector Store
                self._vector_store = VectorStoreManagerV2()
                await self._vector_store.initialize()
                
                # Initialize Hybrid Search Engine
                self._search_engine = HybridSearchV2(
                    vector_store=self._vector_store,
                    dense_weight=0.7,
                    sparse_weight=0.3
                )
                await self._search_engine.initialize()
                
        return self._search_engine
    
    async def hybrid_search(
        self, 
        query: str, 
        top_k: int = 10,
        enable_reranking: bool = True
    ) -> Dict[str, Any]:
        """
        Perform advanced hybrid search (Dense + Sparse + RRF).
        
        Args:
            query: User query string
            top_k: Number of results to return
            enable_reranking: Whether to apply cross-encoder reranking
            
        Returns:
            Rich search results with metadata and analysis.
        """
        try:
            engine = await self._get_engine()
            
            # Execute Real Hybrid Search
            result = await engine.search(
                query=query,
                top_k=top_k,
                method=RetrievalMethod.HYBRID,
                fusion=FusionMethod.RRF,
                enable_reranking=enable_reranking
            )
            
            # Formate output for MCP
            formatted_results: List[Any] = []
            for item in result.results:
                formatted_results.append({
                    "id": item.id,
                    "text": item.text,
                    "score": item.score,
                    "metadata": item.metadata,
                    "analysis": {
                        "dense_score": item.dense_score,
                        "sparse_score": item.sparse_score,
                        "source": item.source
                    }
                })
            
            return {
                "results": formatted_results,
                "metrics": {
                    "total_found": result.total_found,
                    "search_time_ms": result.search_time_ms,
                    "cache_hit": result.cache_hit
                }
            }
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return {"error": str(e), "results": []}
    
    async def dense_lookup(self, doc_id: str) -> Dict[str, Any]:
        """
        Get dense vector representation for a specific document.
        """
        try:
            engine = await self._get_engine()
            # Accessing underlying vector store via engine property or directly
            # This logic depends on exposure in HybridSearchV2, assuming direct access for now
            if engine.dense_retriever and engine.dense_retriever.vector_store:
                 vector = await engine.dense_retriever.vector_store.get_vector(doc_id)
                 return {"doc_id": doc_id, "vector": vector, "dim": len(vector) if vector else 0}
            
            return {"error": "Vector store access not available"}
            
        except Exception as e:
            return {"error": str(e)}

    async def rerank(self, query: str, documents: List[str]) -> Dict[str, Any]:
        """
        Standalone reranking of provided strings based on a query.
        """
        try:
            engine = await self._get_engine()
            
            # Using the reranker directly if available in engine
            if hasattr(engine, 'reranker') and engine.reranker:
                # Wrap documents in internal objects if necessary, or use direct API
                reranked = await engine.reranker.rerank(query, documents)
                return {
                    "query": query,
                    "results": reranked,
                    "method": "cross_encoder_v2"
                }
            
            return {"error": "Reranker not initialized in engine"}
            
        except Exception as e:
            logger.error(f"Standalone rerank failed: {e}")
            return {"error": str(e)}
