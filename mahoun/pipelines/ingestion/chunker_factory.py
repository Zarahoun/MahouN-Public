"""
Chunker factory for ingestion pipeline.

Provides a small compatibility layer for selecting the desired chunker
implementation using environment configuration.
"""

import os
from enum import Enum
from typing import Optional

from mahoun.pipelines.ingestion.enhanced_chunker import EnhancedChunker, ChunkingConfig
from mahoun.pipelines.smart_chunker import SmartChunker


class ChunkerType(str, Enum):
    ENHANCED = "enhanced"
    SMART = "smart"
    SEMANTIC = "semantic"


class ChunkerFactory:
    @staticmethod
    def create_from_env(
        default_type: ChunkerType = ChunkerType.ENHANCED,
        chunk_size: int = 512,
        overlap: int = 50,
        preserve_sentences: bool = True,
        preserve_paragraphs: bool = True,
        dynamic_size: bool = True,
    ):
        """Create a chunker based on environment configuration."""
        chunker_type = os.getenv("MAHOUN_CHUNKER_TYPE", default_type.value).strip().lower()

        if chunker_type == ChunkerType.SMART.value:
            return SmartChunker(chunk_size=chunk_size, overlap=overlap)

        if chunker_type in (ChunkerType.ENHANCED.value, ChunkerType.SEMANTIC.value):
            config = ChunkingConfig(
                chunk_size=chunk_size,
                overlap=overlap,
                preserve_sentences=preserve_sentences,
                preserve_paragraphs=preserve_paragraphs,
                dynamic_size=dynamic_size,
            )
            return EnhancedChunker(config=config)

        # Fallback to enhanced chunker if the requested type is unknown.
        config = ChunkingConfig(
            chunk_size=chunk_size,
            overlap=overlap,
            preserve_sentences=preserve_sentences,
            preserve_paragraphs=preserve_paragraphs,
            dynamic_size=dynamic_size,
        )
        return EnhancedChunker(config=config)
