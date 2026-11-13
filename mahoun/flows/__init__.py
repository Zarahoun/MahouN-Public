"""
Flows Module
============
High-level pipeline orchestration for RAG and other flows.
"""

from .enhanced_rag import EnhancedRAGPipeline

# Alias for compatibility
EnhancedRAGFlow = EnhancedRAGPipeline

__all__ = [
    "EnhancedRAGPipeline",
    "EnhancedRAGFlow",  # Alias
]

