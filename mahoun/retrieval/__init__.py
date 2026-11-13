"""
Retrieval Module
================

Retrieval components for MAHOUN including hybrid search and graph-enhanced retrieval.
"""
from typing import Any, Optional

# Hybrid Search
try:
    from .ultra_hybrid_search import (
        UltraHybridSearch,
        BM25Retriever,
        DenseRetriever,
        RetrievalMethod,
        FusionMethod,
    )
    # Alias for compatibility
    HybridRetriever = UltraHybridSearch
except ImportError as e:
    UltraHybridSearch: Optional[Any] = None
    BM25Retriever: Optional[Any] = None
    DenseRetriever: Optional[Any] = None
    HybridRetriever: Optional[Any] = None
    RetrievalMethod: Optional[Any] = None
    FusionMethod: Optional[Any] = None
# Hybrid Search V2 - Production Grade
try:
    from .hybrid_search_v2 import (
        HybridSearchV2,
        BM25Retriever as BM25RetrieverV2,
        DenseRetriever as DenseRetrieverV2,
        RetrievalMethod as RetrievalMethodV2,
        FusionMethod as FusionMethodV2,
        SearchResult as SearchResultV2,
        HybridSearchResult,
        create_hybrid_search_v2
    )
except ImportError as e:
    HybridSearchV2: Optional[Any] = None
    BM25RetrieverV2: Optional[Any] = None
    DenseRetrieverV2: Optional[Any] = None
    RetrievalMethodV2: Optional[Any] = None
    FusionMethodV2: Optional[Any] = None
    SearchResultV2: Optional[Any] = None
    HybridSearchResult: Optional[Any] = None
    create_hybrid_search_v2: Optional[Any] = None
# Graph Hop Retrieval
try:
    from mahoun.graph.retriever.graph_hop import (
        GraphHopRetriever,
        HopResult,
        expand_with_graph_hops
    )
except ImportError:
    GraphHopRetriever: Optional[Any] = None
    HopResult: Optional[Any] = None
    expand_with_graph_hops: Optional[Any] = None
__all__ = [
    # Hybrid Search (Legacy)
    'UltraHybridSearch',
    'HybridRetriever',
    'BM25Retriever',
    'DenseRetriever',
    'RetrievalMethod',
    'FusionMethod',
    
    # Hybrid Search V2 - Production Grade
    'HybridSearchV2',
    'BM25RetrieverV2',
    'DenseRetrieverV2',
    'RetrievalMethodV2',
    'FusionMethodV2',
    'SearchResultV2',
    'HybridSearchResult',
    'create_hybrid_search_v2',
    
    # Graph hop
    'GraphHopRetriever',
    'HopResult',
    'expand_with_graph_hops',
]
