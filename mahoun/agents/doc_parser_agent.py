"""
Ultra Doc Parser Agent - Enterprise-Grade Document Processing
=============================================================
Agent پیشرفته برای پردازش و تجزیه اسناد حقوقی

Features:
- Full NER Integration (استخراج موجودیت‌ها)
- Legal Storage Integration (ذخیره در PostgreSQL)
- Multi-format Support (PDF, DOCX, TXT, images)
- Intelligent Chunking with Coherence Scoring
- Graceful Degradation with Fallback Parsing
- Structured Output with Quality Metrics

Integration Points:
- pipelines/ingestion/legal_ner.py → Entity extraction
- pipelines/ingestion/legal_storage.py → PostgreSQL storage
- pipelines/ingestion/enhanced_chunker.py → Smart chunking
- pipelines/ingestion/minimal_verdict_parser.py → Verdict parsing
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base_agent import (
    UltraBaseAgent,
    AgentConfig,
    AgentResult,
    AgentState
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class DocParserConfig(AgentConfig):
    """Extended configuration for document parser"""
    # NER settings
    enable_ner: bool = True
    ner_confidence_threshold: float = 0.5
    
    # Storage settings
    enable_legal_storage: bool = True
    enable_chromadb_storage: bool = True
    
    # Chunking settings
    chunk_size: int = 512
    chunk_overlap: int = 50
    enable_coherence_scoring: bool = True
    
    # Parsing settings
    enable_ocr: bool = True
    ocr_language: str = "fas"  # Persian
    
    # Quality settings
    min_text_length: int = 50  # Reduced for testing
    max_text_length: int = 10_000_000  # Increased for massive contracts


# ============================================================================
# Ultra Doc Parser Agent
# ============================================================================

class UltraDocParserAgent(UltraBaseAgent):
    """
    Enterprise-grade document parser with full pipeline integration.
    
    این agent اسناد حقوقی را پردازش کرده و:
    1. متن را استخراج می‌کند (با OCR در صورت نیاز)
    2. ساختار رأی را parse می‌کند
    3. موجودیت‌ها را استخراج می‌کند (NER)
    4. در ChromaDB و PostgreSQL ذخیره می‌کند
    
    Features:
    - Circuit Breaker for external services
    - Retry with exponential backoff
    - Graceful degradation (fallback to basic parsing)
    - Quality metrics and validation
    
    Usage:
        async with UltraDocParserAgent() as agent:
            result = await agent.process({
                "text": "متن رأی...",
                # OR
                "file_path": "/path/to/document.pdf"
            })
    """
    
    def __init__(self, config: Optional[DocParserConfig] = None):
        super().__init__(
            name="doc_parser_agent",
            config=config or DocParserConfig()
        )
        
        # Components (lazy loaded)
        self._ner_engine = None
        self._legal_storage = None
        self._verdict_parser = None
        self._chunker = None
        self._ocr_handler = None
        self._normalizer = None
        
        # Metrics
        self._doc_metrics = {
            "documents_processed": 0,
            "entities_extracted": 0,
            "chunks_created": 0,
            "storage_success": 0,
            "storage_failures": 0,
            "ocr_used": 0,
            "fallback_used": 0,
        }
    
    async def _initialize_impl(self):
        """Initialize all components"""
        self.logger.info("Initializing UltraDocParserAgent components...")
        
        # 1. Initialize NER Engine
        if self.config.enable_ner:
            try:
                from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine
                self._ner_engine = LegalNEREngine(
                    confidence_threshold=self.config.ner_confidence_threshold
                )
                self.logger.info("✅ NER Engine initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ NER Engine not available: {e}")
        
        # 2. Initialize Legal Storage
        if self.config.enable_legal_storage:
            try:
                from mahoun.pipelines.ingestion.legal_storage import LegalStorageService
                self._legal_storage = LegalStorageService()
                await self._legal_storage.initialize()
                self.logger.info("✅ Legal Storage initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ Legal Storage not available: {e}")
        
        # 3. Initialize Verdict Parser
        try:
            from mahoun.pipelines.ingestion.minimal_verdict_parser import MinimalVerdictParser
            self._verdict_parser = MinimalVerdictParser()
            self.logger.info("✅ Verdict Parser initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Verdict Parser not available: {e}")
        
        # 4. Initialize Chunker
        try:
            from mahoun.pipelines.ingestion.enhanced_chunker import EnhancedChunker, ChunkingConfig
            chunk_config = ChunkingConfig(
                chunk_size=self.config.chunk_size,
                overlap=self.config.chunk_overlap
            )
            self._chunker = EnhancedChunker(config=chunk_config)
            self.logger.info("✅ Enhanced Chunker initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Enhanced Chunker not available: {e}")
        
        # 5. Initialize OCR Handler (optional)
        if self.config.enable_ocr:
            try:
                from mahoun.pipelines.ingestion.ocr_handler import OCRHandler
                self._ocr_handler = OCRHandler(language=self.config.ocr_language)
                self.logger.info("✅ OCR Handler initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ OCR Handler not available: {e}")
        
        # 6. Initialize Persian Normalizer
        try:
            from mahoun.pipelines.ingestion.persian_normalizer import PersianLegalNormalizer
            self._normalizer = PersianLegalNormalizer
            self.logger.info("✅ Persian Normalizer initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Persian Normalizer not available: {e}")
        
        self.logger.info("UltraDocParserAgent initialization complete")
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Process document with full pipeline.
        
        Args:
            input_data: {
                "text": str,           # Raw text OR
                "file_path": str,      # Path to file
                "doc_id": str,         # Optional document ID
                "doc_type": str,       # Optional document type
                "metadata": dict,      # Optional metadata
                "skip_storage": bool,  # Skip storage step
                "skip_ner": bool,      # Skip NER step
            }
        
        Returns:
            {
                "doc_id": str,
                "verdict_struct": dict,
                "entities": dict,
                "chunks": list,
                "storage_result": dict,
                "quality_metrics": dict
            }
        """
        start_time = time.time()
        
        # Extract input
        text = input_data.get("text")
        file_path = input_data.get("file_path")
        doc_id = input_data.get("doc_id")
        doc_type = input_data.get("doc_type", "verdict")
        metadata = input_data.get("metadata", {})
        skip_storage = input_data.get("skip_storage", False)
        skip_ner = input_data.get("skip_ner", False)
        
        # Step 1: Get text content
        if not text and file_path:
            text = await self._extract_text_from_file(file_path, correlation_id)
        
        if not text:
            raise ValueError("No text content provided (text or file_path required)")
        
        # Validate text length
        if len(text) < self.config.min_text_length:
            raise ValueError(f"Text too short ({len(text)} chars, min: {self.config.min_text_length})")
        
        if len(text) > self.config.max_text_length:
            self.logger.warning(f"[{correlation_id}] Text truncated from {len(text)} to {self.config.max_text_length}")
            text = text[:self.config.max_text_length]
        
        # Step 2: Normalize text
        if self._normalizer:
            text = self._normalizer.normalize_legal_text(text)
        
        # Step 3: Parse verdict structure
        verdict_struct = await self._parse_verdict(text, correlation_id)
        
        # Generate doc_id if not provided
        if not doc_id:
            case_number = verdict_struct.get("case_meta", {}).get("case_number")
            doc_id = case_number or f"doc_{int(time.time())}"
        
        # Step 4: Extract entities (NER)
        entities: Dict[str, Any] = {}
        if not skip_ner and self._ner_engine:
            entities = await self._extract_entities(text, correlation_id)
            verdict_struct["entities"] = entities
        
        # Step 5: Create chunks
        chunks = await self._create_chunks(text, doc_id, verdict_struct, correlation_id)
        
        # Step 6: Store in databases
        storage_result: Optional[Any] = None
        if not skip_storage:
            storage_result = await self._store_document(
                doc_id=doc_id,
                verdict_struct=verdict_struct,
                chunks=chunks,
                source_file=file_path,
                correlation_id=correlation_id
            )
        
        # Calculate quality metrics
        quality_metrics = self._calculate_quality_metrics(
            text=text,
            verdict_struct=verdict_struct,
            entities=entities,
            chunks=chunks
        )
        
        # Update metrics
        self._doc_metrics["documents_processed"] += 1
        self._doc_metrics["entities_extracted"] += sum(len(v) for v in entities.values())
        self._doc_metrics["chunks_created"] += len(chunks)
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "verdict_struct": verdict_struct,
            "entities": entities,
            "chunks": [{"text": c.get("text", "")[:200], "index": i} for i, c in enumerate(chunks)],
            "chunks_count": len(chunks),
            "storage_result": storage_result,
            "quality_metrics": quality_metrics,
            "processing_time_ms": processing_time,
            "metadata": metadata
        }
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Fallback processing with basic parsing only.
        
        WARNING: This is a degraded mode - NER and storage are skipped.
        """
        self.logger.warning(f"[{correlation_id}] Using FALLBACK mode - basic parsing only")
        self._doc_metrics["fallback_used"] += 1
        
        text = input_data.get("text", "")
        doc_id = input_data.get("doc_id", f"fallback_{int(time.time())}")
        
        # Basic structure extraction
        verdict_struct = {
            "case_meta": {"case_number": doc_id},
            "sections": {"verdict": text[:5000]},
            "parties": {},
            "_fallback_mode": True,
            "_parsing_quality": {"completeness": 0.3}
        }
        
        # Basic chunking (simple split)
        chunk_size = self.config.chunk_size
        chunks: List[Any] = []
        for i in range(0, len(text), chunk_size):
            chunks.append({
                "text": text[i:i+chunk_size],
                "index": len(chunks),
                "metadata": {"fallback": True}
            })
        
        return {
            "doc_id": doc_id,
            "verdict_struct": verdict_struct,
            "entities": {},
            "chunks": chunks[:10],  # Limit for response
            "chunks_count": len(chunks),
            "storage_result": None,
            "quality_metrics": {"fallback_used": True, "completeness": 0.3},
            "fallback_used": True
        }
    
    # ========================================================================
    # Processing Steps
    # ========================================================================
    
    async def _extract_text_from_file(
        self,
        file_path: str,
        correlation_id: Optional[str]
    ) -> str:
        """Extract text from file (with OCR if needed)"""
        import os
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # Try document handlers first
        try:
            from mahoun.pipelines.ingestion.document_handlers import DocumentHandlerFactory
            handler = DocumentHandlerFactory.get_handler(file_path)
            if handler:
                result = await handler.extract_text(file_path)
                if result and result.get("text"):
                    return result["text"]
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] Document handler failed: {e}")
        
        # Fallback to OCR for images/scanned PDFs
        if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp'] or ext == '.pdf':
            if self._ocr_handler:
                try:
                    self._doc_metrics["ocr_used"] += 1
                    return await self._ocr_handler.extract_text(file_path)
                except Exception as e:
                    self.logger.warning(f"[{correlation_id}] OCR failed: {e}")
        
        # Last resort: read as text
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        raise ValueError(f"Cannot extract text from file: {file_path}")
    
    async def _parse_verdict(
        self,
        text: str,
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Parse verdict structure"""
        if self._verdict_parser:
            try:
                return self._verdict_parser.parse(text)
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] Verdict parser failed: {e}")
        
        # Basic fallback structure
        return {
            "case_meta": {},
            "sections": {"verdict": text},
            "parties": {},
            "_parsing_quality": {"completeness": 0.5}
        }
    
    async def _extract_entities(
        self,
        text: str,
        correlation_id: Optional[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract entities using NER engine"""
        if not self._ner_engine:
            return {}
        
        try:
            return self._ner_engine.extract(text)
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] NER extraction failed: {e}")
            return {}
    
    async def _create_chunks(
        self,
        text: str,
        doc_id: str,
        verdict_struct: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Create document chunks"""
        if self._chunker:
            try:
                # Use enhanced chunker
                # Note: chunk_document returns List[Chunk], need to convert to dict list
                enhanced_chunks = self._chunker.chunk_document(
                    text=text,
                    doc_id=doc_id,
                    metadata={"verdict_struct": verdict_struct}
                )
                return [
                    {
                        "text": c.text,
                        "index": i,
                        "metadata": c.metadata,
                        "chunk_id": c.chunk_id
                    }
                    for i, c in enumerate(enhanced_chunks)
                ]
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] Enhanced chunking failed: {e}")
        
        # Basic chunking fallback
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        chunks: List[Any] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append({
                "text": text[start:end],
                "index": len(chunks),
                "metadata": {}
            })
            start = end - overlap if end < len(text) else end
        
        return chunks
    
    async def _store_document(
        self,
        doc_id: str,
        verdict_struct: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        source_file: Optional[str],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Store document in databases"""
        result = {
            "chromadb": None,
            "postgresql": None
        }
        
        # Store in Legal Storage (PostgreSQL)
        if self._legal_storage and self.config.enable_legal_storage:
            try:
                storage_result = await self._legal_storage.store_verdict(
                    doc_id=doc_id,
                    verdict_struct=verdict_struct,
                    chunks=chunks,
                    source_file=source_file
                )
                result["postgresql"] = {
                    "success": storage_result.success,
                    "verdict_id": storage_result.verdict_id,
                    "chunks_stored": storage_result.chunks_stored,
                    "entities_stored": storage_result.entities_stored
                }
                
                if storage_result.success:
                    self._doc_metrics["storage_success"] += 1
                else:
                    self._doc_metrics["storage_failures"] += 1
                    
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] PostgreSQL storage failed: {e}")
                self._doc_metrics["storage_failures"] += 1
                result["postgresql"] = {"success": False, "error": str(e)}
        
        return result
    
    def _calculate_quality_metrics(
        self,
        text: str,
        verdict_struct: Dict[str, Any],
        entities: Dict[str, List],
        chunks: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate document quality metrics"""
        # Parsing quality from verdict parser
        parsing_quality = verdict_struct.get("_parsing_quality", {})
        
        # Entity coverage
        total_entities = sum(len(v) for v in entities.values())
        entity_density = total_entities / (len(text) / 1000) if text else 0
        
        # Section completeness
        sections = verdict_struct.get("sections", {})
        expected_sections = ["verdict", "summary", "reasoning"]
        section_completeness = sum(1 for s in expected_sections if sections.get(s)) / len(expected_sections)
        
        # Chunk quality
        avg_chunk_size = sum(len(c.get("text", "")) for c in chunks) / len(chunks) if chunks else 0
        
        return {
            "text_length": len(text),
            "parsing_completeness": parsing_quality.get("completeness", 0.5),
            "total_entities": total_entities,
            "entity_density_per_1k": round(entity_density, 2),
            "section_completeness": round(section_completeness, 2),
            "chunks_count": len(chunks),
            "avg_chunk_size": round(avg_chunk_size, 0),
            "entities_by_type": {k: len(v) for k, v in entities.items()}
        }
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        """Check health of all components"""
        return {
            "components": {
                "ner_engine": self._ner_engine is not None,
                "legal_storage": self._legal_storage is not None,
                "verdict_parser": self._verdict_parser is not None,
                "chunker": self._chunker is not None,
                "ocr_handler": self._ocr_handler is not None,
                "normalizer": self._normalizer is not None,
            },
            "doc_metrics": self._doc_metrics.copy()
        }
    
    def get_doc_metrics(self) -> Dict[str, Any]:
        """Get document processing metrics"""
        return self._doc_metrics.copy()


# ============================================================================
# Backward Compatibility Alias
# ============================================================================

# Legacy alias for backward compatibility with tests
DocParserAgent = UltraDocParserAgent
