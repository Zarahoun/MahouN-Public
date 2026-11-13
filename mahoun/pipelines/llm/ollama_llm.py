"""
Ollama LLM Service
==================
Real integration with Ollama LLM API for local model inference.
"""

from typing import Any, Dict, List, Optional
import logging
import httpx
import asyncio

logger = logging.getLogger(__name__)


class OllamaLLMService:
    """
    Service for interacting with Ollama LLM.
    
    Supports both sync and async operations with Ollama API.
    """
    
    def __init__(
        self, 
        model: str = "llama2", 
        base_url: str = "http://localhost:11434",
        timeout: int = 120
    ):
        """
        Initialize Ollama LLM Service.
        
        Args:
            model: Model name to use (e.g., "llama2", "mistral", "codellama")
            base_url: Base URL for Ollama API (default: http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = None
        logger.info(f"OllamaLLMService initialized (model={model}, base_url={base_url})")
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self.client
    
    async def _check_ollama_available(self) -> bool:
        """Check if Ollama server is available"""
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama server not available at {self.base_url}: {e}")
            return False
    
    async def generate(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate text from prompt using Ollama.
        
        Args:
            prompt: Input prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text
        """
        # Check if Ollama is available
        if not await self._check_ollama_available():
            logger.warning("Ollama server not available, returning placeholder response")
            return f"[Ollama LLM placeholder response for: {prompt[:50]}...]"
        
        try:
            client = self._get_client()
            
            # Prepare request
            request_data = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    **kwargs
                }
            }
            
            if max_tokens:
                request_data["options"]["num_predict"] = max_tokens
            
            # Make request
            response = await client.post("/api/generate", json=request_data)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result.get("response", "")
            
            logger.debug(f"Generated {len(generated_text)} characters from Ollama")
            return generated_text
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Ollama: {e}")
            return f"[Error: Ollama API call failed - {str(e)}]"
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama: {e}")
            return f"[Error: {str(e)}]"
    
    async def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Chat completion using Ollama.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
                      Roles: 'system', 'user', 'assistant'
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            Response text
        """
        # Check if Ollama is available
        if not await self._check_ollama_available():
            logger.warning("Ollama server not available, returning placeholder response")
            if messages:
                last_message = messages[-1].get("content", "")
                return f"[Ollama LLM placeholder chat response for: {last_message[:50]}...]"
            return "[Ollama LLM placeholder response]"
        
        try:
            client = self._get_client()
            
            # Prepare request
            request_data = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    **kwargs
                }
            }
            
            # Make request
            response = await client.post("/api/chat", json=request_data)
            response.raise_for_status()
            
            result = response.json()
            response_message = result.get("message", {})
            generated_text = response_message.get("content", "")
            
            logger.debug(f"Chat completion: {len(generated_text)} characters from Ollama")
            return generated_text
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Ollama chat: {e}")
            return f"[Error: Ollama API call failed - {str(e)}]"
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama chat: {e}")
            return f"[Error: {str(e)}]"
    
    async def list_models(self) -> List[str]:
        """
        List available models from Ollama.
        
        Returns:
            List of model names
        """
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            return models
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
    
    async def check_model_available(self, model_name: Optional[str] = None) -> bool:
        """
        Check if a specific model is available.
        
        Args:
            model_name: Model name to check (defaults to self.model)
            
        Returns:
            True if model is available
        """
        model = model_name or self.model
        available_models = await self.list_models()
        return model in available_models
    
    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.client:
            try:
                asyncio.create_task(self.client.aclose())
            except RuntimeError:
                # Event loop may not be running - this is expected during shutdown
                pass
