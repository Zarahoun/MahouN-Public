"""
GGUF Embedding Service
======================
Efficient embedding service using GGUF quantized models via llama-cpp-python.

Features:
- 70% memory reduction vs HuggingFace models
- CPU-optimized inference
- Compatible with existing vector storage
- Drop-in replacement for EnhancedEmbeddingService
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)


class GGUFEmbeddingService:
    """
    Embedding service using GGUF quantized models.

    Uses llama-cpp-python's embedding mode for CPU-efficient inference.
    Designed for offline deployment with minimal resource requirements.

    Usage:
        service = GGUFEmbeddingService(
            model_path="models/paraphrase-multilingual-mpnet-base-277M-v2-Q8_0.gguf"
        )
        embeddings = service.embed_texts(["query text", "document text"])
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 512,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ):
        """
        Initialize GGUF embedding service.

        Args:
            model_path: Path to GGUF embedding model
            n_ctx: Context window size (embeddings typically need less)
            n_threads: Number of CPU threads (None = auto-detect)
            verbose: Enable verbose llama.cpp logging
        """
        self.model_path = self._resolve_model_path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads or os.cpu_count() or 4
        self.verbose = verbose

        self._llm = None
        self._embedding_dim: Optional[int] = None

        # Initialize model
        self._initialize_model()

        # Statistics
        self.stats = {
            "total_embeddings": 0,
            "total_texts": 0,
            "model_name": self.model_path.name if self.model_path else "unknown",
        }

        logger.info(
            f"GGUFEmbeddingService initialized "
            f"(model: {self.stats['model_name']}, threads: {self.n_threads})"
        )

    def _resolve_model_path(self, model_path: Optional[str]) -> Path:
        """Resolve model path from parameter or environment."""
        if model_path is None:
            # Check environment variable
            model_path = os.getenv(
                "MAHOUN_EMBEDDING_MODEL_PATH",
                "models/paraphrase-multilingual-mpnet-base-277M-v2-Q8_0.gguf",
            )

        path = Path(model_path)

        # If relative, resolve from project root
        if not path.is_absolute():
            # Try to find project root
            current = Path.cwd()
            while current != current.parent:
                if (current / "models").exists():
                    path = current / model_path
                    break
                current = current.parent

        if not path.exists():
            raise FileNotFoundError(
                f"GGUF embedding model not found: {path}\n"
                f"Please set MAHOUN_EMBEDDING_MODEL_PATH environment variable"
            )

        return path

    def _initialize_model(self):
        """Initialize llama-cpp-python model in embedding mode."""
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed.\n"
                "Install with: pip install llama-cpp-python"
            )

        logger.info(f"Loading GGUF embedding model: {self.model_path}")

        try:
            self._llm = Llama(
                model_path=str(self.model_path),
                embedding=True,  # Enable embedding mode
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=self.verbose,
                n_gpu_layers=0,  # CPU-only for embeddings
            )

            # Test embedding to get dimension
            test_emb = self._llm.create_embedding("test")
            self._embedding_dim = len(test_emb["data"][0]["embedding"])

            logger.info(f"✅ GGUF model loaded (dimension: {self._embedding_dim})")

        except Exception as e:
            logger.error(f"Failed to load GGUF model: {e}")
            raise RuntimeError(f"GGUF model initialization failed: {e}") from e

    def embed_texts(
        self,
        texts: List[str],
        is_query: bool = False,
        batch_size: int = 32,
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            is_query: Whether these are query texts (currently unused, for API compatibility)
            batch_size: Process texts in batches (to manage memory)
            normalize: Normalize embeddings to unit length

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        if not texts:
            return np.array([])

        embeddings = []

        # Process in batches to manage memory
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            for text in batch:
                # Generate embedding
                result = self._llm.create_embedding(text)
                embedding = result["data"][0]["embedding"]
                embeddings.append(embedding)

            # Update stats
            self.stats["total_texts"] += len(batch)
            self.stats["total_embeddings"] += len(batch)

        # Convert to numpy array
        embeddings_array = np.array(embeddings, dtype=np.float32)

        # Normalize if requested
        if normalize:
            norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
            # Avoid division by zero
            norms = np.where(norms == 0, 1, norms)
            embeddings_array = embeddings_array / norms

        logger.debug(
            f"Generated {len(texts)} embeddings (shape: {embeddings_array.shape})"
        )

        return embeddings_array

    @property
    def embedding_dimension(self) -> Optional[int]:
        """Get embedding dimension."""
        return self._embedding_dim

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding service statistics."""
        return {
            **self.stats,
            "embedding_dimension": self._embedding_dim,
            "model_path": str(self.model_path),
            "n_threads": self.n_threads,
        }

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded model."""
        return {
            "model_name": self.model_path.name,
            "model_path": str(self.model_path),
            "model_size_mb": self.model_path.stat().st_size / (1024 * 1024),
            "embedding_dimension": self._embedding_dim,
            "backend": "llama-cpp-python (GGUF)",
        }

    def __repr__(self) -> str:
        return (
            f"GGUFEmbeddingService("
            f"model={self.model_path.name}, "
            f"dim={self._embedding_dim})"
        )
