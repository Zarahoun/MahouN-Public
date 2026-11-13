"""
Enhanced Embedding Service
==========================
Wrapper for using better embedding models with fallback support.

Features:
- Support for multiple embedding providers
- Model selection based on content type
- Fallback to default model if preferred unavailable
- Batch processing optimization
"""

import logging
import os
from typing import Any, Dict, List, Optional, Literal
from mahoun.pipelines.embed_index import EmbeddingService

logger = logging.getLogger(__name__)


class EnhancedEmbeddingService:
    """
    Enhanced embedding service with support for multiple backends.

    Supports:
    - HuggingFace sentence-transformers (default)
    - GGUF quantized models (via llama-cpp-python)

    Automatically selects best available backend and falls back gracefully.
    """

    def __init__(
        self,
        preferred_model: Optional[str] = None,
        fallback_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        backend: Literal["auto", "huggingface", "gguf"] = "auto",
    ):
        """
        Initialize Enhanced Embedding Service.

        Args:
            preferred_model: Preferred model name (e.g., multilingual models)
            fallback_model: Fallback model if preferred unavailable
            backend: Embedding backend ("auto", "huggingface", "gguf")
                - "auto": Try GGUF first, fallback to HuggingFace
                - "gguf": Force GGUF backend
                - "huggingface": Force HuggingFace backend
        """
        self.preferred_model = (
            preferred_model
            or os.getenv(
                "EMBED_MODEL_PREFERRED",
                "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",  # Good for Persian
            )
        )
        self.fallback_model = fallback_model
        self.backend = backend

        self._service = None
        self._current_model = None
        self._current_backend = None

        logger.info(
            f"EnhancedEmbeddingService initialized "
            f"(backend: {self.backend}, preferred: {self.preferred_model})"
        )

    def _get_service(self):
        """Get or create embedding service with backend selection"""
        if self._service is None:
            # Determine backend to use
            if self.backend == "gguf":
                self._service = self._try_gguf_backend()
            elif self.backend == "huggingface":
                self._service = self._try_huggingface_backend()
            else:  # auto
                # Try GGUF first (more efficient)
                self._service = self._try_gguf_backend()
                if self._service is None:
                    # Fallback to HuggingFace
                    self._service = self._try_huggingface_backend()

            if self._service is None:
                raise RuntimeError("Could not initialize any embedding backend")

        return self._service

    def _try_gguf_backend(self):
        """Try to initialize GGUF backend"""
        try:
            from mahoun.pipelines.ingestion.gguf_embedding import GGUFEmbeddingService

            # Check for GGUF model path
            gguf_model_path = os.getenv(
                "MAHOUN_EMBEDDING_MODEL_PATH",
                "models/paraphrase-multilingual-mpnet-base-277M-v2-Q8_0.gguf",
            )

            service = GGUFEmbeddingService(model_path=gguf_model_path)
            self._current_model = gguf_model_path
            self._current_backend = "gguf"
            logger.info(f"✅ Using GGUF embedding backend: {gguf_model_path}")
            return service

        except Exception as e:
            logger.warning(f"GGUF backend not available: {e}")
            return None

    def _try_huggingface_backend(self):
        """Try to initialize HuggingFace backend"""
        # Try preferred model first
        try:
            service = EmbeddingService(model_name=self.preferred_model)
            self._current_model = self.preferred_model
            self._current_backend = "huggingface"
            logger.info(f"Using HuggingFace model: {self.preferred_model}")
            return service
        except Exception as e:
            logger.warning(
                f"Failed to load preferred model {self.preferred_model}: {e}. "
                f"Falling back to {self.fallback_model}"
            )
            try:
                service = EmbeddingService(model_name=self.fallback_model)
                self._current_model = self.fallback_model
                self._current_backend = "huggingface"
                logger.info(f"Using fallback HuggingFace model: {self.fallback_model}")
                return service
            except Exception as e2:
                logger.error(f"Failed to load fallback model: {e2}")
                return None

    def embed_texts(
        self, texts: List[str], is_query: bool = False
    ) -> List[List[float]]:
        """
        Embed texts using the best available model.

        Args:
            texts: List of texts to embed
            is_query: Whether these are query texts

        Returns:
            List of embedding vectors
        """
        service = self._get_service()

        # Handle different backend interfaces
        if self._current_backend == "gguf":
            import numpy as np

            embeddings_array = service.embed_texts(texts, is_query=is_query)
            # Convert to list format for compatibility
            return embeddings_array.tolist()
        else:
            return service.embed_texts(texts, is_query=is_query)

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding service statistics"""
        if self._service is None:
            return {"model": None, "initialized": False}

        stats = self._service.get_stats()
        stats["current_model"] = self._current_model
        stats["current_backend"] = self._current_backend
        stats["is_preferred"] = self._current_model == self.preferred_model
        return stats

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about current model"""
        return {
            "current_model": self._current_model,
            "current_backend": self._current_backend,
            "preferred_model": self.preferred_model,
            "fallback_model": self.fallback_model,
            "backend_requested": self.backend,
            "is_preferred": self._current_model == self.preferred_model,
        }
