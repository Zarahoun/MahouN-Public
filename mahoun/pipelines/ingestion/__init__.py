"""
Ingestion Pipeline Module
=========================
Document ingestion and indexing pipeline.

Features:
- Document Normalization (Persian)
- Verdict Parsing
- Entity Extraction (NER)
- Vector Storage (Chroma)
- Legal Schema Storage (PostgreSQL)
"""
from typing import Any, Optional

# Primary Pipeline (Unified - selects best available)
from .pipeline import IngestionPipeline, IngestionResultV2
IngestionResult = IngestionResultV2

# Core Components
from .minimal_verdict_parser import parse_verdict_file, parse_verdict_text, MinimalVerdictParser
from .document_normalizer import DocumentNormalizer, normalize_document_file, normalize_document_text
from .metadata_extractor import MetadataExtractor

# Enterprise NER Subsystem
try:
    from .legal_ner import extract_entities, LegalNEREngine
except ImportError:
    extract_entities: Optional[Any] = None
    LegalNEREngine: Optional[Any] = None

# Legal Storage Service
try:
    from .legal_storage import (
        LegalStorageService,
        StorageResult,
        store_verdict_to_legal_schema,
        get_legal_storage
    )
except ImportError:
    LegalStorageService: Optional[Any] = None
    StorageResult: Optional[Any] = None
    store_verdict_to_legal_schema: Optional[Any] = None
    get_legal_storage: Optional[Any] = None

# Enhanced Components (Lazy Import)
try:
    from .enhanced_pipeline import EnhancedIngestionPipeline
    from .llm_refiner import LLMRefinementService
    HAS_ENHANCED = True
except ImportError:
    EnhancedIngestionPipeline: Optional[Any] = None
    LLMRefinementService: Optional[Any] = None
    HAS_ENHANCED = False

__all__ = [
    # Primary
    "IngestionPipeline",
    "IngestionResult",
    
    # Core Components
    "DocumentNormalizer",
    "MinimalVerdictParser",
    "MetadataExtractor",
    "extract_entities",
    "LegalNEREngine",
    
    # Utilities
    "normalize_document_text",
    "parse_verdict_text",
    
    # Enhanced Components (when available)
    "EnhancedIngestionPipeline",
    "LLMRefinementService",
]
