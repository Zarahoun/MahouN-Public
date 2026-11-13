"""
Enhanced Ingestion Pipeline
===========================
Enhanced version of IngestionPipeline with all accuracy improvements.

Integrates:
1. LLM-Enhanced Parser
2. Enhanced NER with cross-validation
3. Enhanced Chunker with better boundaries
4. Enhanced Embedding service
5. Validation and Quality Checks
6. LLM Refinement Service

This is a drop-in replacement for IngestionPipeline with improved accuracy.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import time

from .pipeline import IngestionResult
from .llm_enhanced_parser import LLMEnhancedParser
from .enhanced_ner import EnhancedNEREngine
from .enhanced_chunker import EnhancedChunker, ChunkingConfig
from .chunker_factory import ChunkerFactory, ChunkerType
from .enhanced_embedding import EnhancedEmbeddingService
from mahoun.graph.validation.validation_quality import DocumentValidator, QualityAssessor
from .llm_refiner import LLMRefinementService
from mahoun.pipelines.smart_chunker import Chunk

logger = logging.getLogger(__name__)


@dataclass
class EnhancedIngestionResult(IngestionResult):
    """Enhanced ingestion result with quality metrics"""
    quality_score: float = 0.0
    validation_passed: bool = True
    refinement_applied: bool = False


class EnhancedIngestionPipeline:
    """
    Enhanced Ingestion Pipeline with all accuracy improvements.
    
    This pipeline enhances the standard IngestionPipeline with:
    - LLM-based parsing refinement
    - Cross-validated NER
    - Semantic chunking
    - Better embeddings
    - Comprehensive validation
    - LLM refinement
    
    Usage:
        pipeline = EnhancedIngestionPipeline()
        await pipeline.initialize()
        
        result = await pipeline.ingest_document(
            doc_id="doc123",
            text="...",
            metadata={"title": "..."}
        )
    """
    
    def __init__(
        self,
        enable_llm_refinement: bool = True,
        enable_cross_validation: bool = True,
        enable_validation: bool = True,
        strict_validation: bool = False
    ):
        """
        Initialize Enhanced Ingestion Pipeline.
        
        Args:
            enable_llm_refinement: Enable LLM-based refinement
            enable_cross_validation: Enable NER cross-validation
            enable_validation: Enable validation and quality checks
            strict_validation: Use strict validation mode
        """
        # Core components (initialized lazily)
        self.chunker = None
        self.embedding_service = None
        self.vector_store = None
        
        # Enhanced components
        self.llm_parser = LLMEnhancedParser(enable_refinement=enable_llm_refinement)
        self.ner_engine = EnhancedNEREngine(enable_cross_validation=enable_cross_validation)
        self.validator = DocumentValidator(strict_mode=strict_validation) if enable_validation else None
        self.quality_assessor = QualityAssessor() if enable_validation else None
        self.refiner = LLMRefinementService(enable_refinement=enable_llm_refinement)
        
        self._initialized = False
        
        # Statistics
        self.stats = {
            "documents_ingested": 0,
            "total_chunks": 0,
            "total_embeddings": 0,
            "failed_ingestions": 0,
            "avg_processing_time_ms": 0.0,
            "avg_quality_score": 0.0,
            "validation_failures": 0
        }
        
        logger.info("EnhancedIngestionPipeline initialized")
    
    async def initialize(self):
        """Initialize all pipeline components"""
        if self._initialized:
            return
        
        # Initialize vector store
        from mahoun.pipelines.vector_store.manager import VectorStoreManager
        self.vector_store = VectorStoreManager()
        await self.vector_store.initialize()
        
        # Initialize chunker using factory (supports both Enhanced and LegalAware)
        # Controlled by MAHOUN_CHUNKER_TYPE environment variable
        self.chunker = ChunkerFactory.create_from_env(
            default_type=ChunkerType.ENHANCED  # Safe default for backward compatibility
        )
        logger.info(f"Initialized chunker: {type(self.chunker).__name__}")
        
        # Initialize enhanced embedding service
        self.embedding_service = EnhancedEmbeddingService()
        
        self._initialized = True
        logger.info("EnhancedIngestionPipeline fully initialized")
    
    async def ingest_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EnhancedIngestionResult:
        """
        Ingest a document with enhanced accuracy.
        
        Args:
            doc_id: Unique document identifier
            text: Document text content
            metadata: Optional metadata
        
        Returns:
            EnhancedIngestionResult with quality metrics
        """
        start_time = time.time()
        refinement_applied = False
        
        if not self._initialized:
            await self.initialize()
        
        try:
            # Step 1: Enhanced parsing (with LLM refinement if enabled)
            logger.debug(f"Enhanced parsing document {doc_id}")
            
            is_verdict = False
            if metadata and metadata.get("doc_type") == "verdict":
                is_verdict = True
            elif "رأی" in text[:200] or "دادنامه" in text[:200]:
                is_verdict = True
            
            chunks: List[Any] = []
            verdict_struct: Optional[Any] = None
            if is_verdict:
                logger.info(f"Detected verdict document: {doc_id}")
                
                # Use LLM-enhanced parser
                verdict_struct = await self.llm_parser.parse_enhanced(text, doc_id=doc_id)
                refinement_applied = True
                
                # Build chunks from verdict structure
                from mahoun.pipelines.vector_store.manager import build_verdict_chunks
                verdict_chunks_data = build_verdict_chunks(verdict_struct, doc_id)
                
                for i, vc in enumerate(verdict_chunks_data):
                    chunks.append(Chunk(
                        text=vc["text"],
                        chunk_id=f"{doc_id}_chunk_{i}",
                        start=0,
                        end=len(vc["text"]),
                        metadata=vc["metadata"]
                    ))
                
                # Enhanced NER (already applied in parser, but can be refined)
                entities = verdict_struct.get("entities", {})
                if entities:
                    # Re-extract with enhanced NER for cross-validation
                    enhanced_entities = self.ner_engine.extract(text)
                    # Merge results (prefer enhanced if more complete)
                    if len(enhanced_entities.get("persons", [])) > len(entities.get("persons", [])):
                        verdict_struct["entities"] = enhanced_entities
                
                # LLM refinement
                if self.refiner.enable_refinement:
                    verdict_struct = await self.refiner.refine_verdict_structure(
                        verdict_struct, text
                    )
                
                # Validation and quality assessment
                validation_passed = True
                quality_score = 1.0
                
                if self.validator:
                    validation_result = self.validator.validate_verdict(verdict_struct)
                    validation_passed = validation_result.is_valid
                    
                    if self.quality_assessor:
                        quality_metrics = self.quality_assessor.assess_quality(
                            verdict_struct, validation_result
                        )
                        quality_score = quality_metrics.overall_score
                        
                        if quality_score < 0.7:
                            logger.warning(
                                f"Low quality score ({quality_score:.2f}) for document {doc_id}"
                            )
                
            else:
                # Standard document - use enhanced chunking
                chunks = self.chunker.chunk_document(
                    text=text,
                    doc_id=doc_id,
                    metadata=metadata
                )
            
            if not chunks:
                logger.warning(f"No chunks created for document {doc_id}")
                return EnhancedIngestionResult(
                    success=False,
                    doc_id=doc_id,
                    chunks_created=0,
                    embeddings_created=0,
                    indexed=False,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    error="No chunks created",
                    quality_score=0.0,
                    validation_passed=False
                )
            
            logger.info(f"Created {len(chunks)} chunks for document {doc_id}")
            
            # Step 2: Generate embeddings using enhanced service
            logger.debug(f"Generating embeddings for {len(chunks)} chunks")
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_service.embed_texts(
                texts=chunk_texts,
                is_query=False
            )
            
            logger.info(f"Generated {len(embeddings)} embeddings")
            
            if len(embeddings) == 0:
                logger.error(f"No embeddings generated for document {doc_id}")
                return EnhancedIngestionResult(
                    success=False,
                    doc_id=doc_id,
                    chunks_created=len(chunks),
                    embeddings_created=0,
                    indexed=False,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    error="Embedding generation failed",
                    quality_score=quality_score if is_verdict else 0.0,
                    validation_passed=validation_passed if is_verdict else True
                )
            
            # Step 3: Store in vector database
            logger.debug(f"Storing embeddings in vector store")
            
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            chunk_metadatas = [chunk.metadata for chunk in chunks]
            
            if isinstance(embeddings, list):
                embeddings_list = embeddings
            elif hasattr(embeddings, 'tolist'):
                embeddings_list = embeddings.tolist()
            else:
                embeddings_list = list(embeddings)
            
            success = await self.vector_store.insert(
                ids=chunk_ids,
                embeddings=embeddings_list,
                metadatas=chunk_metadatas,
                texts=chunk_texts
            )
            
            if not success:
                logger.error(f"Failed to store embeddings for document {doc_id}")
                return EnhancedIngestionResult(
                    success=False,
                    doc_id=doc_id,
                    chunks_created=len(chunks),
                    embeddings_created=len(embeddings),
                    indexed=False,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    error="Vector store insertion failed",
                    quality_score=quality_score if is_verdict else 0.0,
                    validation_passed=validation_passed if is_verdict else True
                )
            
            # Update statistics
            processing_time_ms = (time.time() - start_time) * 1000
            self._update_stats(len(chunks), len(embeddings), processing_time_ms, quality_score)
            
            if not validation_passed:
                self.stats["validation_failures"] += 1
            
            logger.info(
                f"Successfully ingested document {doc_id}: "
                f"{len(chunks)} chunks, {len(embeddings)} embeddings, "
                f"quality={quality_score:.2f}, {processing_time_ms:.1f}ms"
            )
            
            return EnhancedIngestionResult(
                success=True,
                doc_id=doc_id,
                chunks_created=len(chunks),
                embeddings_created=len(embeddings),
                indexed=True,
                processing_time_ms=processing_time_ms,
                quality_score=quality_score if is_verdict else 0.0,
                validation_passed=validation_passed if is_verdict else True,
                refinement_applied=refinement_applied
            )
            
        except Exception as e:
            logger.error(f"Enhanced ingestion failed for document {doc_id}: {e}", exc_info=True)
            self.stats["failed_ingestions"] += 1
            
            return EnhancedIngestionResult(
                success=False,
                doc_id=doc_id,
                chunks_created=0,
                embeddings_created=0,
                indexed=False,
                processing_time_ms=(time.time() - start_time) * 1000,
                error=str(e),
                quality_score=0.0,
                validation_passed=False
            )
    
    def _update_stats(self, chunks: int, embeddings: int, time_ms: float, quality_score: float):
        """Update pipeline statistics"""
        self.stats["documents_ingested"] += 1
        self.stats["total_chunks"] += chunks
        self.stats["total_embeddings"] += embeddings
        
        n = self.stats["documents_ingested"]
        self.stats["avg_processing_time_ms"] = (
            (self.stats["avg_processing_time_ms"] * (n - 1) + time_ms) / n
        )
        self.stats["avg_quality_score"] = (
            (self.stats["avg_quality_score"] * (n - 1) + quality_score) / n
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        stats = self.stats.copy()
        
        if self.vector_store:
            stats["vector_store"] = self.vector_store.get_stats()
        
        if self.embedding_service:
            stats["embedding"] = self.embedding_service.get_stats()
        
        return stats
    
    async def close(self):
        """Cleanup pipeline resources"""
        if self.vector_store:
            await self.vector_store.close()
        logger.info("EnhancedIngestionPipeline closed")

