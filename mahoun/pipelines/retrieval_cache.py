# pipelines/retrieval_cache.py
"""
Intelligent Caching System for Retrieval
- Query similarity-based caching
- LRU eviction
- Cache warming
- Hit rate tracking
"""

import hashlib
import time
from typing import Dict, List, Optional, Any
from collections import OrderedDict

from mahoun.pipelines._logging import setup_logger

log = setup_logger("cache")


@dataclass
class CacheEntry:
    """Cache entry with metadata"""

    query: str
    results: List[Dict]
    timestamp: float
    hit_count: int
    embedding: Optional[np.ndarray] = None


class QueryCache:
    """Simple hash-based cache"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def _hash_query(self, query: str) -> str:
        """Generate cache key"""
        return hashlib.md5(query.encode()).hexdigest()

    def get(self, query: str) -> Optional[List[Dict]]:
        """Get from cache"""
        key = self._hash_query(query)

        if key in self.cache:
            entry = self.cache[key]

            # Check TTL
            if time.time() - entry.timestamp > self.ttl:
                del self.cache[key]
                self.misses += 1
                return None

            # Update hit count and move to end (LRU)
            entry.hit_count += 1
            self.cache.move_to_end(key)
            self.hits += 1

            log.debug(f"Cache HIT: {query[:50]}")
            return entry.results

        self.misses += 1
        log.debug(f"Cache MISS: {query[:50]}")
        return None

    def put(self, query: str, results: List[Dict]):
        """Put in cache"""
        key = self._hash_query(query)

        # Evict if full
        if len(self.cache) >= self.max_size and key not in self.cache:
            self.cache.popitem(last=False)  # Remove oldest

        entry = CacheEntry(query=query, results=results, timestamp=time.time(), hit_count=0)

        self.cache[key] = entry
        self.cache.move_to_end(key)

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "total_requests": total,
        }

    def clear(self):
        """Clear cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


class SemanticCache:
    """
    Ultra-advanced semantic similarity-based cache with fail-closed DI.
    
    Constructor Injection Contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``embed_model`` MUST be injected by bootstrap (primary path).
    Lazy fallback is DEPRECATED and triggers loud warnings.
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl: int = 3600,
        similarity_threshold: float = 0.95,
        embed_model: Optional["SentenceTransformer"] = None,
        correlation_id: str = "",
    ):
        """
        Args:
            max_size: Maximum cache size
            ttl: Time to live in seconds
            similarity_threshold: Similarity threshold for cache hits
            embed_model: Pre-constructed SentenceTransformer (MANDATORY in production).
                        If None, triggers DEPRECATED lazy fallback with warning.
            correlation_id: Request tracking ID for observability.
        """
        import time
        self._correlation_id = correlation_id or f"cache-{time.time()}"
        
        self.max_size = max_size
        self.ttl = ttl
        self.similarity_threshold = similarity_threshold
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0

        if embed_model is not None:
            # PRIMARY PATH: Bootstrap-injected model
            self._embedding_model = embed_model
            log.info(
                f"[{self._correlation_id}] ✅ SemanticCache initialized "
                f"(bootstrap-injected model)"
            )
        else:
            # DEPRECATED FALLBACK: Lazy loading
            log.warning(
                f"[{self._correlation_id}] ⚠️  DEPRECATED: SemanticCache "
                f"initialized without injected model. Will attempt lazy load on first use. "
                f"Bootstrap wiring is MANDATORY in production. "
                f"Remediation: Update bootstrap/runtime.py to inject SentenceTransformer."
            )
            self._embedding_model = None

    def _get_embedding_model(self):
        """
        DEPRECATED: Lazy load embedding model.
        
        This method exists only for backward compatibility. Bootstrap injection
        is the PRIMARY path.
        """
        if self._embedding_model is None:
            import time
            log.warning(
                f"[{self._correlation_id}] ⚠️  Lazy model loading triggered. "
                f"This is a DEPRECATED fallback path."
            )
            try:
                from sentence_transformers import SentenceTransformer
                
                start = time.time()
                self._embedding_model = SentenceTransformer("BAAI/bge-m3")
                latency_ms = (time.time() - start) * 1000
                
                log.warning(
                    f"[{self._correlation_id}] ⚠️  Lazy model loading completed "
                    f"(model=BAAI/bge-m3, latency={latency_ms:.2f}ms)"
                )
            except ImportError:
                log.error(
                    f"[{self._correlation_id}] ❌ sentence-transformers not installed "
                    f"and no model injected."
                )
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers OR "
                    "inject pre-constructed model via bootstrap wiring."
                )
            except Exception as e:
                log.error(
                    f"[{self._correlation_id}] ❌ Lazy model loading failed: {e}"
                )
                raise RuntimeError(f"Failed to load embedding model: {e}")
        return self._embedding_model

    def _embed_query(self, query: str) -> np.ndarray:
        """Generate query embedding"""
        model = self._get_embedding_model()
        embedding = model.encode([query], normalize_embeddings=True)[0]
        return embedding

    def _compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity"""
        return float(np.dot(emb1, emb2))

    def get(self, query: str) -> Optional[List[Dict]]:
        """Get from cache using semantic similarity"""

        if not self.cache:
            self.misses += 1
            return None

        # Embed query
        query_emb = self._embed_query(query)

        # Find most similar cached query
        best_match = None
        best_similarity = 0.0

        for key, entry in self.cache.items():
            # Check TTL
            if time.time() - entry.timestamp > self.ttl:
                continue

            # Compute similarity
            if entry.embedding is not None:
                similarity = self._compute_similarity(query_emb, entry.embedding)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = (key, entry)

        # Check threshold
        if best_match and best_similarity >= self.similarity_threshold:
            key, entry = best_match
            entry.hit_count += 1
            self.cache.move_to_end(key)
            self.hits += 1

            log.debug(f"Semantic cache HIT: {query[:50]} (sim: {best_similarity:.3f})")
            return entry.results

        self.misses += 1
        log.debug(f"Semantic cache MISS: {query[:50]}")
        return None

    def put(self, query: str, results: List[Dict]):
        """Put in cache with embedding"""
        key = hashlib.md5(query.encode()).hexdigest()

        # Evict if full
        if len(self.cache) >= self.max_size and key not in self.cache:
            self.cache.popitem(last=False)

        # Embed query
        query_emb = self._embed_query(query)

        entry = CacheEntry(
            query=query, results=results, timestamp=time.time(), hit_count=0, embedding=query_emb
        )

        self.cache[key] = entry
        self.cache.move_to_end(key)

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "total_requests": total,
            "similarity_threshold": self.similarity_threshold,
        }

    def clear(self):
        """Clear cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


class CacheWarmer:
    """Pre-populate cache with common queries"""

    @staticmethod
    def warm_cache(cache: QueryCache, common_queries: List[str], retrieval_fn: callable):
        """Warm cache with common queries"""

        log.info(f"Warming cache with {len(common_queries)} queries...")

        for query in common_queries:
            results = retrieval_fn(query)
            cache.put(query, results)

        log.info(f"Cache warmed: {len(cache.cache)} entries")


def main():
    """Test caching"""

    # Test simple cache
    print("Testing Simple Cache:")
    cache = QueryCache(max_size=3, ttl=10)

    # Simulate queries
    queries = ["قانون مدنی", "حقوق جزا", "قانون مدنی", "قرارداد", "قانون مدنی"]

    for q in queries:
        result = cache.get(q)
        if result is None:
            # Simulate retrieval
            result = [{"id": "doc1", "text": f"Result for {q}"}]
            cache.put(q, result)
        print(f"Query: {q} -> {'HIT' if result else 'MISS'}")

    print(f"\nCache Stats: {cache.get_stats()}")

    # Test semantic cache
    print("\n\nTesting Semantic Cache:")
    sem_cache = SemanticCache(max_size=3, similarity_threshold=0.9)

    queries = [
        "قانون مدنی چیست",
        "قانون مدنی کدام است",  # Similar
        "حقوق جزا",
        "قانون مدنی",  # Similar to first
    ]

    for q in queries:
        result = sem_cache.get(q)
        if result is None:
            result = [{"id": "doc1", "text": f"Result for {q}"}]
            sem_cache.put(q, result)
        print(f"Query: {q} -> {'HIT' if result else 'MISS'}")

    print(f"\nSemantic Cache Stats: {sem_cache.get_stats()}")


if __name__ == "__main__":
    main()
