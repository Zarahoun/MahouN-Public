"""
Enhanced Chunker with Better Semantic Boundaries
================================================
Improves chunking by:
1. Better detection of semantic boundaries
2. Preserving context between chunks
3. Avoiding splitting within sentences/paragraphs
4. Dynamic chunk size based on content type
"""

import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from mahoun.pipelines.smart_chunker import Chunk

logger = logging.getLogger(__name__)


@dataclass
class ChunkingConfig:
    """Configuration for enhanced chunking"""
    chunk_size: int = 512
    overlap: int = 50
    min_chunk_size: int = 100
    preserve_sentences: bool = True
    preserve_paragraphs: bool = True
    dynamic_size: bool = True


class EnhancedChunker:
    """
    Enhanced chunker with better semantic boundary detection.
    """
    
    def __init__(
        self,
        config: Optional[ChunkingConfig] = None,
        fallback_chunker=None
    ):
        """
        Initialize Enhanced Chunker.
        
        Args:
            config: Chunking configuration
            fallback_chunker: Fallback chunker (e.g., SmartChunker)
        """
        self.config = config or ChunkingConfig()
        self.fallback_chunker = fallback_chunker
        logger.info("EnhancedChunker initialized")
    
    def chunk_document(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Chunk document with enhanced semantic boundaries.
        
        Args:
            text: Document text
            doc_id: Document ID
            metadata: Optional metadata
        
        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for doc_id: {doc_id}")
            return []
        
        # Detect content type for dynamic sizing
        content_type = self._detect_content_type(text)
        
        # Adjust chunk size based on content
        chunk_size = self._get_dynamic_chunk_size(content_type)
        
        # Perform enhanced chunking
        chunks = self._enhanced_chunk(text, doc_id, chunk_size, metadata)
        
        # Post-process chunks
        chunks = self._post_process_chunks(chunks, text)
        
        logger.info(f"Enhanced chunked document {doc_id} into {len(chunks)} chunks")
        return chunks
    
    def _detect_content_type(self, text: str) -> str:
        """Detect content type (verdict, law, contract, etc.)"""
        text_lower = text[:500].lower()
        
        if "رأی" in text_lower or "دادنامه" in text_lower:
            return "verdict"
        elif "ماده" in text_lower and "قانون" in text_lower:
            return "law"
        elif "قرارداد" in text_lower or "عقد" in text_lower:
            return "contract"
        else:
            return "general"
    
    def _get_dynamic_chunk_size(self, content_type: str) -> int:
        """Get dynamic chunk size based on content type"""
        if not self.config.dynamic_size:
            return self.config.chunk_size
        
        base_size = self.config.chunk_size
        
        # Adjust based on content type
        if content_type == "verdict":
            # Verdicts often have structured sections, can use larger chunks
            return int(base_size * 1.2)
        elif content_type == "law":
            # Law articles are usually self-contained, standard size
            return base_size
        elif content_type == "contract":
            # Contracts need careful parsing, smaller chunks
            return int(base_size * 0.9)
        else:
            return base_size
    
    def _enhanced_chunk(
        self,
        text: str,
        doc_id: str,
        chunk_size: int,
        metadata: Optional[Dict[str, Any]]
    ) -> List[Chunk]:
        """Perform enhanced chunking with semantic boundaries"""
        
        chunks: List[Any] = []
        chunk_index = 0
        position = 0
        text_length = len(text)
        
        while position < text_length:
            # Determine chunk end position
            chunk_end = min(position + chunk_size, text_length)
            
            # Adjust end to respect semantic boundaries
            if chunk_end < text_length:
                chunk_end = self._find_semantic_boundary(
                    text, position, chunk_end, chunk_size
                )
            
            # Extract chunk text
            chunk_text = text[position:chunk_end].strip()
            
            # Skip empty chunks
            if not chunk_text or len(chunk_text) < self.config.min_chunk_size:
                # If we're near the end, break
                if chunk_end >= text_length - self.config.min_chunk_size:
                    break
                position = chunk_end
                continue
            
            # Create chunk
            chunk_metadata = metadata.copy() if metadata else {}
            chunk_metadata["doc_id"] = doc_id
            chunk_metadata["chunk_index"] = chunk_index
            
            chunks.append(Chunk(
                text=chunk_text,
                chunk_id=f"{doc_id}_chunk_{chunk_index}",
                start=position,
                end=chunk_end,
                metadata=chunk_metadata
            ))
            
            chunk_index += 1
            
            # Move position with overlap
            position = chunk_end - self.config.overlap
            if position < 0:
                position = 0
            
            # Break if we've processed everything
            if position >= text_length:
                break
        
        return chunks
    
    def _find_semantic_boundary(
        self,
        text: str,
        start: int,
        suggested_end: int,
        target_size: int
    ) -> int:
        """
        Find the best semantic boundary near the suggested end position.
        
        Tries to avoid splitting:
        - Within sentences
        - Within paragraphs
        - Within Arabic/Persian words
        """
        # Search window around suggested end
        search_start = max(start, suggested_end - self.config.overlap)
        search_end = min(len(text), suggested_end + self.config.overlap)
        search_text = text[search_start:search_end]
        
        best_boundary = suggested_end
        best_score = 0
        
        # Candidate boundary positions (backward from suggested_end)
        candidates: List[Any] = []
        
        # PRIORITY 1: Legal-aware boundaries (BEFORE generic patterns)
        legal_boundaries = [
            r'\n\s*ماده\s+\d+',           # Article boundaries
            r'\n\s*بند\s+[ا-ی]',        # Clause boundaries  
            r'\n\s*تبصره\s*[:\d]',        # Note boundaries
            r'\n\s*(?:رأی|نظریه)\s+دادگاه', # Verdict section boundaries
            r'\n\s*(?:گردشکار|خلاصه)\s*:', # Summary section boundaries
            r'\n\s*(?:مستند|استناد)\s*:', # Citation section boundaries
        ]
        
        for pattern in legal_boundaries:
            legal_matches = [
                search_start + m.start()
                for m in re.finditer(pattern, search_text)
            ]
            candidates.extend(legal_matches)
        
        # Look for paragraph breaks
        if self.config.preserve_paragraphs:
            para_breaks = [
                search_start + m.start()
                for m in re.finditer(r'\n\s*\n', search_text)
            ]
            candidates.extend(para_breaks)
        
        # Look for sentence endings
        if self.config.preserve_sentences:
            # Persian sentence endings
            sentence_endings = [
                search_start + m.start() + len(m.group())
                for m in re.finditer(r'[.!?]\s+', search_text)
            ]
            candidates.extend(sentence_endings)
        
        # Look for common section markers
        section_markers = [
            search_start + m.start()
            for m in re.finditer(r'\n\s*[۰-۹\d]+\s*[\.-]\s*', search_text)
        ]
        candidates.extend(section_markers)
        
        # Evaluate candidates
        for candidate in candidates:
            if start < candidate <= search_end:
                # Score based on proximity to target size
                distance = abs(candidate - suggested_end)
                score = 1.0 / (1.0 + distance / 10.0)
                
                if score > best_score:
                    best_score = score
                    best_boundary = candidate
        
        # If no good boundary found, try to avoid splitting words
        if best_boundary == suggested_end:
            # Look for space or punctuation near the end
            for i in range(suggested_end, max(start, suggested_end - 50), -1):
                if text[i] in [' ', '\n', '\t', '.', '،', ';']:
                    best_boundary = i + 1
                    break
        
        return best_boundary
    
    def _post_process_chunks(
        self,
        chunks: List[Chunk],
        original_text: str
    ) -> List[Chunk]:
        """Post-process chunks to ensure quality"""
        
        processed: List[Any] = []
        for chunk in chunks:
            # Skip chunks that are too short (unless it's the last one)
            if len(chunk.text.strip()) < self.config.min_chunk_size:
                # Try to merge with previous chunk if possible
                if processed and len(processed[-1].text) < self.config.chunk_size * 1.5:
                    # Merge with previous
                    prev_chunk = processed[-1]
                    merged_text = prev_chunk.text + " " + chunk.text
                    prev_chunk.text = merged_text.strip()
                    prev_chunk.end = chunk.end
                    continue
                else:
                    # Keep it if it's meaningful (contains some content)
                    if len(chunk.text.strip()) > 30:
                        processed.append(chunk)
                    continue
            
            # Clean up chunk text
            chunk.text = chunk.text.strip()
            
            # Remove excessive whitespace
            chunk.text = re.sub(r'\s+', ' ', chunk.text)
            chunk.text = re.sub(r'\n\s*\n+', '\n\n', chunk.text)
            
            processed.append(chunk)
        
        return processed


# Convenience function
def chunk_document_enhanced(
    text: str,
    doc_id: str,
    chunk_size: int = 512,
    overlap: int = 50,
    metadata: Optional[Dict[str, Any]] = None
) -> List[Chunk]:
    """
    Chunk document with enhanced semantic boundaries.
    
    Args:
        text: Document text
        doc_id: Document ID
        chunk_size: Target chunk size
        overlap: Overlap between chunks
        metadata: Optional metadata
    
    Returns:
        List of Chunk objects
    """
    config = ChunkingConfig(
        chunk_size=chunk_size,
        overlap=overlap
    )
    chunker = EnhancedChunker(config=config)
    return chunker.chunk_document(text, doc_id, metadata)

