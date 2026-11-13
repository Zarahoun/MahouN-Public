"""
Mahoun LLM Module
=================
LLM routing, loading, and inference components.

Components are lazily imported to avoid heavy dependencies at startup.
"""

from typing import TYPE_CHECKING

# Lazy imports to avoid loading heavy dependencies (torch, transformers) at startup
if TYPE_CHECKING:
    from .local_driver import LocalLLMDriver, GenerationConfig, ModelMetrics
    from .router import LLMRouter, LLMProvider, ModelConfig, LLMRouterError
    from .fallback import FALLBACK_CHAIN, MODEL_CAPS, AVAILABLE_MODELS


def __getattr__(name: str):
    """Lazy import for heavy modules."""
    if name in ("LocalLLMDriver", "GenerationConfig", "ModelMetrics"):
        from .local_driver import LocalLLMDriver, GenerationConfig, ModelMetrics
        return {"LocalLLMDriver": LocalLLMDriver, 
                "GenerationConfig": GenerationConfig, 
                "ModelMetrics": ModelMetrics}[name]
    
    if name in ("LLMRouter", "LLMProvider", "ModelConfig", "LLMRouterError"):
        from .router import LLMRouter, LLMProvider, ModelConfig, LLMRouterError
        return {"LLMRouter": LLMRouter,
                "LLMProvider": LLMProvider,
                "ModelConfig": ModelConfig,
                "LLMRouterError": LLMRouterError}[name]
    
    if name in ("FALLBACK_CHAIN", "MODEL_CAPS", "AVAILABLE_MODELS"):
        from .fallback import FALLBACK_CHAIN, MODEL_CAPS, AVAILABLE_MODELS
        return {"FALLBACK_CHAIN": FALLBACK_CHAIN,
                "MODEL_CAPS": MODEL_CAPS,
                "AVAILABLE_MODELS": AVAILABLE_MODELS}[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Router (lightweight)
    "LLMRouter",
    "LLMProvider", 
    "ModelConfig",
    "LLMRouterError",
    # Local driver (heavy - lazy loaded)
    "LocalLLMDriver",
    "GenerationConfig",
    "ModelMetrics",
    # Fallback config
    "FALLBACK_CHAIN",
    "MODEL_CAPS",
    "AVAILABLE_MODELS",
]
