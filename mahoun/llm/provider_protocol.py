# mahoun/llm/provider_protocol.py
"""
LLM Provider Protocol — DI Abstraction for Multiple LLM Backends
=================================================================

Defines the contract that all LLM providers (OpenAI, Ollama, VLLM, HuggingFace, etc.)
must implement. This enables MAHOUN to operate in airgapped environments where OpenAI
is unavailable or undesirable.

Architectural Principles
------------------------
* **Provider Agnostic**: Services depend on the protocol, not concrete implementations
* **Airgap-First**: MAHOUN must work without external API access
* **Bootstrap Injection**: All providers are constructed and injected by bootstrap
* **Fail-Closed Degradation**: Services gracefully degrade when no provider is available

Provider Hierarchy
------------------
```
LLMProviderProtocol (Protocol/ABC)
├── OpenAIProvider
├── OllamaProvider  
├── VLLMProvider
├── HuggingFaceProvider
└── MockProvider (testing)
```

Usage Pattern
-------------
```python
# Service (consumer)
class QueryRewriter:
    def __init__(self, llm_provider: Optional[LLMProviderProtocol] = None):
        self._provider = llm_provider

# Bootstrap (producer)
from openai import OpenAI
provider = OpenAIProvider(client=OpenAI(api_key=...))
rewriter = QueryRewriter(llm_provider=provider)
```

References
----------
* Design: `.kiro/specs/dependency-injection-refactor/design.md` §2.11
* Requirements: `.kiro/specs/dependency-injection-refactor/bugfix.md` §2.11
* Task: `.kiro/specs/dependency-injection-refactor/tasks.md` Task 11
"""

import logging
from typing import Dict, List, Optional, Protocol, Any
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────────
# Core Domain Models
# ────────────────────────────────────────────────────────────────────────────────


@dataclass
class LLMMessage:
    """
    Single message in an LLM conversation.
    
    Attributes:
        role: Message role ("system", "user", "assistant")
        content: Message text content
    """
    role: str
    content: str


@dataclass
class LLMResponse:
    """
    Standardized LLM response across all providers.
    
    Attributes:
        content: Generated text content
        model: Model identifier used for generation
        usage: Token usage metadata (optional)
        metadata: Provider-specific metadata (optional)
    """
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    metadata: Optional[Dict[str, Any]] = None


# ────────────────────────────────────────────────────────────────────────────────
# Provider Protocol (DI Contract)
# ────────────────────────────────────────────────────────────────────────────────


class LLMProviderProtocol(Protocol):
    """
    Contract that all LLM providers must implement.
    
    This protocol enables dependency injection of different LLM backends
    (OpenAI, Ollama, VLLM, HuggingFace, local models, etc.) without services
    depending on specific provider implementations.
    
    Implementation Requirements
    ----------------------------
    * MUST be thread-safe (stateless or internally synchronized)
    * MUST handle errors gracefully (return empty/error response, never raise in production)
    * MUST complete within timeout budget (provider-specific SLA)
    * MUST log all failures at ERROR level with correlation_id
    * SHOULD support streaming for long responses (optional)
    
    Governance Contracts
    --------------------
    * **GC-LLM-1**: All provider calls MUST include correlation_id for audit trail
    * **GC-LLM-2**: PII scrubbing applied before external API calls
    * **GC-LLM-3**: Rate limiting enforced per provider (circuit breaker pattern)
    * **GC-LLM-4**: Provider failures MUST NOT crash the application (fail-closed)
    """
    
    def generate(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: str = "",
    ) -> LLMResponse:
        """
        Generate completion from messages.
        
        Args:
            messages: Conversation history (system, user, assistant messages)
            model: Model identifier (provider-specific, uses default if None)
            temperature: Sampling temperature [0.0, 2.0]
            max_tokens: Maximum tokens to generate
            correlation_id: Request tracking ID for audit trail
        
        Returns:
            LLMResponse with generated content and metadata
        
        Raises:
            Should NOT raise in production. Returns error response on failure.
        """
        ...
    
    def get_provider_name(self) -> str:
        """
        Return provider identifier (e.g., "openai", "ollama", "vllm").
        
        Used for logging, telemetry, and debugging.
        """
        ...
    
    def is_available(self) -> bool:
        """
        Check if provider is currently available.
        
        Returns:
            True if provider can accept requests, False otherwise
        """
        ...


# ────────────────────────────────────────────────────────────────────────────────
# Example OpenAI Provider Implementation (Reference)
# ────────────────────────────────────────────────────────────────────────────────


class OpenAIProvider:
    """
    OpenAI LLM provider implementation.
    
    This is a REFERENCE IMPLEMENTATION showing how to implement LLMProviderProtocol.
    Bootstrap is responsible for constructing this and injecting it into services.
    
    Constructor Injection Contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``client`` MUST be a pre-constructed OpenAI client (injected by bootstrap).
    This class does NOT construct the client itself.
    """
    
    def __init__(
        self,
        client: Any,  # openai.OpenAI type (avoiding hard import dependency)
        default_model: str = "gpt-3.5-turbo",
    ):
        """
        Args:
            client: Pre-constructed OpenAI client (injected by bootstrap)
            default_model: Default model to use when not specified
        """
        self._client = client
        self._default_model = default_model
        _logger.info(f"OpenAIProvider initialized (model={default_model})")
    
    def generate(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: str = "",
    ) -> LLMResponse:
        """Generate completion using OpenAI API."""
        import uuid
        correlation_id = correlation_id or f"openai-{uuid.uuid4().hex[:8]}"
        model = model or self._default_model
        
        try:
            # Convert to OpenAI message format
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            response = self._client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None
            
            return LLMResponse(
                content=response.choices[0].message.content.strip(),
                model=response.model,
                usage=usage,
                metadata={"correlation_id": correlation_id},
            )
            
        except Exception as e:
            _logger.error(
                f"[{correlation_id}] OpenAI API error: {e}",
                exc_info=True
            )
            return LLMResponse(
                content="",
                model=model,
                metadata={
                    "error": str(e),
                    "correlation_id": correlation_id,
                },
            )
    
    def get_provider_name(self) -> str:
        """Return provider identifier."""
        return "openai"
    
    def is_available(self) -> bool:
        """Check if OpenAI client is available."""
        return self._client is not None
