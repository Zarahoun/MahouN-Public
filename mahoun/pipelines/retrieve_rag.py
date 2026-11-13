"""
Advanced Hybrid RAG with Multi-Stage Retrieval and Reranking
============================================================

Enterprise-grade Retrieval-Augmented Generation with:
- Dense retrieval (Semantic)
- Sparse retrieval (BM25)
- Hybrid fusion
- Cross-encoder reranking
- Query expansion
- Result diversification
- Graph-enhanced reasoning
- Quantum-inspired scoring
- Causal inference
"""

import os
import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    import chromadb  # type: ignore
    from chromadb.config import Settings  # type: ignore
except Exception:
    chromadb = None
    Settings = None

# Optional heavy deps; import lazily where needed
try:
    from rank_bm25 import BM25Okapi  # type: ignore
except Exception:
    BM25Okapi = None  # type: ignore

AutoTokenizer = None
AutoModelForSequenceClassification = None
try:
    import torch  # type: ignore
except Exception:

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _TorchStub:
        cuda = _Cuda()

        @staticmethod
        def no_grad():
            return _NoGrad()

    torch = _TorchStub()  # type: ignore

from ._config import load_config
from ._logging import setup_logger

# Import from ultra systems
from mahoun.rag.ultra_graph_rag import UltraGraphRAG
from mahoun.retrieval.ultra_hybrid_search import UltraHybridSearch
from mahoun.rag.ultra_evaluation_system import UltraEvaluationSystem

log = setup_logger("retrieve")

# Global caches to avoid repeated heavy loads
_RERANK_TOKENIZER = None
_RERANK_MODEL = None


@dataclass
class RetrievalResult:
    """Structured retrieval result"""

    id: str
    text: str
    score: float
    rank: int
    method: str  # 'dense', 'sparse', 'hybrid', 'reranked'
    metadata: Dict = None


class QueryExpander:
    """Expand queries for better retrieval"""

    LEGAL_SYNONYMS = {
        "قانون": ["ماده", "تبصره", "مقررات"],
        "دادگاه": ["محکمه", "قاضی", "رأی"],
        "قرارداد": ["عقد", "توافق", "معامله"],
    }

    @staticmethod
    def expand(query: str) -> List[str]:
        """Generate query variations"""
        queries = [query]

        # Add synonym expansions
        for term, synonyms in QueryExpander.LEGAL_SYNONYMS.items():
            if term in query:
                for syn in synonyms:
                    queries.append(query.replace(term, syn))

        return queries[:3]  # Limit to 3 variations


class AdvancedRetriever:
    """Multi-stage retrieval system with ultra capabilities"""

    def __init__(self, config):
        self.cfg = config

        # Vector DB: file-based or HTTP client
        if getattr(self.cfg, "use_chroma_http", False):
            log.info(
                f"Using Chroma HTTP client at {self.cfg.chroma_host}:{self.cfg.chroma_port}"
            )
            try:
                self.client = chromadb.HttpClient(
                    host=self.cfg.chroma_host,
                    port=self.cfg.chroma_port,
                )
            except Exception as e:
                log.warning(f"Falling back to PersistentClient due to: {e}")
                self.client = chromadb.PersistentClient(
                    path=self.cfg.chroma_dir,
                    settings=Settings(anonymized_telemetry=False),
                )
        else:
            self.client = chromadb.PersistentClient(
                path=self.cfg.chroma_dir, settings=Settings(anonymized_telemetry=False)
            )
        self.collection = self.client.get_or_create_collection(
            self.cfg.chroma_collection, metadata={"hnsw:space": "cosine"}
        )

        # Device preference
        self.device = (
            self.cfg.rerank_device
            if self.cfg.rerank_device in ("cpu", "cuda")
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        log.info(f"Reranker device set to {self.device}")

        # Lazy-load reranker to reduce init latency
        self.rerank_tokenizer = None
        self.rerank_model = None
        self.ce_available = True

        # Ultra systems
        self.ultra_rag = UltraGraphRAG()
        self.ultra_search = UltraHybridSearch()
        self.ultra_eval = UltraEvaluationSystem()

        log.info("Ultra-Advanced Retriever initialized")

    def dense_retrieve(self, query: str, top_k: int = 20) -> List[RetrievalResult]:
        """Dense (semantic) retrieval"""
        results = self.collection.query(query_texts=[query], n_results=top_k)

        retrieved = []
        for i, (doc_id, doc, dist, meta) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["distances"][0],
                (
                    results["metadatas"][0]
                    if results.get("metadatas")
                    else [{}] * len(results["ids"][0])
                ),
            )
        ):
            retrieved.append(
                RetrievalResult(
                    id=doc_id,
                    text=doc,
                    score=1 - dist,  # Convert distance to similarity
                    rank=i + 1,
                    method="dense",
                    metadata=meta,
                )
            )

        return retrieved

    def sparse_retrieve(
        self,
        query: str,
        documents: Optional[List[str]] = None,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 20,
    ) -> Any:
        """
        Sparse retrieval backend.
        - If bm25_provider == 'pyserini' and index is available, query index and return dict id->score.
        - Otherwise, compute BM25 over provided documents list and return a list aligned to documents.
        """
        provider = getattr(self.cfg, "bm25_provider", "internal")
        if provider == "pyserini":
            try:
                from pyserini.search.lucene import LuceneSearcher

                index_dir = getattr(self.cfg, "bm25_index_dir", "data/pyserini_index")
                searcher = LuceneSearcher(index_dir)
                k = min(getattr(self.cfg, "pyserini_search_k", top_k), 1000)
                hits = searcher.search(query, k=k)
                # Build dict of scores for quick lookup
                return {h.docid: float(h.score) for h in hits}
            except Exception as e:
                log.warning(
                    f"Pyserini backend unavailable ({e}); falling back to internal BM25"
                )
                provider = "internal"
        # Internal BM25 over candidate documents
        if documents is None:
            raise ValueError("documents must be provided for internal BM25 scoring")
        tokenized_docs = [d.split() for d in documents]
        if BM25Okapi is not None:
            bm25 = BM25Okapi(tokenized_docs)
            scores = bm25.get_scores(query.split())
            return scores.tolist()
        # Fallback lightweight scoring (token overlap Jaccard)
        q_tokens = set(query.split())
        scores = []
        for toks in tokenized_docs:
            tset = set(toks)
            score = 0.0
            if tset:
                score = len(q_tokens & tset) / len(q_tokens | tset)
            scores.append(float(score))
        return scores

    def hybrid_fusion(
        self,
        dense_results: List[RetrievalResult],
        sparse_scores: Any,
        alpha: float = 0.65,
    ) -> List[RetrievalResult]:
        """Hybrid fusion with normalization"""
        # Prepare sparse scores aligned to dense_results
        if isinstance(sparse_scores, dict):
            aligned_sparse = np.array(
                [sparse_scores.get(r.id, 0.0) for r in dense_results], dtype=float
            )
        else:
            aligned_sparse = np.array(sparse_scores, dtype=float)

        # Normalize scores
        dense_scores = np.array([r.score for r in dense_results], dtype=float)

        def normalize(arr):
            if arr.size == 0:
                return arr
            a_min, a_max = float(arr.min()), float(arr.max())
            if a_max == a_min:
                return np.ones_like(arr)
            return (arr - a_min) / (a_max - a_min)

        dense_norm = normalize(dense_scores)
        sparse_norm = normalize(aligned_sparse)

        # Weighted combination
        hybrid_scores = alpha * dense_norm + (1 - alpha) * sparse_norm

        # Update results
        for i, result in enumerate(dense_results):
            result.score = float(hybrid_scores[i])
            result.method = "hybrid"

        # Sort by hybrid score
        dense_results.sort(key=lambda x: x.score, reverse=True)

        # Update ranks
        for i, result in enumerate(dense_results):
            result.rank = i + 1

        return dense_results

    def _ensure_reranker(self):
        """Lazy-load and cache reranker model/tokenizer globally."""
        global _RERANK_TOKENIZER, _RERANK_MODEL
        if self.rerank_tokenizer is None or self.rerank_model is None:
            try:
                global AutoTokenizer, AutoModelForSequenceClassification
                if AutoTokenizer is None or AutoModelForSequenceClassification is None:
                    from transformers import (
                        AutoTokenizer as _AT,
                        AutoModelForSequenceClassification as _AM,
                    )  # type: ignore

                    AutoTokenizer = _AT
                    AutoModelForSequenceClassification = _AM
                if _RERANK_TOKENIZER is None or _RERANK_MODEL is None:
                    log.info(f"Loading reranker {self.cfg.rerank_model} (lazy)")
                    _RERANK_TOKENIZER = AutoTokenizer.from_pretrained(
                        self.cfg.rerank_model
                    )
                    _RERANK_MODEL = AutoModelForSequenceClassification.from_pretrained(
                        self.cfg.rerank_model
                    )
                self.rerank_tokenizer = _RERANK_TOKENIZER
                self.rerank_model = _RERANK_MODEL.to(self.device).eval()
            except Exception as e:
                log.warning(f"Cross-encoder unavailable: {e}. Skipping CE rerank.")
                self.ce_available = False

    def _normalize_scores(self, scores):
        import numpy as _np

        if self.cfg.ce_normalization == "sigmoid":
            # Map logits to (0,1)
            return 1.0 / (1.0 + _np.exp(-scores))
        # min-max per batch
        smin, smax = scores.min(), scores.max()
        if smax == smin:
            return _np.ones_like(scores)
        return (scores - smin) / (smax - smin)

    def cross_encoder_rerank(
        self, query: str, results: List[RetrievalResult], top_k: int = 5
    ) -> List[RetrievalResult]:
        """Cross-encoder reranking"""

        if not results:
            return []
        # Ensure model (graceful fallback if unavailable)
        try:
            self._ensure_reranker()
        except Exception as e:
            log.warning(
                f"Failed to ensure reranker: {e}. Falling back to hybrid scores."
            )
            self.ce_available = False
        if (
            not self.ce_available
            or self.rerank_tokenizer is None
            or self.rerank_model is None
        ):
            log.warning(
                "Cross-encoder reranker not available; returning hybrid results"
            )
            # Still ensure ranks are updated consistently
            results = sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
            for i, result in enumerate(results):
                result.rank = i + 1
            return results

        import time

        t0 = time.perf_counter()
        # Prepare pairs
        pairs = [(query, r.text[:512]) for r in results]

        # Batched inference
        scores_all = []
        batch_size = max(1, getattr(self.cfg, "rerank_batch_size", 16))
        with torch.no_grad():
            for i in range(0, len(pairs), batch_size):
                q_batch = [p[0] for p in pairs[i : i + batch_size]]
                d_batch = [p[1] for p in pairs[i : i + batch_size]]
                inputs = self.rerank_tokenizer(
                    q_batch,
                    d_batch,
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                    max_length=512,
                ).to(self.device)
                logits = self.rerank_model(**inputs).logits.squeeze(-1)
                scores_all.append(logits.float().cpu().numpy())
        scores = np.concatenate(scores_all) if scores_all else np.array([])
        # Normalize scores to (0,1)
        scores = self._normalize_scores(scores)

        # Update scores
        for i, result in enumerate(results):
            result.score = float(scores[i])
            result.method = "reranked"

        # Sort and limit
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]

        # Update ranks
        for i, result in enumerate(results):
            result.rank = i + 1

        t1 = time.perf_counter()
        log.debug(
            f"Cross-encoder rerank: {len(results)} items in {(t1 - t0) * 1000:.1f} ms"
        )

        return results

    def diversify_results(
        self, results: List[RetrievalResult], lambda_param: float = 0.5
    ) -> List[RetrievalResult]:
        """MMR-based diversification"""
        if len(results) <= 1:
            return results

        selected = [results[0]]
        remaining = results[1:]

        while remaining and len(selected) < len(results):
            best_score = -float("inf")
            best_idx = 0

            for i, candidate in enumerate(remaining):
                # Relevance
                relevance = candidate.score

                # Max similarity to selected
                max_sim = max(
                    self._text_similarity(candidate.text, s.text) for s in selected
                )

                # MMR score
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    @staticmethod
    def _text_similarity(text1: str, text2: str) -> float:
        """Simple Jaccard similarity"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0
