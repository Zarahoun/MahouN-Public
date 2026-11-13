"""
Document Normalizer for MAHOUN
===============================

تبدیل تمام ورودی‌ها به JSON استاندارد
از کامپوننت‌های موجود استفاده می‌کند:
- Document Handlers برای parsing
- IngestionPipeline برای processing
- Metadata Extractor برای استخراج metadata
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from mahoun.core.uid_generator import generate_document_id

from .document_handlers import (
    TxtHandler,
    DocxHandler,
    PdfHandler,
    DocumentExtractionResult,
)
from .ocr_handler import OCRHandler

logger = logging.getLogger(__name__)


@dataclass
class NormalizedDocument:
    """ساختار JSON استاندارد برای همه مدارک"""

    document_id: str
    type: str  # contract, letter, report, general_conditions, etc.
    metadata: Dict[str, Any]
    content: Dict[str, Any]
    attachments: List[Dict[str, Any]]
    processing_info: Dict[str, Any]


class DocumentNormalizer:
    """
    Document Normalizer - تبدیل تمام ورودی‌ها به JSON استاندارد

    این کلاس از کامپوننت‌های موجود استفاده می‌کند:
    - Document Handlers برای extract کردن text
    - Metadata Extractor برای استخراج metadata
    - IngestionPipeline برای processing (optional)

    Usage:
        normalizer = DocumentNormalizer()
        result = await normalizer.normalize_file("contract.pdf")
        # یا
        result = await normalizer.normalize_text(text, metadata)
    """

    def __init__(self):
        """Initialize Document Normalizer"""
        # Initialize document handlers
        self.txt_handler = TxtHandler()
        self.docx_handler = DocxHandler()
        self.pdf_handler = PdfHandler()
        self.ocr_handler = OCRHandler()  # For images

        # Metadata extractor (will be initialized when needed)
        self.metadata_extractor = None

        logger.info("DocumentNormalizer initialized")

    async def normalize_file(
        self,
        file_path: str,
        doc_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizedDocument:
        """
        Normalize a file to JSON standard format

        Args:
            file_path: مسیر فایل
            doc_type: نوع سند (contract, letter, report, etc.) - اگر None باشد، auto-detect می‌کند
            metadata: metadata اضافی

        Returns:
            NormalizedDocument با ساختار JSON استاندارد
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Step 1: Extract text using existing handlers
        extraction_result = self._extract_text(file_path)

        if not extraction_result.success:
            raise ValueError(f"Failed to extract text: {extraction_result.error}")

        # Step 2: Detect document type if not provided
        if not doc_type:
            doc_type = self._detect_document_type(file_path, extraction_result.text)

        # Step 3: Extract metadata
        extracted_metadata = await self._extract_metadata(
            text=extraction_result.text,
            doc_type=doc_type,
            file_path=file_path,
            existing_metadata=metadata or {},
        )

        # Step 4: Build normalized document
        content_hash = hashlib.sha256(
            extraction_result.text.encode("utf-8")
        ).hexdigest()
        document_id = generate_document_id(content_hash)

        normalized = NormalizedDocument(
            document_id=document_id,
            type=doc_type,
            metadata={
                **extracted_metadata,
                "file_path": str(file_path),
                "file_name": file_path_obj.name,
                "file_size": file_path_obj.stat().st_size,
                "handler_used": extraction_result.handler_used,
                **(metadata or {}),
            },
            content={
                "text": extraction_result.text,
                "raw_text": extraction_result.text,  # Keep original
                "normalized_text": self._normalize_text(extraction_result.text),
                "sections": self._extract_sections(extraction_result.text, doc_type),
            },
            attachments=[],
            processing_info={
                "normalized_at": datetime.now(timezone.utc).isoformat(),
                "handler": extraction_result.handler_used,
                "extraction_success": extraction_result.success,
            },
        )

        logger.info(f"Normalized document: {document_id} (type: {doc_type})")
        return normalized

    async def normalize_text(
        self, text: str, doc_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> NormalizedDocument:
        """
        Normalize text to JSON standard format

        Args:
            text: متن سند
            doc_type: نوع سند
            metadata: metadata اضافی

        Returns:
            NormalizedDocument
        """
        # Extract metadata
        extracted_metadata = await self._extract_metadata(
            text=text, doc_type=doc_type, existing_metadata=metadata or {}
        )

        # Build normalized document
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document_id = generate_document_id(content_hash)

        normalized = NormalizedDocument(
            document_id=document_id,
            type=doc_type,
            metadata={**extracted_metadata, **(metadata or {})},
            content={
                "text": text,
                "raw_text": text,
                "normalized_text": self._normalize_text(text),
                "sections": self._extract_sections(text, doc_type),
            },
            attachments=[],
            processing_info={
                "normalized_at": datetime.now(timezone.utc).isoformat(),
                "handler": "text_input",
            },
        )

        logger.info(f"Normalized text document: {document_id} (type: {doc_type})")
        return normalized

    def _extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text using existing handlers"""
        # Try handlers in order: PDF, DOCX, TXT, then OCR for images
        handlers = [
            self.pdf_handler,
            self.docx_handler,
            self.txt_handler,
            self.ocr_handler,  # For images
        ]

        for handler in handlers:
            if handler.available and handler.supports_file(file_path):
                try:
                    return handler.extract_text(file_path)
                except Exception as e:
                    logger.warning(f"Handler {handler.__class__.__name__} failed: {e}")
                    continue

        # If no handler worked, return error
        return DocumentExtractionResult(
            success=False,
            text="",
            metadata={"file_path": file_path},
            error="No suitable handler found for this file type",
            handler_used="none",
        )

    def _detect_document_type(self, file_path: str, text: str) -> str:
        """
        Auto-detect document type based on file path and content

        Returns:
            نوع سند: contract, letter, report, general_conditions, etc.
        """
        file_path_lower = file_path.lower()
        text_lower = text[:500].lower()  # First 500 chars

        # Check file name patterns
        if "قرارداد" in file_path_lower or "contract" in file_path_lower:
            return "contract"
        if "نامه" in file_path_lower or "letter" in file_path_lower:
            return "letter"
        if "گزارش" in file_path_lower or "report" in file_path_lower:
            return "report"
        if "شرایط" in file_path_lower or "conditions" in file_path_lower:
            return "general_conditions"

        # Check content patterns
        if "قرارداد" in text_lower or "متعاهد" in text_lower:
            return "contract"
        if "بسمه تعالی" in text_lower or "محترم" in text_lower:
            return "letter"
        if "گزارش" in text_lower or "خلاصه" in text_lower:
            return "report"

        # Default
        return "document"

    async def _extract_metadata(
        self,
        text: str,
        doc_type: str,
        file_path: Optional[str] = None,
        existing_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extract metadata from document

        از Metadata Extractor استفاده می‌کند (اگر موجود باشد)
        """
        metadata = existing_metadata.copy() if existing_metadata else {}

        # Initialize metadata extractor if needed
        if self.metadata_extractor is None:
            try:
                from .metadata_extractor import MetadataExtractor

                self.metadata_extractor = MetadataExtractor()
            except ImportError:
                logger.warning(
                    "MetadataExtractor not available, using basic extraction"
                )
                self.metadata_extractor = None

        # Extract metadata using extractor
        if self.metadata_extractor:
            try:
                extracted = await self.metadata_extractor.extract(text, doc_type)
                metadata.update(extracted)
            except Exception as e:
                logger.warning(f"Metadata extraction failed: {e}")

        # Basic extraction (fallback)
        if not metadata.get("date"):
            metadata["date"] = self._extract_date(text)

        if not metadata.get("subject"):
            metadata["subject"] = self._extract_subject(text)

        return metadata

    def _extract_date(self, text: str) -> Optional[str]:
        """Extract date from text (basic pattern matching)"""
        import re

        # Persian date patterns
        patterns = [
            r"(\d{4})/(\d{1,2})/(\d{1,2})",  # 1403/01/15
            r"(\d{1,2})/(\d{1,2})/(\d{4})",  # 15/01/1403
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:500])
            if match:
                return match.group(0)

        return None

    def _extract_subject(self, text: str) -> Optional[str]:
        """Extract subject from text (first line or after keywords)"""
        lines = text.split("\n")[:10]  # First 10 lines

        # Look for subject keywords
        keywords = ["موضوع:", "عنوان:", "Subject:", "Title:"]

        for i, line in enumerate(lines):
            for keyword in keywords:
                if keyword in line:
                    subject = line.split(keyword, 1)[1].strip()
                    if subject:
                        return subject[:200]  # First 200 chars

        # Return first non-empty line
        for line in lines:
            if line.strip() and len(line.strip()) > 10:
                return line.strip()[:200]

        return None

    def _normalize_text(self, text: str) -> str:
        """Normalize text (using existing normalizer if available)"""
        try:
            from .persian_normalizer import PersianLegalNormalizer

            normalizer = PersianLegalNormalizer()
            return normalizer.normalize_legal_text(text)
        except ImportError:
            # Basic normalization
            return text.strip()

    def _extract_sections(self, text: str, doc_type: str) -> Dict[str, str]:
        """
        Extract sections from document based on type

        Returns:
            Dictionary of section_name -> section_text
        """
        sections: Dict[str, Any] = {}
        # Basic section extraction (can be enhanced)
        if doc_type == "contract":
            # Look for common contract sections
            section_keywords = {
                "parties": ["طرفین", "متعاهدین"],
                "subject": ["موضوع قرارداد"],
                "obligations": ["تعهدات", "وظایف"],
                "payment": ["پرداخت", "مبلغ"],
                "duration": ["مدت", "زمان"],
            }

            for section_name, keywords in section_keywords.items():
                for keyword in keywords:
                    if keyword in text:
                        # Extract section (simplified)
                        sections[section_name] = f"Section containing: {keyword}"
                        break

        return sections

    def to_dict(self, normalized: NormalizedDocument) -> Dict[str, Any]:
        """Convert NormalizedDocument to dictionary (JSON-serializable)"""
        return {
            "document_id": normalized.document_id,
            "type": normalized.type,
            "metadata": normalized.metadata,
            "content": normalized.content,
            "attachments": normalized.attachments,
            "processing_info": normalized.processing_info,
        }


# ============================================================================
# Helper Functions
# ============================================================================


async def normalize_document_file(file_path: str, **kwargs) -> Dict[str, Any]:
    """
    Helper function to normalize a document file

    Returns:
        Dictionary representation of normalized document
    """
    normalizer = DocumentNormalizer()
    normalized = await normalizer.normalize_file(file_path, **kwargs)
    return normalizer.to_dict(normalized)


async def normalize_document_text(text: str, doc_type: str, **kwargs) -> Dict[str, Any]:
    """
    Helper function to normalize document text

    Returns:
        Dictionary representation of normalized document
    """
    normalizer = DocumentNormalizer()
    normalized = await normalizer.normalize_text(text, doc_type, **kwargs)
    return normalizer.to_dict(normalized)
