"""
Local LLM Driver - GGUF Optimized
=================================
Lightweight local LLM driver optimized for GGUF quantized models.

Uses llama-cpp-python for efficient CPU inference on low-resource machines.
NO torch, NO transformers - pure llama.cpp backend.

Features:
- GGUF model support (4-bit, 8-bit quantization)
- CPU-optimized inference
- Low memory footprint
- Simple API
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class GenerationConfig:
    """Configuration for text generation."""
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for llama-cpp."""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repeat_penalty": self.repeat_penalty,
            "stop": self.stop or [],
        }


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    model_name: str = ""
    load_time_seconds: float = 0.0
    total_generations: int = 0
    total_tokens_generated: int = 0
    total_generation_time: float = 0.0
    
    @property
    def avg_generation_time(self) -> float:
        if self.total_generations == 0:
            return 0.0
        return self.total_generation_time / self.total_generations
    
    @property
    def tokens_per_second(self) -> float:
        if self.total_generation_time == 0:
            return 0.0
        return self.total_tokens_generated / self.total_generation_time


class LocalLLMDriver:
    """
    Lightweight local LLM driver for GGUF models.
    
    Uses llama-cpp-python for efficient CPU inference.
    Designed for low-resource machines (old laptops, etc.)
    
    Usage:
        driver = LocalLLMDriver(model_dir="./models")
        driver.load("llama-3.2-1b.Q4_K_M.gguf")
        response = driver.generate("Hello, how are you?")
    """
    
    def __init__(
        self,
        model_dir: Optional[str] = None,
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        n_gpu_layers: int = 0,
        verbose: bool = False,
    ):
        """
        Initialize the driver.
        
        Args:
            model_dir: Directory containing GGUF models
            n_ctx: Context window size
            n_threads: Number of CPU threads (None = auto)
            n_gpu_layers: Number of layers to offload to GPU (0 = CPU only)
            verbose: Enable verbose logging from llama.cpp
        """
        self.model_dir = Path(model_dir) if model_dir else Path("models")
        self.n_ctx = n_ctx
        self.n_threads = n_threads or os.cpu_count() or 4
        self.n_gpu_layers = n_gpu_layers
        self.verbose = verbose
        
        self._llm: Any = None
        self._model_path: Optional[Path] = None
        self.metrics = ModelMetrics()
        
        # Ensure model directory exists
        self.model_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_loaded(self) -> bool:
        """Check if a model is loaded."""
        return self._llm is not None
    
    @property
    def model_name(self) -> Optional[str]:
        """Get loaded model name."""
        if self._model_path:
            return self._model_path.name
        return None
    
    def load(self, model_name: str) -> None:
        """
        Load a GGUF model.
        
        Args:
            model_name: Model filename (e.g., "llama-3.2-1b.Q4_K_M.gguf")
            
        Raises:
            FileNotFoundError: If model not found
            ImportError: If llama-cpp-python not installed
            RuntimeError: If loading fails
        """
        # Find model file
        model_path = self._find_model(model_name)
        
        if not model_path:
            available = self.list_models()
            raise FileNotFoundError(
                f"Model '{model_name}' not found.\n"
                f"Available models: {available}"
            )
        
        logger.info(f"Loading GGUF model: {model_path.name}")
        start_time = time.time()
        
        try:
            # Import llama-cpp-python
            try:
                from llama_cpp import Llama
            except ImportError:
                raise ImportError(
                    "llama-cpp-python not installed.\n"
                    "Install with: pip install llama-cpp-python"
                )
            
            # Unload previous model
            if self._llm is not None:
                self.unload()
            
            # Load model
            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                verbose=self.verbose,
            )
            
            self._model_path = model_path
            load_time = time.time() - start_time
            
            self.metrics = ModelMetrics(
                model_name=model_path.name,
                load_time_seconds=load_time,
            )
            
            logger.info(f"Model loaded in {load_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise RuntimeError(f"Model loading failed: {e}") from e
    
    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate text from prompt.
        
        Args:
            prompt: Input prompt
            config: Generation configuration
            system_prompt: Optional system prompt
            
        Returns:
            Generated text
            
        Raises:
            RuntimeError: If model not loaded
        """
        if not self.is_loaded:
            raise RuntimeError(
                "No model loaded. Call load() first.\n"
                f"Available models: {self.list_models()}"
            )
        
        config = config or GenerationConfig()
        start_time = time.time()
        
        try:
            # Build full prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            # Generate
            output = self._llm(
                full_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                top_k=config.top_k,
                repeat_penalty=config.repeat_penalty,
                stop=config.stop,
            )
            
            # Extract text
            text = output["choices"][0]["text"]
            tokens_generated = output.get("usage", {}).get("completion_tokens", 0)
            
            # Update metrics
            generation_time = time.time() - start_time
            self.metrics.total_generations += 1
            self.metrics.total_tokens_generated += tokens_generated
            self.metrics.total_generation_time += generation_time
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise RuntimeError(f"Text generation failed: {e}") from e
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """
        Chat completion with message history.
        
        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            config: Generation configuration
            
        Returns:
            Assistant response
        """
        if not self.is_loaded:
            raise RuntimeError("No model loaded. Call load() first.")
        
        config = config or GenerationConfig()
        
        try:
            output = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                top_k=config.top_k,
                repeat_penalty=config.repeat_penalty,
                stop=config.stop,
            )
            
            return output["choices"][0]["message"]["content"].strip()
            
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise RuntimeError(f"Chat completion failed: {e}") from e
    
    def unload(self) -> None:
        """Unload model and free memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self._model_path = None
            logger.info("Model unloaded")
    
    def list_models(self) -> List[str]:
        """List available GGUF models."""
        if not self.model_dir.exists():
            return []
        
        models = []
        for f in self.model_dir.iterdir():
            if f.suffix.lower() == ".gguf":
                models.append(f.name)
        
        return sorted(models)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return {
            "model_name": self.metrics.model_name,
            "load_time_seconds": self.metrics.load_time_seconds,
            "total_generations": self.metrics.total_generations,
            "total_tokens_generated": self.metrics.total_tokens_generated,
            "avg_generation_time": self.metrics.avg_generation_time,
            "tokens_per_second": self.metrics.tokens_per_second,
        }
    
    def _find_model(self, model_name: str) -> Optional[Path]:
        """Find model file by name."""
        # Direct path
        if Path(model_name).exists():
            return Path(model_name)
        
        # In model directory
        model_path = self.model_dir / model_name
        if model_path.exists():
            return model_path
        
        # Add .gguf extension
        if not model_name.endswith(".gguf"):
            model_path = self.model_dir / f"{model_name}.gguf"
            if model_path.exists():
                return model_path
        
        # Search by partial name
        for f in self.model_dir.iterdir():
            if f.suffix.lower() == ".gguf" and model_name.lower() in f.name.lower():
                return f
        
        return None
    
    def __repr__(self) -> str:
        status = f"loaded={self.model_name}" if self.is_loaded else "not loaded"
        return f"LocalLLMDriver({status})"
    
    def __del__(self) -> None:
        """Cleanup on deletion."""
        self.unload()
