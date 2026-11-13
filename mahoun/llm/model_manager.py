#!/usr/bin/env python3
"""
Model Manager with Fallback Chains
===================================
Robust model loading with fallback strategies and error handling

Features:
- Automatic fallback chains
- Model size validation
- Memory monitoring
- Retry logic with exponential backoff
- Health checks
- Graceful degradation
"""

import os
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import torch
from transformers import AutoModel, AutoTokenizer, AutoModelForSequenceClassification
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)


class ModelManager:
    """Robust model manager with fallback chains and size validation"""
    
    # Fallback chains for different model types
    FALLBACK_CHAINS = {
        "embedding": [
            "BAAI/bge-m3",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            "sentence-transformers/all-MiniLM-L6-v2"  # Smallest fallback
        ],
        "nli": [
            "microsoft/deberta-v3-base",
            "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
            "cross-encoder/nli-deberta-v3-small"
        ],
        "ner": [
            "HooshvareLab/bert-base-parsbert-uncased",
            "xlm-roberta-base",  # Multilingual fallback
            None  # Disable NER if all fail
        ]
    }
    
    # Maximum model sizes (in GB) - جلوگیری از load شدن مدل‌های خیلی بزرگ
    MAX_MODEL_SIZES = {
        "embedding": 2.0,  # Max 2GB
        "nli": 1.5,        # Max 1.5GB
        "ner": 1.5,        # Max 1.5GB
        "default": 2.0     # Default max
    }
    
    # Model metadata (approximate sizes and parameters)
    MODEL_METADATA = {
        "BAAI/bge-m3": {"size_gb": 0.6, "params": "560M", "recommended": True},
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": {"size_gb": 1.1, "params": "278M", "recommended": True},
        "sentence-transformers/all-MiniLM-L6-v2": {"size_gb": 0.09, "params": "22M", "recommended": True},
        "microsoft/deberta-v3-base": {"size_gb": 0.5, "params": "184M", "recommended": True},
        "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli": {"size_gb": 0.7, "params": "184M", "recommended": True},
        "cross-encoder/nli-deberta-v3-small": {"size_gb": 0.15, "params": "44M", "recommended": True},
        "HooshvareLab/bert-base-parsbert-uncased": {"size_gb": 0.5, "params": "118M", "recommended": True},
        "xlm-roberta-base": {"size_gb": 1.1, "params": "270M", "recommended": True}
    }
    
    def __init__(
        self,
        cache_dir: str = "/app/models",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        enable_quantization: bool = False,
        max_memory_gb: Optional[float] = None,
        strict_size_check: bool = True
    ):
        """
        Initialize Model Manager
        
        Args:
            cache_dir: Cache directory for models
            max_retries: Maximum retry attempts
            retry_delay: Initial retry delay (exponential backoff)
            enable_quantization: Enable 8-bit quantization
            max_memory_gb: Maximum memory to use (None = no limit)
            strict_size_check: Reject models exceeding size limits
        """
        self.cache_dir = Path(cache_dir)
        # Only create cache_dir if we have permission (skip in tests with /app path)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # Use temp directory as fallback in test/restricted environments
            import tempfile
            self.cache_dir = Path(tempfile.gettempdir()) / "mahoun_model_cache"
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.enable_quantization = enable_quantization
        self.max_memory_gb = max_memory_gb
        self.strict_size_check = strict_size_check
        
        # Model cache
        self._models: Dict[str, Any] = {}
        self._tokenizers: Dict[str, Any] = {}
        self._load_stats: Dict[str, Dict[str, Any]] = {}
        
        # Set cache directory
        os.environ["TRANSFORMERS_CACHE"] = str(self.cache_dir)
        
        log.info(f"🚀 ModelManager initialized")
        log.info(f"   Cache: {self.cache_dir}")
        log.info(f"   Max retries: {self.max_retries}")
        log.info(f"   Quantization: {self.enable_quantization}")
        log.info(f"   Max memory: {self.max_memory_gb or 'unlimited'} GB")
        log.info(f"   Strict size check: {self.strict_size_check}")
    
    def _check_model_size(self, model_name: str, model_type: str) -> bool:
        """
        Check if model size is acceptable
        
        Args:
            model_name: Model name
            model_type: Model type
            
        Returns:
            True if size is OK, False otherwise
        """
        if not self.strict_size_check:
            return True
        
        # Get model metadata
        metadata = self.MODEL_METADATA.get(model_name, {})
        model_size = metadata.get("size_gb", 0)
        
        # Get max size for this type
        max_size = self.MAX_MODEL_SIZES.get(model_type, self.MAX_MODEL_SIZES["default"])
        
        if model_size > max_size:
            log.warning(
                f"⚠️ Model {model_name} ({model_size}GB) exceeds "
                f"max size for {model_type} ({max_size}GB)"
            )
            return False
        
        # Check available memory
        if self.max_memory_gb:
            current_usage = self._get_memory_usage_gb()
            if current_usage + model_size > self.max_memory_gb:
                log.warning(
                    f"⚠️ Loading {model_name} ({model_size}GB) would exceed "
                    f"memory limit ({self.max_memory_gb}GB, current: {current_usage:.2f}GB)"
                )
                return False
        
        return True
    
    def _get_memory_usage_gb(self) -> float:
        """Get current memory usage in GB"""
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024**3)
        return 0.0
    
    def _validate_model_name(self, model_name: str) -> bool:
        """
        Validate model name to prevent loading dangerous models
        
        Args:
            model_name: Model name to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not model_name:
            return False
        
        # Block known large models
        blocked_patterns = [
            "llama-2-70b",
            "llama-2-13b",
            "falcon-40b",
            "gpt-j-6b",
            "bloom-7b",
            "opt-66b",
            "gpt-neox-20b"
        ]
        
        model_lower = model_name.lower()
        for pattern in blocked_patterns:
            if pattern in model_lower:
                log.error(f"❌ Model {model_name} is blocked (too large)")
                return False
        
        return True
    
    def load_model_with_retry(
        self,
        model_name: str,
        model_type: str = "auto",
        **kwargs
    ) -> Optional[Any]:
        """
        Load model with retry logic and size validation
        
        Args:
            model_name: Model name or path
            model_type: Type of model (auto, embedding, nli, ner)
            **kwargs: Additional arguments for model loading
            
        Returns:
            Loaded model or None if failed
        """
        # Validate model name
        if not self._validate_model_name(model_name):
            log.error(f"❌ Model validation failed: {model_name}")
            return None
        
        # Check model size
        if not self._check_model_size(model_name, model_type):
            log.warning(f"⚠️ Skipping {model_name} due to size constraints")
            return None
        
        # Get model metadata
        metadata = self.MODEL_METADATA.get(model_name, {})
        size_gb = metadata.get("size_gb", "unknown")
        params = metadata.get("params", "unknown")
        
        for attempt in range(self.max_retries):
            try:
                log.info(
                    f"📥 Loading {model_name} "
                    f"(attempt {attempt + 1}/{self.max_retries}, "
                    f"size: {size_gb}GB, params: {params})"
                )
                
                start_time = time.time()
                
                # Load based on type
                if model_type == "embedding":
                    model = SentenceTransformer(
                        model_name,
                        cache_folder=str(self.cache_dir),
                        **kwargs
                    )
                elif model_type == "nli":
                    model = AutoModelForSequenceClassification.from_pretrained(
                        model_name,
                        cache_dir=self.cache_dir,
                        **self._get_quantization_config(),
                        **kwargs
                    )
                else:
                    # Auto-detect or general model
                    model = AutoModel.from_pretrained(
                        model_name,
                        cache_dir=self.cache_dir,
                        **self._get_quantization_config(),
                        **kwargs
                    )
                
                load_time = time.time() - start_time
                
                # Track stats
                self._load_stats[model_name] = {
                    "load_time": load_time,
                    "attempts": attempt + 1,
                    "size_gb": size_gb,
                    "params": params,
                    "timestamp": time.time()
                }
                
                log.info(f"✅ Successfully loaded {model_name} in {load_time:.2f}s")
                return model
                
            except Exception as e:
                log.warning(f"❌ Failed to load {model_name} (attempt {attempt + 1}): {e}")
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    log.info(f"⏳ Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    log.error(f"❌ All attempts failed for {model_name}")
        
        return None
    
    def load_tokenizer_with_retry(self, model_name: str, **kwargs) -> Optional[Any]:
        """Load tokenizer with retry logic"""
        for attempt in range(self.max_retries):
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    model_name,
                    cache_dir=self.cache_dir,
                    **kwargs
                )
                log.info(f"✅ Successfully loaded tokenizer for {model_name}")
                return tokenizer
                
            except Exception as e:
                log.warning(f"❌ Failed to load tokenizer for {model_name}: {e}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    log.error(f"❌ All tokenizer attempts failed for {model_name}")
        
        return None
    
    def get_model_with_fallback(
        self,
        model_type: str,
        **kwargs
    ) -> Optional[Any]:
        """
        Get model with fallback chain
        
        Args:
            model_type: Type of model (embedding, nli, ner)
            **kwargs: Additional arguments
            
        Returns:
            Loaded model or None if all fallbacks fail
        """
        if model_type not in self.FALLBACK_CHAINS:
            raise ValueError(f"Unknown model type: {model_type}")
        
        fallback_chain = self.FALLBACK_CHAINS[model_type]
        
        log.info(f"🔄 Loading {model_type} model with fallback chain ({len(fallback_chain)} options)")
        
        for i, model_name in enumerate(fallback_chain):
            if model_name is None:
                log.warning(f"⚠️ Reached end of fallback chain for {model_type}, disabling")
                return None
            
            # Check cache first
            cache_key = f"{model_type}:{model_name}"
            if cache_key in self._models:
                log.info(f"✅ Using cached {model_name}")
                return self._models[cache_key]
            
            # Try to load
            log.info(f"🔄 Trying {model_name} (option {i+1}/{len(fallback_chain)})")
            model = self.load_model_with_retry(
                model_name,
                model_type=model_type,
                **kwargs
            )
            
            if model is not None:
                # Cache successful model
                self._models[cache_key] = model
                
                if i > 0:
                    log.warning(f"⚠️ Using fallback model {model_name} for {model_type}")
                else:
                    log.info(f"✅ Using primary model {model_name} for {model_type}")
                
                return model
            
            log.warning(f"❌ Fallback {model_name} failed, trying next...")
        
        log.error(f"❌ All fallbacks failed for {model_type}")
        return None
    
    def get_tokenizer_with_fallback(
        self,
        model_type: str,
        **kwargs
    ) -> Optional[Any]:
        """Get tokenizer with fallback chain"""
        if model_type not in self.FALLBACK_CHAINS:
            raise ValueError(f"Unknown model type: {model_type}")
        
        fallback_chain = self.FALLBACK_CHAINS[model_type]
        
        for model_name in fallback_chain:
            if model_name is None:
                return None
            
            # Check cache
            cache_key = f"tokenizer:{model_name}"
            if cache_key in self._tokenizers:
                return self._tokenizers[cache_key]
            
            # Try to load
            tokenizer = self.load_tokenizer_with_retry(model_name, **kwargs)
            
            if tokenizer is not None:
                self._tokenizers[cache_key] = tokenizer
                return tokenizer
        
        return None
    
    def _get_quantization_config(self) -> Dict[str, Any]:
        """Get quantization configuration"""
        if not self.enable_quantization:
            return {}
        
        # Check if bitsandbytes is available
        try:
            import bitsandbytes
            log.info("✅ Using 8-bit quantization")
            return {
                "load_in_8bit": True,
                "device_map": "auto"
            }
        except ImportError:
            log.warning("⚠️ bitsandbytes not available, skipping quantization")
            return {}
    
    def unload_model(self, model_type: str, model_name: str = None):
        """Unload model to free memory"""
        if model_name:
            cache_key = f"{model_type}:{model_name}"
            if cache_key in self._models:
                del self._models[cache_key]
                log.info(f"🗑️ Unloaded {cache_key}")
        else:
            # Unload all models of this type
            keys_to_remove = [k for k in self._models.keys() if k.startswith(f"{model_type}:")]
            for key in keys_to_remove:
                del self._models[key]
            log.info(f"🗑️ Unloaded all {model_type} models")
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log.info("🧹 Cleared GPU cache")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models"""
        info = {
            "cache_dir": str(self.cache_dir),
            "loaded_models": list(self._models.keys()),
            "loaded_tokenizers": list(self._tokenizers.keys()),
            "fallback_chains": self.FALLBACK_CHAINS,
            "max_model_sizes": self.MAX_MODEL_SIZES,
            "quantization_enabled": self.enable_quantization,
            "strict_size_check": self.strict_size_check,
            "max_memory_gb": self.max_memory_gb,
            "load_stats": self._load_stats
        }
        
        # Memory usage
        if torch.cuda.is_available():
            info["gpu_memory"] = {
                "allocated_gb": torch.cuda.memory_allocated() / (1024**3),
                "cached_gb": torch.cuda.memory_reserved() / (1024**3),
                "total_gb": torch.cuda.get_device_properties(0).total_memory / (1024**3)
            }
        
        return info
    
    def health_check(self) -> Dict[str, Any]:
        """Check health of all model types"""
        results = {}
        
        for model_type in self.FALLBACK_CHAINS.keys():
            try:
                # Check if already loaded
                loaded_models = [k for k in self._models.keys() if k.startswith(f"{model_type}:")]
                
                if loaded_models:
                    results[model_type] = {
                        "status": "healthy",
                        "model_loaded": True,
                        "cached": True,
                        "model_name": loaded_models[0].split(":", 1)[1]
                    }
                else:
                    # Try to load
                    model = self.get_model_with_fallback(model_type)
                    results[model_type] = {
                        "status": "healthy" if model is not None else "failed",
                        "model_loaded": model is not None,
                        "cached": False
                    }
            except Exception as e:
                results[model_type] = {
                    "status": "error",
                    "error": str(e),
                    "model_loaded": False
                }
        
        return results
    
    def get_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for optimization"""
        recommendations = []
        
        # Check memory usage
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / (1024**3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            usage_percent = (allocated / total) * 100
            
            if usage_percent > 80:
                recommendations.append({
                    "type": "memory",
                    "severity": "high",
                    "message": f"GPU memory usage is high ({usage_percent:.1f}%)",
                    "suggestion": "Consider enabling quantization or unloading unused models"
                })
            elif usage_percent > 60:
                recommendations.append({
                    "type": "memory",
                    "severity": "medium",
                    "message": f"GPU memory usage is moderate ({usage_percent:.1f}%)",
                    "suggestion": "Monitor memory usage"
                })
        
        # Check if using fallback models
        for model_type, chain in self.FALLBACK_CHAINS.items():
            loaded = [k for k in self._models.keys() if k.startswith(f"{model_type}:")]
            if loaded:
                model_name = loaded[0].split(":", 1)[1]
                if model_name != chain[0]:  # Not using primary
                    recommendations.append({
                        "type": "fallback",
                        "severity": "low",
                        "message": f"Using fallback model for {model_type}: {model_name}",
                        "suggestion": f"Primary model {chain[0]} failed to load"
                    })
        
        # Check quantization
        if not self.enable_quantization and torch.cuda.is_available():
            recommendations.append({
                "type": "optimization",
                "severity": "low",
                "message": "Quantization is disabled",
                "suggestion": "Enable quantization to reduce memory usage"
            })
        
        return {
            "recommendations": recommendations,
            "count": len(recommendations),
            "timestamp": time.time()
        }


# Global model manager instance
_model_manager = None

def get_model_manager() -> ModelManager:
    """Get global model manager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


# Convenience functions
def get_embedding_model(**kwargs):
    """Get embedding model with fallback"""
    return get_model_manager().get_model_with_fallback("embedding", **kwargs)

def get_nli_model(**kwargs):
    """Get NLI model with fallback"""
    return get_model_manager().get_model_with_fallback("nli", **kwargs)

def get_ner_model(**kwargs):
    """Get NER model with fallback"""
    return get_model_manager().get_model_with_fallback("ner", **kwargs)
