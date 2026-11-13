"""
Unified Ingestion Pipeline
=========================

Provides a simple interface to the ingestion system.
Chooses the best available implementation (Enhanced > V2).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_pipeline import IngestionPipelineV2, IngestionResultV2

logger = logging.getLogger(__name__)

# Try to import enhanced pipeline
try:
    from .enhanced_pipeline import EnhancedIngestionPipeline
    from .enhanced_pipeline import EnhancedIngestionResult
    HAS_ENHANCED = True
except ImportError:  # pragma: no cover
    EnhancedIngestionPipeline = None  # type: ignore
    EnhancedIngestionResult = None  # type: ignore
    HAS_ENHANCED = False
    logger.info("Enhanced ingestion pipeline not available, using base pipeline")


class IngestionPipeline:
    """
    Unified ingestion pipeline that selects the best available implementation.
    
    Usage:
        pipeline = IngestionPipeline()
        await pipeline.initialize()
        
        result = await pipeline.ingest_document(
            doc_id="doc123",
            text="...",
            metadata={"title": "..."}
        )
    """
    
    def __init__(
        self,
        prefer_enhanced: bool = True,
        **kwargs
    ):
        """
        Initialize unified pipeline.
        
        Args:
            prefer_enhanced: Whether to use enhanced pipeline if available
            **kwargs: Passed to the selected pipeline implementation
        """
        self.prefer_enhanced = prefer_enhanced and HAS_ENHANCED
        self.kwargs = kwargs
        self._pipeline: Any = None
        self._initialized = False
        
        if self.prefer_enhanced:
            logger.info("Initialized unified pipeline (preferring enhanced)")
        else:
            logger.info("Initialized unified pipeline (using base V2)")
    
    async def initialize(self) -> None:
        """Initialize the selected pipeline implementation."""
        if self._initialized:
            return
            
        if self.prefer_enhanced:
            self._pipeline = EnhancedIngestionPipeline(**self.kwargs)
        else:
            self._pipeline = IngestionPipelineV2(**self.kwargs)
            
        await self._pipeline.initialize()
        self._initialized = True
        logger.info(f"Unified pipeline initialized with {'enhanced' if self.prefer_enhanced else 'base'} implementation")
    
    async def ingest_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Ingest a document.
        
        Returns:
            IngestionResult (EnhancedIngestionResult if enhanced pipeline used)
        """
        if not self._initialized:
            await self.initialize()
            
        return await self._pipeline.ingest_document(doc_id, text, metadata)
    
    async def ingest_file(
        self,
        file_path: str,
        doc_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Ingest a file.
        
        Returns:
            IngestionResult (EnhancedIngestionResult if enhanced pipeline used)
        """
        if not self._initialized:
            await self.initialize()
            
        return await self._pipeline.ingest_file(file_path, doc_id, metadata)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        if not self._initialized:
            return {}
        return self._pipeline.get_stats()
    
    async def close(self) -> None:
        """Close pipeline resources."""
        if self._pipeline and hasattr(self._pipeline, 'close'):
            await self._pipeline.close()
        self._initialized = False
        logger.info("Unified pipeline closed")


# Backward compatibility aliases
IngestionResult = IngestionResultV2

__all__ = [
    "IngestionPipeline",
    "IngestionResult",
]