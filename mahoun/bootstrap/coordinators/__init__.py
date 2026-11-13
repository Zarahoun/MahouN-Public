"""
Bootstrap Coordinators Package

Thin orchestration layer that uses injected services.
Coordinators contain NO business logic — only orchestration!

Coordinators:
- EmbeddingModelsCoordinator: Orchestrate embedding model loading
- LLMLoaderCoordinator: Orchestrate LLM loading
- AgentRegistryCoordinator: Orchestrate agent registration
"""

from mahoun.bootstrap.coordinators.embedding_models import EmbeddingModelsCoordinator
from mahoun.bootstrap.coordinators.llm_loader import LLMLoaderCoordinator
from mahoun.bootstrap.coordinators.agent_registry import AgentRegistryCoordinator

__all__ = [
    "EmbeddingModelsCoordinator",
    "LLMLoaderCoordinator", 
    "AgentRegistryCoordinator",
]
