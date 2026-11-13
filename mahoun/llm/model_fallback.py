"""
Model Fallback System
======================

Automatic fallback to alternative models if primary fails.
"""

from dataclasses import dataclass
from typing import Any, Optional, List, Dict
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration"""
    name: str
    provider: str  # huggingface, openai, local
    model_id: str
    device: str
    priority: int  # Lower = higher priority
    max_retries: int = 3
    timeout: float = 30.0
    fallback_on_error: bool = True


class ModelFallbackManager:
    """
    Manages model fallback logic
    
    If primary model fails, automatically tries alternatives.
    """
    
    def __init__(self):
        """Initialize fallback manager"""
        self.models: Dict[str, List[ModelConfig]] = {
            "embedding": [],
            "llm": [],
            "reranker": [],
        }
        
        self.model_instances: Dict[str, Any] = {}
        self.failure_counts: Dict[str, int] = {}
        self.last_failure_time: Dict[str, float] = {}
        
        logger.info("Initialized ModelFallbackManager")
        
    def register_model(
        self,
        model_type: str,
        config: ModelConfig
    ):
        """Register a model configuration"""
        if model_type not in self.models:
            self.models[model_type] = []
            
        self.models[model_type].append(config)
        
        # Sort by priority
        self.models[model_type].sort(key=lambda x: x.priority)
        
        logger.info(f"Registered {model_type} model: {config.name} (priority={config.priority})")
        
    def get_model(
        self,
        model_type: str,
        force_reload: bool = False
    ) -> Optional[Any]:
        """
        Get model instance with automatic fallback
        
        Args:
            model_type: Type of model (embedding/llm/reranker)
            force_reload: Force reload model
            
        Returns:
            Model instance or None
        """
        if model_type not in self.models or not self.models[model_type]:
            logger.error(f"No models registered for type: {model_type}")
            return None
            
        # Try each model in priority order
        for config in self.models[model_type]:
            model_key = f"{model_type}:{config.name}"
            
            # Check if model is in cooldown after failure
            if not force_reload and model_key in self.last_failure_time:
                cooldown = 300  # 5 minutes
                if time.time() - self.last_failure_time[model_key] < cooldown:
                    logger.debug(f"Model {config.name} in cooldown, skipping")
                    continue
                    
            # Try to load model
            try:
                # Check if already loaded
                if not force_reload and model_key in self.model_instances:
                    return self.model_instances[model_key]
                    
                # Load model
                logger.info(f"Loading {model_type} model: {config.name}")
                model = self._load_model(config)
                
                if model is not None:
                    self.model_instances[model_key] = model
                    logger.info(f"✅ Successfully loaded: {config.name}")
                    return model
                    
            except Exception as e:
                logger.error(f"Failed to load {config.name}: {e}")
                self.failure_counts[model_key] = self.failure_counts.get(model_key, 0) + 1
                self.last_failure_time[model_key] = time.time()
                
                if not config.fallback_on_error:
                    raise
                    
                # Try next model
                continue
                
        logger.error(f"All {model_type} models failed to load")
        return None
        
    def _load_model(self, config: ModelConfig) -> Optional[Any]:
        """Load model based on configuration"""
        if config.provider == "huggingface":
            return self._load_huggingface_model(config)
        elif config.provider == "openai":
            return self._load_openai_model(config)
        elif config.provider == "local":
            return self._load_local_model(config)
        else:
            logger.error(f"Unknown provider: {config.provider}")
            return None
            
    def _load_huggingface_model(self, config: ModelConfig) -> Optional[Any]:
        """Load HuggingFace model"""
        try:
            if "sentence-transformers" in config.model_id or config.name == "embedding":
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(config.model_id)
                
                # Move to device
                import torch
                if config.device == "cuda" and torch.cuda.is_available():
                    model = model.to("cuda")
                    
                return model
                
            else:
                from transformers import AutoModel, AutoTokenizer
                model = AutoModel.from_pretrained(config.model_id)
                tokenizer = AutoTokenizer.from_pretrained(config.model_id)
                
                return {"model": model, "tokenizer": tokenizer}
                
        except Exception as e:
            logger.error(f"HuggingFace model load failed: {e}")
            return None
            
    def _load_openai_model(self, config: ModelConfig) -> Optional[Any]:
        """Load OpenAI model (just config, actual calls are API-based)"""
        try:
            import openai
            import os
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set")
                return None
                
            openai.api_key = api_key
            
            return {
                "provider": "openai",
                "model": config.model_id,
                "client": openai
            }
            
        except Exception as e:
            logger.error(f"OpenAI setup failed: {e}")
            return None
            
    def _load_local_model(self, config: ModelConfig) -> Optional[Any]:
        """Load local model"""
        try:
            import torch
            model = torch.load(config.model_id)
            
            if config.device == "cuda" and torch.cuda.is_available():
                model = model.to("cuda")
                
            return model
            
        except Exception as e:
            logger.error(f"Local model load failed: {e}")
            return None
            
    def get_statistics(self) -> Dict[str, Any]:
        """Get fallback statistics"""
        stats = {
            "registered_models": {
                model_type: len(configs)
                for model_type, configs in self.models.items()
            },
            "loaded_models": len(self.model_instances),
            "failures": self.failure_counts,
        }
        
        return stats


# ============================================================================
# Pre-configured Fallback Chains
# ============================================================================

def setup_minimal_fallback() -> ModelFallbackManager:
    """Setup minimal fallback for Colab"""
    manager = ModelFallbackManager()
    
    # Embedding models (از کوچک به بزرگ)
    manager.register_model("embedding", ModelConfig(
        name="minilm",
        provider="huggingface",
        model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cuda",
        priority=1
    ))
    
    manager.register_model("embedding", ModelConfig(
        name="distiluse",
        provider="huggingface",
        model_id="sentence-transformers/distiluse-base-multilingual-cased-v2",
        device="cuda",
        priority=2
    ))
    
    # LLM models
    manager.register_model("llm", ModelConfig(
        name="flan-t5-base",
        provider="huggingface",
        model_id="google/flan-t5-base",
        device="cuda",
        priority=1
    ))
    
    manager.register_model("llm", ModelConfig(
        name="gpt-3.5",
        provider="openai",
        model_id="gpt-3.5-turbo",
        device="cpu",
        priority=2
    ))
    
    logger.info("Minimal fallback configured")
    return manager


def setup_production_fallback() -> ModelFallbackManager:
    """Setup production fallback with all models"""
    manager = ModelFallbackManager()
    
    # Embedding models
    models = [
        ("bge-m3", "BAAI/bge-m3", 1),
        ("mpnet", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2", 2),
        ("minilm", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 3),
    ]
    
    for name, model_id, priority in models:
        manager.register_model("embedding", ModelConfig(
            name=name,
            provider="huggingface",
            model_id=model_id,
            device="cuda",
            priority=priority
        ))
    
    # LLM models
    llm_models = [
        ("gpt-4", "openai", "gpt-4-turbo-preview", 1),
        ("gpt-3.5", "openai", "gpt-3.5-turbo", 2),
        ("flan-t5-xl", "huggingface", "google/flan-t5-xl", 3),
        ("flan-t5-base", "huggingface", "google/flan-t5-base", 4),
    ]
    
    for name, provider, model_id, priority in llm_models:
        manager.register_model("llm", ModelConfig(
            name=name,
            provider=provider,
            model_id=model_id,
            device="cuda" if provider == "huggingface" else "cpu",
            priority=priority
        ))
    
    logger.info("Production fallback configured")
    return manager


# ============================================================================
# Global Instance
# ============================================================================

_fallback_manager: Optional[ModelFallbackManager] = None


def get_fallback_manager(mode: str = "minimal") -> ModelFallbackManager:
    """Get or create fallback manager"""
    global _fallback_manager
    
    if _fallback_manager is None:
        if mode == "minimal":
            _fallback_manager = setup_minimal_fallback()
        else:
            _fallback_manager = setup_production_fallback()
            
    return _fallback_manager
