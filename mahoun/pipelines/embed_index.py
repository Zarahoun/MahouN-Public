# pipelines/embed_index.py
"""
Advanced Embedding & Indexing with:
- Multi-model support
- Batch processing with progress
- FP16/BF16 optimization
- Incremental indexing
- Metadata enrichment
- Quality checks

Used in two modes:
1) CLI (offline indexing from JSONL)
2) Online embedding via EmbeddingService (used by IngestionPipeline)
"""

import os
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import hashlib

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

import tqdm
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    chromadb = None
    Settings = None
    HAS_CHROMADB = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

# Optional imports for advanced features
try:
    import wandb
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# -----------------------------------------------------------------------------
# Config & Logging imports (robust to missing legacy modules)
# -----------------------------------------------------------------------------
try:
    from _config import load_config  # legacy / external config module
except ImportError:
    load_config = None  # we'll fall back to env vars in that case

try:
    from mahoun.pipelines._logging import setup_logger  # Use project logging helper
except ImportError:  # fallback logger if module not present
    import logging

    def setup_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

log = setup_logger("embed")


# -----------------------------------------------------------------------------
# Embedding configuration + core embedder
# -----------------------------------------------------------------------------
@dataclass
class EmbeddingConfig:
    """Embedding configuration"""
    model_name: str
    batch_size: int
    max_length: int = 512
    normalize: bool = True
    use_fp16: bool = True
    device: str = "cuda" if (torch is not None and torch.cuda.is_available()) else "cpu"


class AdvancedEmbedder:
    """
    Ultra-advanced embedding system with fail-closed DI.
    
    Constructor Injection Contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``model`` MUST be injected by bootstrap (primary path).
    Lazy fallback is DEPRECATED and triggers loud warnings.
    """

    def __init__(
        self,
        config: EmbeddingConfig,
        model: Optional["SentenceTransformer"] = None,
        correlation_id: str = "",
    ):
        """
        Args:
            config: Embedding configuration
            model: Pre-constructed SentenceTransformer (MANDATORY in production).
                  If None, triggers DEPRECATED lazy fallback with warning.
            correlation_id: Request tracking ID for observability.
        """
        import time
        self._correlation_id = correlation_id or f"embedder-{time.time()}"
        
        self.config = config

        if model is not None:
            # PRIMARY PATH: Bootstrap-injected model
            self.model = model
            self.model.eval()
            
            # Enable FP16 if available
            if config.use_fp16 and config.device == "cuda":
                self.model = self.model.half()
                log.info("FP16 enabled")
            
            log.info(
                f"[{self._correlation_id}] ✅ AdvancedEmbedder initialized "
                f"(bootstrap-injected model)"
            )
        else:
            # DEPRECATED FALLBACK: Lazy construction
            log.warning(
                f"[{self._correlation_id}] ⚠️  DEPRECATED: AdvancedEmbedder "
                f"initialized without injected model. Attempting lazy construction. "
                f"Bootstrap wiring is MANDATORY in production. "
                f"Remediation: Update bootstrap/runtime.py to inject SentenceTransformer."
            )
            self.model = self._lazy_construct_model()
    
    def _lazy_construct_model(self) -> "SentenceTransformer":
        """
        DEPRECATED: Lazy model construction fallback.
        
        This method exists only for backward compatibility. Bootstrap injection
        is the PRIMARY path.
        """
        import time
        try:
            from sentence_transformers import SentenceTransformer
            
            start = time.time()
            model = SentenceTransformer(self.config.model_name, device=self.config.device)
            model.eval()

            # Enable FP16 if available
            if self.config.use_fp16 and self.config.device == "cuda":
                model = model.half()
                log.info("FP16 enabled")
            
            latency_ms = (time.time() - start) * 1000
            
            log.warning(
                f"[{self._correlation_id}] ⚠️  Lazy model construction completed "
                f"(model={self.config.model_name}, latency={latency_ms:.2f}ms). "
                f"This is a DEPRECATED fallback path."
            )
            return model
            
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
                f"[{self._correlation_id}] ❌ Lazy model construction failed: {e}"
            )
            raise RuntimeError(f"Failed to construct embedding model: {e}")

    def embed_batch(
        self,
        texts: List[str],
        show_progress: bool = False,
    ) -> np.ndarray:
        """Embed a batch of texts"""

        if torch is None:
            raise RuntimeError("torch not installed, cannot embed batch")
        with torch.inference_mode():
            embeddings = self.model.encode(
                texts,
                batch_size=self.config.batch_size,
                show_progress_bar=show_progress,
                device=self.config.device,
                convert_to_numpy=True,
                normalize_embeddings=self.config.normalize,
            )

        return embeddings

    def embed_with_metadata(
        self,
        records: List[Dict],
        text_field: str = "text",
    ) -> Tuple[List[str], List[str], np.ndarray, List[Dict]]:
        """
        Embed records with metadata.
        Returns: (ids, texts, embeddings, metadatas)
        """
        ids: List[str] = []
        texts: List[str] = []
        metadatas: List[Dict] = []

        for rec in records:
            text = rec.get(text_field, "")
            if not text or len(text.strip()) < 10:
                log.warning(f"Skipping empty/short text for {rec.get('id')}")
                continue

            # Truncate if needed (rough char estimate from max_length tokens)
            text_truncated = text[: self.config.max_length * 4]

            ids.append(rec["id"])
            texts.append(text_truncated)

            # Prepare metadata
            meta = rec.get("meta", {}).copy()
            meta["text_length"] = len(text)
            meta["truncated"] = len(text) > len(text_truncated)
            metadatas.append(meta)

        # Embed
        log.info(f"Embedding {len(texts)} documents.")
        embeddings = self.embed_batch(texts, show_progress=True)

        return ids, texts, embeddings, metadatas


# -----------------------------------------------------------------------------
# Incremental Chroma indexer (offline / batch indexing)
# -----------------------------------------------------------------------------
class IncrementalIndexer:
    """Incremental vector indexing"""

    def __init__(self, persist_dir: str, collection_name: str):
        self.persist_dir = persist_dir
        self.collection_name = collection_name

        # New Chroma architecture: PersistentClient + Settings
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        self.collection = self.client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        log.info(
            f"Collection: {collection_name} "
            f"({self.collection.count()} docs)"
        )

    def index_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: np.ndarray,
        metadatas: List[Dict],
        batch_size: int = 1000,
    ):
        """Index in batches"""

        total = len(ids)
        for i in tqdm(range(0, total, batch_size), desc="Indexing"):
            end = min(i + batch_size, total)

            self.collection.upsert(
                ids=ids[i:end],
                documents=documents[i:end],
                embeddings=embeddings[i:end].tolist(),
                metadatas=metadatas[i:end],
            )

        log.info(f"Indexed {total} documents")

    def get_stats(self) -> Dict:
        """Get collection statistics"""
        count = self.collection.count()

        # Sample to get metadata stats
        if count > 0:
            sample = self.collection.get(limit=min(100, count))

            categories: Dict[str, int] = {}
            for meta in sample.get("metadatas", []):
                cat = meta.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1
        else:
            categories: Dict[str, Any] = {}
        return {
            "total_documents": count,
            "collection_name": self.collection_name,
            "category_distribution": categories,
        }


# -----------------------------------------------------------------------------
# Embedding quality metrics (optional, for eval / W&B)
# -----------------------------------------------------------------------------
def compute_embedding_quality(embeddings: np.ndarray) -> Dict:
    """Compute embedding quality metrics"""

    # Compute pairwise similarities
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / (norms + 1e-8)
    similarities = normalized @ normalized.T

    # Remove diagonal
    np.fill_diagonal(similarities, 0)

    metrics = {
        "avg_similarity": float(similarities.mean()),
        "max_similarity": float(similarities.max()),
        "min_similarity": float(similarities.min()),
        "std_similarity": float(similarities.std()),
        "embedding_dim": embeddings.shape[1],
        "num_embeddings": embeddings.shape[0],
    }

    return metrics


# -----------------------------------------------------------------------------
# Adapter for online usage in MAHOUN (used by IngestionPipeline)
# -----------------------------------------------------------------------------
class EmbeddingService:
    """
    Adapter class for MAHOUN IngestionPipeline.

    It wraps AdvancedEmbedder and exposes:
        - embed_texts(texts: List[str], is_query: bool = False)
        - get_stats()
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        # Load from config if available
        if load_config is not None:
            cfg = load_config()
            model_name = model_name or getattr(cfg, "embed_model", None)
            batch_size = batch_size or getattr(cfg, "embed_batch", None)

        # Fallback to env vars / defaults
        model_name = model_name or os.getenv(
            "EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        batch_size = batch_size or int(os.getenv("EMBED_BATCH", "16"))

        embed_config = EmbeddingConfig(
            model_name=model_name,
            batch_size=batch_size,
            use_fp16=(torch is not None and torch.cuda.is_available()),
        )
        self.embedder = AdvancedEmbedder(embed_config)

        self._stats: Dict[str, Optional[float]] = {
            "calls": 0,
            "texts_embedded": 0,
            "last_error": None,
        }

        log.info(
            f"EmbeddingService initialized | "
            f"model={model_name}, batch={batch_size}, "
            f"device={embed_config.device}"
        )

    def embed_texts(self, texts: List[str], is_query: bool = False):
        """
        Embed a list of texts.
        Returns a list-of-lists (JSON-serializable) suitable for Chroma insert.
        """
        self._stats["calls"] += 1
        self._stats["texts_embedded"] += len(texts)

        try:
            embeddings = self.embedder.embed_batch(texts, show_progress=False)
            # Ensure plain Python list for serialization
            return embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        except Exception as e:
            self._stats["last_error"] = str(e)
            log.error(f"Embedding failed: {e}", exc_info=True)
            raise RuntimeError(f"Embedding failed: {e}") from e

    def get_stats(self) -> Dict:
        return dict(self._stats)


# -----------------------------------------------------------------------------
# CLI entrypoint for offline embedding + indexing from JSONL
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True, help="Input JSONL file")
    ap.add_argument("--persist_dir", default=None, help="Chroma persist directory")
    ap.add_argument("--collection", default=None, help="Collection name")
    ap.add_argument("--model", default=None, help="Override embedding model")
    ap.add_argument("--batch_size", type=int, default=None, help="Batch size")
    ap.add_argument("--incremental", action="store_true", help="Incremental indexing")
    ap.add_argument("--compute_quality", action="store_true", help="Compute quality metrics")
    ap.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    args = ap.parse_args()

    # Load config if available, else fallback to env/defaults
    if load_config is not None:
        cfg = load_config()
        persist_dir = args.persist_dir or getattr(cfg, "chroma_dir", "./chroma_data")
        collection_name = args.collection or getattr(
            cfg, "chroma_collection", "mahoun_verdicts"
        )
        model_name = args.model or getattr(
            cfg, "embed_model", "sentence-transformers/all-MiniLM-L6-v2"
        )
        batch_size = args.batch_size or getattr(cfg, "embed_batch", 16)
    else:
        persist_dir = args.persist_dir or os.getenv("CHROMA_DIR", "./chroma_data")
        collection_name = args.collection or os.getenv(
            "CHROMA_COLLECTION", "mahoun_verdicts"
        )
        model_name = args.model or os.getenv(
            "EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        batch_size = args.batch_size or int(os.getenv("EMBED_BATCH", "16"))

    # W&B init
    if args.wandb:
        if not HAS_WANDB:
            log.warning("wandb not installed, skipping W&B logging. Install with: pip install wandb")
            args.wandb = False
        else:
            wandb.init(
                project=os.getenv("WANDB_PROJECT", "mahoun"),
                name="embed-index",
                reinit=True,
                config={
                    "model": model_name,
                    "batch_size": batch_size,
                    "collection": collection_name,
                },
            )

    # Load data
    log.info(f"Loading data from {args.jsonl}")
    records: List[Dict] = []
    with open(args.jsonl, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))

    log.info(f"Loaded {len(records)} records")

    # Initialize embedder
    embed_config = EmbeddingConfig(
        model_name=model_name,
        batch_size=batch_size,
        use_fp16=(torch is not None and torch.cuda.is_available()),
    )
    embedder = AdvancedEmbedder(embed_config)

    # Embed
    ids, texts, embeddings, metadatas = embedder.embed_with_metadata(records)

    log.info(f"Generated {len(embeddings)} embeddings")

    # Quality metrics
    if args.compute_quality:
        quality = compute_embedding_quality(embeddings)
        log.info(f"Quality metrics: {quality}")

        if args.wandb:
            wandb.log({"embedding_quality": quality})

    # Index
    indexer = IncrementalIndexer(persist_dir, collection_name)
    indexer.index_batch(ids, texts, embeddings, metadatas)

    # Stats
    stats = indexer.get_stats()
    log.info(f"Collection stats: {stats}")

    # W&B logging
    if args.wandb:
        wandb.log(
            {
                "num_documents": len(ids),
                "embedding_model": model_name,
                "embedding_dim": embeddings.shape[1] if len(embeddings) > 0 else 0,
                "collection_size": stats["total_documents"],
                "status": "completed",
            }
        )

        if stats.get("category_distribution"):
            wandb.log({"category_distribution": stats["category_distribution"]})

        # Optional: embedding visualization
        if len(embeddings) > 0 and args.wandb and HAS_SKLEARN:
            try:
                pca = PCA(n_components=2)
                embeddings_2d = pca.fit_transform(embeddings[:1000])

                scatter_data = [
                    [x, y, metadatas[i].get("category", "unknown")]
                    for i, (x, y) in enumerate(embeddings_2d)
                ]

                table = wandb.Table(
                    data=scatter_data, columns=["x", "y", "category"]
                )
                wandb.log(
                    {
                        "embedding_space": wandb.plot.scatter(
                            table, "x", "y", title="Embedding Space (PCA)"
                        )
                    }
                )
            except Exception as e:
                log.warning(f"Failed to create embedding visualization: {e}")

        wandb.finish()

    log.info(f"✅ Indexing complete: {persist_dir}/{collection_name}")


if __name__ == "__main__":
    main()
