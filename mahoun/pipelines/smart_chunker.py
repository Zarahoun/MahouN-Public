"""
Smart Chunker - MVP Adapter
============================
Adapter for semantic chunking that wraps ultra_systems.chunking.

This provides a simplified interface for document chunking in the ingestion pipeline.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """
    A document chunk.

    Attributes:
        text: The chunk text
        chunk_id: Unique identifier
        start: Start position in original document
        end: End position in original document
        metadata: Additional metadata
    """

    text: str
    chunk_id: str
    start: int
    end: int
    metadata: Dict[str, Any]


class SmartChunker:
    """
    Smart Chunker for MAHOUN MVP.

    This adapter wraps ultra_systems.chunking.ultra_semantic_chunker
    and provides a simple interface for the ingestion pipeline.

    Usage:
        chunker = SmartChunker()
        chunks = chunker.chunk_document(
            text="...",
            doc_id="doc123"
        )
    """

    def __init__(
        self, chunk_size: int = 512, overlap: int = 50, strategy: str = "semantic"
    ):
        """
        Initialize Smart Chunker.

        Args:
            chunk_size: Target chunk size in characters
            overlap: Overlap between chunks
            strategy: Chunking strategy (semantic, fixed, paragraph)
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.strategy = strategy
        self._chunker = None

        logger.info(
            f"SmartChunker initialized (strategy: {strategy}, size: {chunk_size})"
        )

    def _get_chunker(self):
        """Lazy initialization of the underlying chunker"""
        if self._chunker is None:
            try:
                from mahoun.ultra_systems.chunking.ultra_semantic_chunker import (
                    UltraSemanticChunker,
                    ChunkingConfig,
                    ChunkingStrategy,
                )

                # Map strategy string to enum
                strategy_map = {
                    "semantic": ChunkingStrategy.SEMANTIC,
                    "fixed": ChunkingStrategy.FIXED_SIZE,
                    "paragraph": ChunkingStrategy.PARAGRAPH,
                    "hybrid": ChunkingStrategy.HYBRID,
                }

                strategy_enum = strategy_map.get(
                    self.strategy.lower(), ChunkingStrategy.HYBRID
                )

                config = ChunkingConfig(
                    strategy=strategy_enum,
                    chunk_size=self.chunk_size,
                    overlap=self.overlap,
                )

                self._chunker = UltraSemanticChunker(config)
                logger.info("Underlying UltraSemanticChunker initialized")

            except ImportError as e:
                logger.error(f"Failed to import UltraSemanticChunker: {e}")
                logger.warning("Falling back to simple fixed-size chunking")
                self._chunker = None

        return self._chunker

    def chunk_document(
        self, text: str, doc_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Chunk a document into smaller pieces.

        Args:
            text: Document text
            doc_id: Document ID
            metadata: Optional metadata to attach to chunks

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for doc_id: {doc_id}")
            return []

        # Get chunker
        chunker = self._get_chunker()

        if chunker:
            # Use semantic chunker
            try:
                ultra_chunks = chunker.chunk(text, doc_id=doc_id)

                # Convert to our Chunk format
                chunks: List[Any] = []
                for uc in ultra_chunks:
                    chunk_metadata = metadata.copy() if metadata else {}
                    chunk_metadata.update(uc.metadata)
                    chunk_metadata["doc_id"] = doc_id

                    chunks.append(
                        Chunk(
                            text=uc.text,
                            chunk_id=uc.chunk_id,
                            start=uc.start,
                            end=uc.end,
                            metadata=chunk_metadata,
                        )
                    )

                logger.debug(f"Chunked document {doc_id} into {len(chunks)} chunks")
                # Apply legal article boundary anchoring
                chunks = self._anchor_chunk_boundaries_to_legal_articles(chunks, text)
                return chunks

            except Exception as e:
                logger.error(
                    f"Semantic chunking failed: {e}, falling back to simple chunking"
                )

        # Fallback: simple fixed-size chunking
        chunks = self._simple_chunk(text, doc_id, metadata)
        # Apply legal article boundary anchoring
        chunks = self._anchor_chunk_boundaries_to_legal_articles(chunks, text)
        return chunks

    def _anchor_chunk_boundaries_to_legal_articles(
        self, chunks: List[Chunk], text: str
    ) -> List[Chunk]:
        """
        Adjust chunk boundaries to not split legal articles.
        If a boundary falls inside a legal article, merge the adjacent chunks.

        Args:
            chunks: List of chunks from chunker
            text: Original document text

        Returns:
            List of chunks with boundaries anchored to legal article structure
        """
        if len(chunks) < 2:
            return chunks

        # Pattern for legal article (supports Persian and English)
        # Matches: "Article 123" or "ماده 123" (with optional whitespace and digits)
        article_pattern = re.compile(
            r'(?:\bArticle\s+\d+|\bماده\s+\d+)',
            re.UNICODE
        )

        i = 0
        while i < len(chunks) - 1:
            # Boundary between chunk i and i+1
            boundary = chunks[i].end  # same as chunks[i+1].start

            # Check if boundary splits a legal article
            if self._boundary_splits_legal_article(boundary, text, article_pattern):
                # Merge chunks i and i+1
                merged_text = chunks[i].text + chunks[i+1].text
                merged_chunk = Chunk(
                    text=merged_text,
                    chunk_id=chunks[i].chunk_id,  # keep first chunk's ID
                    start=chunks[i].start,
                    end=chunks[i+1].end,
                    metadata={
                        **chunks[i].metadata,
                        "merged": True,
                        "merged_with": chunks[i+1].chunk_id,
                        "original_chunk_count": 2
                    }
                )
                # Replace chunks[i] with merged chunk and remove i+1
                chunks[i] = merged_chunk
                del chunks[i+1]
                # Do not increment i; check the new merged chunk with next
            else:
                i += 1

        logger.debug(
            f"After legal article anchoring: {len(chunks)} chunks"
        )
        return chunks

    def _boundary_splits_legal_article(
        self, boundary: int, text: str, pattern: re.Pattern
    ) -> bool:
        """
        Check if a boundary position splits a legal article match.

        Args:
            boundary: Character position in text (0-indexed)
            text: Original document text
            pattern: Compiled regex pattern for legal article

        Returns:
            True if boundary is inside a legal article match (not at edges)
        """
        for match in pattern.finditer(text):
            match_start, match_end = match.span()
            # Boundary is inside the match (not at the very start or end)
            if match_start < boundary < match_end:
                return True
        return False

    def _simple_chunk(
        self, text: str, doc_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Fallback simple chunking.

        Splits text into fixed-size chunks with overlap.
        """
        chunks: List[Any] = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_metadata = metadata.copy() if metadata else {}
                chunk_metadata["doc_id"] = doc_id
                chunk_metadata["chunk_index"] = chunk_index

                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_id=f"{doc_id}_chunk_{chunk_index}",
                        start=start,
                        end=end,
                        metadata=chunk_metadata,
                    )
                )

                chunk_index += 1

            start = end - self.overlap
            if start >= len(text):
                break

        logger.debug(f"Simple chunked document {doc_id} into {len(chunks)} chunks")
        return chunks
