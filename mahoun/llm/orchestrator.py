"""
Model Orchestrator
==================
Enterprise-grade manager for local LLM lifecycles.

Features:
- Dynamic Model Loading/Unloading
- Capability-based Routing (Coding vs Reasoning)
- Thread-safe Model Access
- LRU caching for memory optimization
- Automatic resource cleanup
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, List, Set

from mahoun.llm.local_driver import LocalLLMDriver

logger = logging.getLogger(__name__)


class ModelCapability(str, Enum):
    """Capabilities provided by different models."""

    CODING = "coding"  # Qwen-Coder approach
    REASONING = "reasoning"  # Granite/Llama approach
    GENERAL = "general"  # Fallback
    EMBEDDING = "embedding"  # Text embedding (usually separate service)


@dataclass
class LoadedModel:
    """Track metadata for a currently loaded model."""

    driver: LocalLLMDriver
    model_name: str
    capabilities: Set[ModelCapability]
    last_used: float = field(default_factory=time.time)

    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()


class ModelOrchestrator:
    """
    Orchestrates local LLM resources.

    Ensures that we only have N models loaded at once (typically 1 on consumer hardware),
    dynamically swapping based on required capability.

    Singleton pattern via module-level instance.
    """

    _instance: Optional["ModelOrchestrator"] = None

    def __init__(self):
        self._loaded_models: Dict[str, LoadedModel] = {}
        self._lock = asyncio.Lock()

        # Configuration
        self.max_loaded_models = int(os.getenv("MAHOUN_MAX_LOADED_MODELS", "1"))
        self.model_dir = Path(os.getenv("MAHOUN_MODEL_DIR", "models"))

        # Capability Mapping (Capability -> GGUF Filename)
        # Can be overridden via env vars for flexibility
        self.capability_map = {
            ModelCapability.CODING: os.getenv(
                "MAHOUN_MODEL_PATH_CODING", "Qwen2.5-Coder-1.5B-Instruct.Q4_0.gguf"
            ),
            ModelCapability.REASONING: os.getenv(
                "MAHOUN_MODEL_PATH_REASONING", "granite-4.0-1b-IQ4_NL.gguf"
            ),
            ModelCapability.GENERAL: os.getenv(
                "MAHOUN_MODEL_PATH_GENERAL", "Llama-3.2-1B-Instruct-Q6_K.gguf"
            ),
        }

        logger.info(
            f"ModelOrchestrator initialized (max_models={self.max_loaded_models})"
        )

    @classmethod
    def get_instance(cls) -> "ModelOrchestrator":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = ModelOrchestrator()
        return cls._instance

    async def get_driver(self, capability: ModelCapability) -> LocalLLMDriver:
        """
        Get a ready-to-use driver for the requested capability.

        This will:
        1. Identify the target model file.
        2. Check if it's already loaded (return cached if so).
        3. If full, unload the least recently used model.
        4. Load the target model.
        """
        target_model_name = self.capability_map.get(capability)
        if not target_model_name:
            raise ValueError(f"No model mapped for capability: {capability}")

        async with self._lock:
            # 1. Hit cache
            if target_model_name in self._loaded_models:
                logger.debug(f"Cache hit for model: {target_model_name}")
                loaded = self._loaded_models[target_model_name]
                loaded.touch()
                return loaded.driver

            # 2. Miss - need to load
            logger.info(
                f"Cache miss for capability {capability} -> {target_model_name}"
            )

            # 3. Manage memory pressure
            if len(self._loaded_models) >= self.max_loaded_models:
                await self._evict_lru()

            # 4. Load new model
            return await self._load_model(target_model_name, capability)

    async def _load_model(
        self, model_name: str, capability: ModelCapability
    ) -> LocalLLMDriver:
        """Internal method to load a model implementation."""
        try:
            full_path = self.model_dir / model_name
            if not full_path.exists():
                # Fallback check for relative paths
                if Path(model_name).exists():
                    full_path = Path(model_name)
                else:
                    raise FileNotFoundError(f"Model file not found: {model_name}")

            logger.info(f"Loading {model_name}...")
            start_t = time.time()

            # Initialize driver (blocking IO wrapped in thread if needed,
            # but LocalLLMDriver is fast enough to just call for now or we can use ThreadPoolExecutor)
            driver = LocalLLMDriver(
                model_dir=str(self.model_dir),
                n_gpu_layers=int(os.getenv("MAHOUN_N_GPU_LAYERS", "0")),
                n_ctx=int(os.getenv("MAHOUN_N_CTX", "2048")),
            )

            # Verify model file matches what we expect or just load by filename
            # LocalLLMDriver.load takes just filename if in model_dir
            driver.load(model_name)

            elapsed = time.time() - start_t
            logger.info(f"✅ Loaded {model_name} in {elapsed:.2f}s")

            # Register
            self._loaded_models[model_name] = LoadedModel(
                driver=driver, model_name=model_name, capabilities={capability}
            )

            return driver

        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise RuntimeError(f"Model loading failed: {e}") from e

    async def _evict_lru(self):
        """Unload the Least Recently Used model."""
        if not self._loaded_models:
            return

        # Find oldest timestamp
        lru_model_name = min(
            self._loaded_models.keys(), key=lambda k: self._loaded_models[k].last_used
        )

        logger.info(f"Evicting LRU model: {lru_model_name}")
        loaded = self._loaded_models.pop(lru_model_name)

        # Unload
        try:
            loaded.driver.unload()
            del loaded
            # Force garbage collection if needed (optional)
            import gc

            gc.collect()
        except Exception as e:
            logger.warning(f"Error unloading model {lru_model_name}: {e}")

    def list_loaded(self) -> List[str]:
        """List currently loaded models."""
        return list(self._loaded_models.keys())

    async def shutdown(self):
        """Unload all models."""
        async with self._lock:
            for name, loaded in self._loaded_models.items():
                logger.info(f"Unloading {name}...")
                loaded.driver.unload()
            self._loaded_models.clear()


# Convenience global accessor
def get_orchestrator() -> ModelOrchestrator:
    return ModelOrchestrator.get_instance()
