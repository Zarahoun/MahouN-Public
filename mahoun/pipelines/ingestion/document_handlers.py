"""
Document Format Handlers for MAHOUN Ingestion Pipeline
=======================================================

Production-grade document format handlers with fail-closed OCR integrity.
Supports: TXT, DOCX, PDF (with hardened OCR), Images

Design Principles:
- Fail-closed for production (no fallback without integrity guarantees)
- Never crash orchestrator initialization
- Return structured text output with cryptographic proofs
- Maintain Desktop-Minimal compatibility in development

Dependencies (optional):
- python-docx: DOCX support
- pypdf: Basic PDF text extraction
- pdfplumber: Advanced PDF extraction (tables, layout)
- pdf2image + poppler: PDF to image conversion for OCR
- pytesseract + tesseract-ocr: OCR engine (fallback only in dev)
- paddleocr: Base OCR library
- HardenedPaddleOCR: Production OCR with integrity guarantees (REQUIRED in production)

Security & Trust Architecture:
- HardenedPaddleOCR is MANDATORY in production for scanned documents
- Fallback to plain OCR only allowed in development mode
- Merkle tree integrity verification enforced in production
- Checkpoint/resume capability required for large documents
"""

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Optional Chunking Integration
# ============================================================================

try:
    from mahoun.pipelines.ingestion.enhanced_chunker import EnhancedChunker, ChunkingConfig
    _CHUNKER_AVAILABLE = True
    logger.info("✅ EnhancedChunker available for document chunking")
except ImportError:
    _CHUNKER_AVAILABLE = False
    logger.warning("⚠️ EnhancedChunker not available, chunking disabled")

# ============================================================================
# Optional Metadata Extraction Integration
# ============================================================================

try:
    from mahoun.pipelines.ingestion.metadata_extractor import MetadataExtractor
    _METADATA_EXTRACTOR_AVAILABLE = True
    logger.info("✅ MetadataExtractor available for document metadata extraction")
except ImportError:
    _METADATA_EXTRACTOR_AVAILABLE = False
    logger.warning("⚠️ MetadataExtractor not available, metadata extraction disabled")

# ============================================================================
# Optional Monitoring Integration
# ============================================================================

try:
    from mahoun.graph.neo4j.monitoring import Neo4jMetrics
    _MONITORING_AVAILABLE = True
    logger.info("✅ Neo4jMetrics available for monitoring")
except ImportError:
    _MONITORING_AVAILABLE = False
    logger.warning("⚠️ Neo4jMetrics not available, monitoring disabled")

# Global monitoring instance (singleton)
_global_metrics: Optional[Any] = None

def get_global_metrics() -> Optional[Any]:
    """Get or create global metrics instance"""
    global _global_metrics
    if _MONITORING_AVAILABLE and _global_metrics is None:
        _global_metrics = Neo4jMetrics()
    return _global_metrics


# ============================================================================
# Custom Exceptions for OCR Integrity Enforcement
# ============================================================================


class OCRIntegrityError(Exception):
    """
    Raised when OCR integrity guarantees cannot be met.
    
    This is a BLOCKING error in production mode per CONSTITUTION.md Section 10
    (Fail-Closed Principle). The system MUST NOT proceed with OCR processing
    if integrity guarantees (Merkle tree, checkpointing) are unavailable.
    """
    pass


class HardenedOCRUnavailableError(OCRIntegrityError):
    """
    Raised when HardenedPaddleOCR is required but unavailable.
    
    In production, this is a FATAL error. In development, this triggers
    a warning and allows fallback with reduced trust guarantees.
    """
    pass


class OCRMerkleIntegrityError(OCRIntegrityError):
    """
    Raised when Merkle tree integrity proof cannot be generated.
    
    In production, OCR results without Merkle proof are NOT trusted.
    This enforces cryptographic verification of OCR output integrity.
    """
    pass


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class DocumentExtractionResult:
    """
    Result of document text extraction with integrity metadata.
    
    Attributes:
        success: Whether extraction succeeded
        text: Extracted text content
        metadata: Extraction metadata including integrity proofs
        error: Error message if extraction failed
        handler_used: Name of handler that processed the document
        integrity_verified: Whether cryptographic integrity was verified (production requirement)
        chunks: Optional list of text chunks for processing (if chunking enabled)
    """
    success: bool
    text: str
    metadata: Dict[str, Any]
    error: Optional[str] = None
    handler_used: str = "unknown"
    integrity_verified: bool = False  # NEW: Track integrity verification status
    chunks: Optional[List[Any]] = None  # NEW: Optional chunked text


class BaseDocumentHandler:
    """Base class for document handlers"""
    
    def __init__(self):
        self.available = self._check_dependencies()
        if not self.available:
            logger.warning(f"{self.__class__.__name__} dependencies not available")
    
    def _check_dependencies(self) -> bool:
        """Check if required dependencies are available"""
        raise NotImplementedError
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text from document"""
        raise NotImplementedError
    
    def supports_file(self, file_path: str) -> bool:
        """Check if this handler supports the file"""
        raise NotImplementedError


class TxtHandler(BaseDocumentHandler):
    """Plain text file handler (always available)"""
    
    def _check_dependencies(self) -> bool:
        return True  # No dependencies needed
    
    def supports_file(self, file_path: str) -> bool:
        return file_path.lower().endswith(('.txt', '.md'))
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text from TXT file"""
        try:
            # Try multiple encodings
            encodings = ['utf-8', 'utf-8-sig', 'cp1256', 'windows-1256', 'iso-8859-1']
            text: Optional[Any] = None
            used_encoding: Optional[Any] = None
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                # Last resort: read as binary and decode with errors='replace'
                with open(file_path, 'rb') as f:
                    text = f.read().decode('utf-8', errors='replace')
                used_encoding = 'utf-8 (with replacements)'
            
            return DocumentExtractionResult(
                success=True,
                text=text,
                metadata={
                    "format": "txt",
                    "file_path": file_path,
                    "file_size": Path(file_path).stat().st_size,
                    "encoding": used_encoding,
                    "extraction_method": "native"
                },
                handler_used="TxtHandler"
            )
        except Exception as e:
            logger.error(f"Failed to read TXT file {file_path}: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "txt", "file_path": file_path},
                error=str(e),
                handler_used="TxtHandler"
            )


class DocxHandler(BaseDocumentHandler):
    """DOCX file handler using python-docx"""
    
    def _check_dependencies(self) -> bool:
        try:
            import docx
            return True
        except ImportError:
            return False
    
    def supports_file(self, file_path: str) -> bool:
        return file_path.lower().endswith('.docx')
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text from DOCX file with full structure"""
        if not self.available:
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "docx", "file_path": file_path},
                error="python-docx library not available. Install: pip install python-docx",
                handler_used="DocxHandler"
            )
        
        try:
            import docx
            
            doc = docx.Document(file_path)
            
            # Extract paragraphs with style info
            paragraphs: List[Any] = []
            for p in doc.paragraphs:
                if p.text.strip():
                    # Check if heading
                    if p.style and p.style.name.startswith('Heading'):
                        paragraphs.append(f"\n{'#' * int(p.style.name[-1]) if p.style.name[-1].isdigit() else '##'} {p.text}\n")
                    else:
                        paragraphs.append(p.text)
            
            # Extract tables
            table_texts: List[Any] = []
            for table_idx, table in enumerate(doc.tables):
                table_rows: List[Any] = []
                for row in table.rows:
                    row_text = ' | '.join(cell.text.strip() for cell in row.cells)
                    if row_text.strip():
                        table_rows.append(row_text)
                if table_rows:
                    table_texts.append(f"\n=== جدول {table_idx + 1} ===\n" + '\n'.join(table_rows))
            
            # Extract headers and footers
            headers: List[Any] = []
            footers: List[Any] = []
            for section in doc.sections:
                if section.header and section.header.paragraphs:
                    for p in section.header.paragraphs:
                        if p.text.strip():
                            headers.append(p.text.strip())
                if section.footer and section.footer.paragraphs:
                    for p in section.footer.paragraphs:
                        if p.text.strip():
                            footers.append(p.text.strip())
            
            # Combine all text
            all_parts: List[Any] = []
            if headers:
                all_parts.append("=== سربرگ ===\n" + '\n'.join(set(headers)))
            all_parts.append('\n\n'.join(paragraphs))
            if table_texts:
                all_parts.extend(table_texts)
            if footers:
                all_parts.append("\n=== پاورقی ===\n" + '\n'.join(set(footers)))
            
            all_text = '\n\n'.join(all_parts)
            
            return DocumentExtractionResult(
                success=True,
                text=all_text,
                metadata={
                    "format": "docx",
                    "file_path": file_path,
                    "file_size": Path(file_path).stat().st_size,
                    "num_paragraphs": len(paragraphs),
                    "num_tables": len(doc.tables),
                    "has_headers": len(headers) > 0,
                    "has_footers": len(footers) > 0,
                    "extraction_method": "python-docx"
                },
                handler_used="DocxHandler"
            )
            
        except Exception as e:
            logger.error(f"Failed to extract text from DOCX {file_path}: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "docx", "file_path": file_path},
                error=str(e),
                handler_used="DocxHandler"
            )


class PdfHandler(BaseDocumentHandler):
    """
    Advanced PDF handler with multiple extraction strategies:
    1. pdftotext (fast, native, zero character loss)
    2. pypdfium2 (high-performance PDF engine)
    3. pdfplumber (tables and layout)
    4. pypdf (fallback for simple PDFs)
    5. Hardened OCR (for scanned PDFs)
    """
    
    def __init__(self):
        self.pdftotext_available = self._check_pdftotext()
        self.pypdfium2_available = False
        self.pdfplumber_available = False
        self.pypdf_available = False
        self.pdf2image_available = False
        self.ocr_available = False
        
        # Check pypdfium2
        try:
            import pypdfium2
            self.pypdfium2_available = True
        except ImportError:
            pass

        # Check pdfplumber
        try:
            import pdfplumber
            self.pdfplumber_available = True
        except ImportError:
            pass
        
        # Check pypdf
        try:
            import pypdf
            self.pypdf_available = True
        except ImportError:
            pass
        
        # Check pdf2image for OCR
        try:
            from pdf2image import convert_from_path
            self.pdf2image_available = True
        except ImportError:
            pass
        
        super().__init__()

    @property
    def pypdf2_available(self) -> bool:
        """Backward compatibility alias for pypdf_available."""
        return self.pypdf_available

    @staticmethod
    def _check_pdftotext() -> bool:
        import shutil
        return shutil.which("pdftotext") is not None
    
    def _check_dependencies(self) -> bool:
        return (
            self.pdftotext_available
            or self.pypdfium2_available
            or self.pdfplumber_available
            or self.pypdf_available
        )
    
    def supports_file(self, file_path: str) -> bool:
        return file_path.lower().endswith('.pdf')
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text from PDF with multiple strategies"""
        
        # Strategy 1: Try pdftotext (fastest and cleanest for digital Persian PDFs)
        if self.pdftotext_available:
            result = self._extract_with_pdftotext(file_path)
            if result.success and len(result.text.strip()) > 100:
                return result

        # Strategy 2: Try pypdfium2
        if self.pypdfium2_available:
            result = self._extract_with_pypdfium2(file_path)
            if result.success and len(result.text.strip()) > 100:
                return result

        # Strategy 3: Try pdfplumber (best for tables)
        if self.pdfplumber_available:
            result = self._extract_with_pdfplumber(file_path)
            if result.success and len(result.text.strip()) > 100:
                return result
        
        # Strategy 4: Try pypdf
        if self.pypdf_available:
            result = self._extract_with_pypdf(file_path)
            if result.success and len(result.text.strip()) > 100:
                return result
        
        # Strategy 5: OCR fallback for scanned PDFs
        if self.pdf2image_available:
            logger.info(f"Text extraction yielded minimal text, trying OCR for: {file_path}")
            result = self._extract_with_ocr(file_path)
            if result.success:
                return result
        
        # No method worked
        return DocumentExtractionResult(
            success=False,
            text="",
            metadata={"format": "pdf", "file_path": file_path},
            error="Could not extract text from PDF.",
            handler_used="PdfHandler"
        )

    def _extract_with_pdftotext(self, file_path: str) -> DocumentExtractionResult:
        """Extract using pdftotext command-line utility"""
        import subprocess
        try:
            res = subprocess.run(
                ["pdftotext", file_path, "-"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode == 0 and res.stdout.strip():
                return DocumentExtractionResult(
                    success=True,
                    text=res.stdout,
                    metadata={
                        "format": "pdf",
                        "file_path": file_path,
                        "file_size": Path(file_path).stat().st_size,
                        "extraction_method": "pdftotext",
                    },
                    handler_used="PdfHandler (pdftotext)",
                )
        except Exception as e:
            logger.warning(f"pdftotext extraction failed: {e}")
        return DocumentExtractionResult(success=False, text="", metadata={}, error="pdftotext failed", handler_used="PdfHandler")

    def _extract_with_pypdfium2(self, file_path: str) -> DocumentExtractionResult:
        """Extract using pypdfium2"""
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_path)
            pages_text = []
            for i, page in enumerate(pdf):
                textpage = page.get_textpage()
                text = textpage.get_text_range()
                if text.strip():
                    pages_text.append(f"=== صفحه {i + 1} ===\n{text}")
            all_text = "\n\n".join(pages_text)
            return DocumentExtractionResult(
                success=True,
                text=all_text,
                metadata={
                    "format": "pdf",
                    "file_path": file_path,
                    "file_size": Path(file_path).stat().st_size,
                    "num_pages": len(pdf),
                    "extraction_method": "pypdfium2",
                },
                handler_used="PdfHandler (pypdfium2)",
            )
        except Exception as e:
            logger.warning(f"pypdfium2 extraction failed: {e}")
        return DocumentExtractionResult(success=False, text="", metadata={}, error="pypdfium2 failed", handler_used="PdfHandler")
    
    def _extract_with_pdfplumber(self, file_path: str) -> DocumentExtractionResult:
        """Extract using pdfplumber (best for tables)"""
        try:
            import pdfplumber
            
            pages_text: List[Any] = []
            tables_text: List[Any] = []
            with pdfplumber.open(file_path) as pdf:
                num_pages = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    # Extract text
                    text = page.extract_text()
                    if text and text.strip():
                        pages_text.append(f"=== صفحه {page_num + 1} ===\n{text}")
                    
                    # Extract tables
                    tables = page.extract_tables()
                    for table_idx, table in enumerate(tables):
                        if table:
                            table_rows: List[Any] = []
                            for row in table:
                                row_text = ' | '.join(str(cell or '').strip() for cell in row)
                                if row_text.strip():
                                    table_rows.append(row_text)
                            if table_rows:
                                tables_text.append(
                                    f"\n=== جدول صفحه {page_num + 1} ===\n" + 
                                    '\n'.join(table_rows)
                                )
            
            all_text = '\n\n'.join(pages_text)
            if tables_text:
                all_text += '\n\n' + '\n'.join(tables_text)
            
            return DocumentExtractionResult(
                success=True,
                text=all_text,
                metadata={
                    "format": "pdf",
                    "file_path": file_path,
                    "file_size": Path(file_path).stat().st_size,
                    "num_pages": num_pages,
                    "num_tables": len(tables_text),
                    "extraction_method": "pdfplumber"
                },
                handler_used="PdfHandler"
            )
            
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "pdf", "file_path": file_path},
                error=str(e),
                handler_used="PdfHandler"
            )
    
    def _extract_with_pypdf(self, file_path: str) -> DocumentExtractionResult:
        """Extract using pypdf (simple PDFs)"""
        try:
            from pypdf import PdfReader
            
            with open(file_path, 'rb') as f:
                pdf_reader = PdfReader(f)
                num_pages = len(pdf_reader.pages)
                
                pages_text: List[Any] = []
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        pages_text.append(f"=== صفحه {page_num + 1} ===\n{page_text}")
                
                all_text = '\n\n'.join(pages_text)
                
                return DocumentExtractionResult(
                    success=True,
                    text=all_text,
                    metadata={
                        "format": "pdf",
                        "file_path": file_path,
                        "file_size": Path(file_path).stat().st_size,
                        "num_pages": num_pages,
                        "extraction_method": "pypdf"
                    },
                    handler_used="PdfHandler"
                )
                
        except Exception as e:
            logger.warning(f"pypdf extraction failed: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "pdf", "file_path": file_path},
                error=str(e),
                handler_used="PdfHandler"
            )
    
    def _extract_with_ocr(self, file_path: str) -> DocumentExtractionResult:
        """
        Extract text using OCR with FAIL-CLOSED integrity enforcement.
        
        Production Architecture:
        ========================
        1. HardenedPaddleOCR is MANDATORY in production mode
        2. Merkle tree integrity proof is REQUIRED in production
        3. Checkpoint/resume capability is REQUIRED for documents > 100 pages
        4. Fallback to plain OCR is BLOCKED in production mode
        
        Development Architecture:
        =========================
        1. HardenedPaddleOCR is preferred but not mandatory
        2. Fallback to plain PaddleOCR is allowed with WARNING
        3. Fallback to Tesseract is last resort
        
        Security Guarantees:
        ====================
        - Cryptographic integrity via Merkle tree (production)
        - Fault-tolerant processing via checkpointing
        - Persian-legal domain confidence weighting
        - Deterministic output for audit trail

        The delegated hardened implementation calls
        ``hardened_ocr.ocr_image_hardened(...)`` with checkpointing and
        captures ``merkle_root = hardened_ocr.get_document_merkle_root()``.
        
        Raises:
            HardenedOCRUnavailableError: In production, if HardenedPaddleOCR unavailable
            OCRMerkleIntegrityError: In production, if Merkle proof cannot be generated
            OCRIntegrityError: For any other integrity-related failure in production
        """
        try:
            from pdf2image import convert_from_path
            from mahoun.core.environment import is_production

            # PRIORITY 1: resolve and initialize the integrity-preserving OCR
            # before any development-only engine can be considered.
            try:
                from mahoun.pipelines.ingestion.hardened_paddle_ocr import HardenedPaddleOCR
                hardened_ocr = HardenedPaddleOCR(
                    model_dir="/secure/models/paddleocr",
                    checkpoint_dir="/tmp/mahoun_ocr_checkpoints",
                    legal_keyword_threshold=0.85,
                    general_confidence_threshold=0.80,
                )
            except ImportError as e:
                if is_production():
                    raise ImportError(
                        "HardenedPaddleOCR is REQUIRED for production OCR; "
                        "checkpointing and Merkle integrity are mandatory"
                    ) from e
                hardened_ocr = None
                logger.warning("HardenedPaddleOCR unavailable; falling back in development")
            
            # Convert PDF pages to images
            with tempfile.TemporaryDirectory() as temp_dir:
                merkle_root = None
                images = convert_from_path(
                    file_path,
                    dpi=300,
                    output_folder=temp_dir,
                    fmt='png'
                )
                
                logger.info(f"📄 Processing {len(images)} pages for OCR (file: {file_path})")
                
                # ====================================================================
                # STEP 1: Try HardenedPaddleOCR (PRODUCTION REQUIREMENT)
                # ====================================================================
                try:
                    result = self._extract_with_hardened_ocr(
                        file_path=file_path,
                        images=images,
                        temp_dir=temp_dir,
                        hardened_ocr=hardened_ocr
                    )
                    
                    # SUCCESS: HardenedPaddleOCR worked
                    logger.info(f"✅ HardenedPaddleOCR succeeded with Merkle integrity")
                    merkle_root = result.metadata.get("merkle_root")
                    if merkle_root:
                        result.metadata["merkle_root"] = merkle_root
                    return result
                    
                except Exception as hardened_error:
                    # HardenedPaddleOCR failed or unavailable
                    logger.warning(f"⚠️ HardenedPaddleOCR failed: {hardened_error}")
                    
                    # ============================================================
                    # FAIL-CLOSED CHECK: Production must stop here
                    # ============================================================
                    if is_production():
                        error_msg = (
                            f"PRODUCTION FAIL-CLOSED: HardenedPaddleOCR is REQUIRED for OCR. "
                            f"Scanned PDF processing CANNOT proceed without integrity guarantees. "
                            f"File: {file_path}, Pages: {len(images)}, Error: {hardened_error}"
                        )
                        logger.critical(f"🚫 {error_msg}")
                        raise HardenedOCRUnavailableError(error_msg) from hardened_error
                    
                    # Development mode: log warning and try fallback
                    logger.warning(
                        f"🔧 DEVELOPMENT MODE: Attempting fallback to plain OCR "
                        f"(integrity NOT guaranteed, would be BLOCKED in production)"
                    )
                
                # ====================================================================
                # PRIORITY 2: Fallback to plain PaddleOCR (DEVELOPMENT ONLY)
                # ====================================================================
                try:
                    try:
                        from paddleocr import PaddleOCR
                    except ImportError as e:
                        logger.warning("Plain PaddleOCR unavailable: %s", e)
                    result = self._extract_with_plain_paddleocr(
                        file_path=file_path,
                        images=images,
                        temp_dir=temp_dir
                    )
                    
                    # Mark as non-integrity-verified
                    result.integrity_verified = False
                    result.metadata["warning"] = "NO_INTEGRITY_PROOF_DEVELOPMENT_ONLY"
                    
                    logger.warning(f"⚠️ Plain PaddleOCR used (NO integrity verification)")
                    return result
                    
                except (ImportError, Exception) as paddle_error:
                    logger.warning(f"⚠️ Plain PaddleOCR failed: {paddle_error}")
                
                # ====================================================================
                # PRIORITY 3: Fallback to Tesseract (LAST RESORT, DEVELOPMENT ONLY)
                # ====================================================================
                try:
                    try:
                        import pytesseract
                    except ImportError:
                        logger.warning("Tesseract dependency unavailable")
                    result = self._extract_with_tesseract(
                        file_path=file_path,
                        images=images
                    )
                    
                    # Mark as non-integrity-verified
                    result.integrity_verified = False
                    result.metadata["warning"] = "TESSERACT_FALLBACK_NO_INTEGRITY"
                    
                    logger.warning(f"⚠️ Tesseract used (NO integrity verification)")
                    return result
                    
                except Exception as tesseract_error:
                    logger.error(f"❌ All OCR methods failed. Last error: {tesseract_error}")
                    
                    return DocumentExtractionResult(
                        success=False,
                        text="",
                        metadata={"format": "pdf", "file_path": file_path},
                        error=f"All OCR methods failed. Hardened: unavailable, Plain: failed, Tesseract: {tesseract_error}",
                        handler_used="PdfHandler",
                        integrity_verified=False
                    )
                
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "pdf", "file_path": file_path},
                error=f"OCR failed: {e}",
                handler_used="PdfHandler",
                integrity_verified=False
            )
    
    def _extract_with_hardened_ocr(
        self, 
        file_path: str, 
        images: List[Any], 
        temp_dir: str,
        hardened_ocr: Optional[Any] = None,
    ) -> DocumentExtractionResult:
        """
        Extract using HardenedPaddleOCR with full integrity guarantees.
        
        This method provides:
        - Checkpoint/resume for fault tolerance
        - Document-level Merkle tree integrity proof
        - Persian-legal keyword confidence weighting
        - Atomic state persistence
        
        Raises:
            ImportError: If HardenedPaddleOCR module unavailable
            OCRMerkleIntegrityError: If Merkle proof cannot be generated (production only)
            Exception: For any processing error
        """
        from mahoun.pipelines.ingestion.ocr_adapters import get_ocr_container, OCRContainerConfig
        from mahoun.core.environment import is_production
        
        # Generate document ID for checkpointing
        pdf_path = Path(file_path)
        with open(pdf_path, "rb") as f:
            doc_hash = hashlib.sha256(f.read()).hexdigest()[:16]
        document_id = f"ocr_{doc_hash}"
        
        # Get OCR container with ensemble enabled
        ocr_config = OCRContainerConfig(
            enable_ensemble=True,
            ensemble_strategy="weighted",
            min_engines=2,
            enable_post_processor=True,
            enable_pre_processor=True,
            fail_closed=is_production()
        )
        ocr_container = get_ocr_container(ocr_config)
        
        # Ensemble output has no Merkle proof of its own, so it is limited to
        # development mode; production always uses the hardened path below.
        if not is_production() and ocr_container.ocr_ensemble:
            logger.info(f"🔐 Using OCR Ensemble (multi-engine voting) for doc_id: {document_id}")
            
            try:
                ensemble_result = ocr_container.ocr_ensemble.process_images(
                    images=images,
                    document_id=document_id
                )
                
                if ensemble_result and ensemble_result.success:
                    logger.info(
                        f"✓ OCR Ensemble successful: "
                        f"strategy={ensemble_result.voting_strategy}, "
                        f"confidence={ensemble_result.confidence:.2f}, "
                        f"engines={len(ensemble_result.engine_results)}"
                    )
                    
                    # Apply post-processor if available
                    if ocr_container.post_processor:
                        logger.info("Applying OCR post-processor")
                        ensemble_result = ocr_container.post_processor.process(ensemble_result)
                    
                    # Extract text from ensemble result
                    all_text_parts = []
                    for page_num, text in enumerate(ensemble_result.text.split('\n=== صفحه ')):
                        if text.strip():
                            all_text_parts.append(f"=== صفحه {page_num + 1} ===\n{text.strip()}")
                    
                    full_text = "\n".join(all_text_parts)
                    
                    # Return with ensemble metadata
                    return DocumentExtractionResult(
                        success=True,
                        text=full_text,
                        metadata={
                            "method": "ensemble_ocr",
                            "extraction_method": "ocr_ensemble",
                            "voting_strategy": ensemble_result.voting_strategy,
                            "confidence": ensemble_result.confidence,
                            "engines_used": [e.engine_name for e in ensemble_result.engine_results],
                            "disagreements": len(ensemble_result.disagreements),
                            "document_id": document_id,
                            "is_scanned": True,
                            "integrity_verified": False,
                        },
                        handler_used="PdfHandler (ocr_ensemble)",
                        integrity_verified=False,
                    )
                else:
                    logger.warning(f"OCR Ensemble failed: {ensemble_result.error if ensemble_result else 'Unknown error'}")
            except Exception as e:
                logger.warning(f"OCR Ensemble execution failed: {e}, falling back to single-engine OCR")
        
        # Fallback to HardenedPaddleOCR (single-engine, production-grade)
        logger.info(f"🔐 Initializing HardenedPaddleOCR (doc_id: {document_id})")
        
        # Initialize HardenedPaddleOCR
        if hardened_ocr is None:
            raise HardenedOCRUnavailableError(
                "HardenedPaddleOCR was not initialized before the hardened OCR path"
            )
        
        # Process each page with hardened OCR
        all_text_parts = []
        failed_pages = []
        
        for page_num, image in enumerate(images):
            try:
                # Save image temporarily
                img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                image.save(img_path)
                
                # Use ocr_image_hardened method with checkpointing
                page_result = hardened_ocr.ocr_image_hardened(
                    image_path=img_path,
                    document_id=document_id,
                    page_number=page_num,
                    enable_checkpointing=True
                )
                
                if page_result and page_result.get('success') and page_result.get('text'):
                    text = page_result['text']
                    if text and text.strip():
                        all_text_parts.append(f"=== صفحه {page_num + 1} ===\n{text}")
                        logger.debug(f"✓ Page {page_num + 1}/{len(images)} processed")
                    else:
                        failed_pages.append(page_num + 1)
                        logger.warning(f"⚠️ Page {page_num + 1}: empty text")
                else:
                    failed_pages.append(page_num + 1)
                    logger.warning(f"⚠️ Page {page_num + 1}: OCR failed")
                    
            except Exception as page_error:
                failed_pages.append(page_num + 1)
                logger.error(f"❌ Page {page_num + 1} error: {page_error}")
        
        # Check if we got any text
        if not all_text_parts:
            raise RuntimeError(
                f"HardenedPaddleOCR produced NO text for any page. "
                f"Total pages: {len(images)}, Failed pages: {failed_pages}"
            )
        
        # Get Merkle root for integrity proof
        merkle_root = None
        try:
            merkle_root = hardened_ocr.get_document_merkle_root()
            logger.info(f"🔐 Merkle root: {merkle_root[:16]}..." if merkle_root else "No Merkle root")
        except Exception as merkle_error:
            logger.error(f"❌ Merkle root generation failed: {merkle_error}")
            merkle_root = None
        
        # CRITICAL: In production, Merkle proof is REQUIRED
        if is_production() and not merkle_root:
            raise OCRMerkleIntegrityError(
                f"PRODUCTION REQUIREMENT FAILED: Merkle tree integrity proof is MANDATORY. "
                f"OCR results cannot be trusted without cryptographic verification. "
                f"File: {file_path}, Pages processed: {len(all_text_parts)}/{len(images)}"
            )
        
        # Build final result
        all_text = '\n\n'.join(all_text_parts)
        file_size = Path(file_path).stat().st_size
        
        metadata = {
            "format": "pdf",
            "file_path": file_path,
            "file_size": file_size,
            "num_pages": len(images),
            "pages_processed": len(all_text_parts),
            "pages_failed": failed_pages if failed_pages else [],
            "extraction_method": "ocr_hardened_paddleocr",
            "is_scanned": True,
            "checkpoint_enabled": True,
            "document_id": document_id,
        }
        
        # Add Merkle root if available
        if merkle_root:
            metadata["merkle_root"] = merkle_root
            metadata["integrity_verified"] = True
        else:
            metadata["integrity_verified"] = False
        
        return DocumentExtractionResult(
            success=True,
            text=all_text,
            metadata=metadata,
            handler_used="PdfHandler",
            integrity_verified=bool(merkle_root)
        )
    
    def _extract_with_plain_paddleocr(
        self, 
        file_path: str, 
        images: List[Any], 
        temp_dir: str
    ) -> DocumentExtractionResult:
        """
        Fallback extraction using plain PaddleOCR (DEVELOPMENT ONLY).
        
        WARNING: This method provides NO integrity guarantees:
        - No Merkle tree verification
        - No checkpointing support
        - No confidence weighting
        - BLOCKED in production mode
        """
        from paddleocr import PaddleOCR
        
        logger.warning("🔧 Using plain PaddleOCR (NO integrity guarantees)")
        
        paddle_ocr = PaddleOCR(use_angle_cls=True, lang='fa')
        pages_text = []
        
        for page_num, image in enumerate(images):
            img_path = os.path.join(temp_dir, f"page_{page_num}.png")
            image.save(img_path)
            
            result = paddle_ocr.ocr(img_path, cls=True)
            
            if result and result[0]:
                text_parts: List[Any] = []
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                        if text:
                            text_parts.append(text)
                
                if text_parts:
                    pages_text.append(f"=== صفحه {page_num + 1} ===\n" + '\n'.join(text_parts))
        
        all_text = '\n\n'.join(pages_text)
        file_size = Path(file_path).stat().st_size
        
        metadata = {
            "format": "pdf",
            "file_path": file_path,
            "file_size": file_size,
            "num_pages": len(images),
            "extraction_method": "ocr_paddleocr_fallback",
            "is_scanned": True,
            "warning": "NO_INTEGRITY_VERIFICATION",
        }
        
        return DocumentExtractionResult(
            success=len(all_text.strip()) > 0,
            text=all_text,
            metadata=metadata,
            handler_used="PdfHandler",
            integrity_verified=False
        )
    
    def _extract_with_tesseract(
        self, 
        file_path: str, 
        images: List[Any]
    ) -> DocumentExtractionResult:
        """
        Last resort extraction using Tesseract (DEVELOPMENT ONLY).
        
        WARNING: Lowest quality OCR, no integrity guarantees.
        """
        import pytesseract
        
        logger.warning("🔧 Using Tesseract (last resort, NO integrity guarantees)")
        
        pages_text = []
        for page_num, image in enumerate(images):
            # OCR with Persian + English
            text = pytesseract.image_to_string(image, lang='fas+eng')
            if text and text.strip():
                pages_text.append(f"=== صفحه {page_num + 1} ===\n{text}")
        
        all_text = '\n\n'.join(pages_text)
        file_size = Path(file_path).stat().st_size
        
        metadata = {
            "format": "pdf",
            "file_path": file_path,
            "file_size": file_size,
            "num_pages": len(images),
            "extraction_method": "ocr_tesseract_fallback",
            "is_scanned": True,
            "warning": "TESSERACT_NO_INTEGRITY",
        }
        
        return DocumentExtractionResult(
            success=len(all_text.strip()) > 0,
            text=all_text,
            metadata=metadata,
            handler_used="PdfHandler",
            integrity_verified=False
        )


class ImageHandler(BaseDocumentHandler):
    """
    Image handler with OCR support
    Supports: JPG, PNG, BMP, TIFF, GIF
    """
    
    def __init__(self):
        # LAZY INITIALIZATION - No OCR engines initialized here
        self.paddle_available = None  # None means not checked yet
        self.tesseract_available = None  # None means not checked yet
        self.ocr_engine = None
        self.paddle_ocr = None
        
        super().__init__()
    
    def _lazy_init_ocr(self):
        """Lazy initialization of OCR engines - only when needed"""
        # Only check if not already determined
        if self.paddle_available is None and self.tesseract_available is None:
            # Try PaddleOCR first (better for Persian)
            try:
                from paddleocr import PaddleOCR
                self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang='fa')
                self.paddle_available = True
                self.ocr_engine = "paddleocr"
            except ImportError:
                self.paddle_ocr = None
                self.paddle_available = False
            
            # Fallback to Tesseract only if PaddleOCR not available
            if not self.paddle_available:
                try:
                    import pytesseract
                    from PIL import Image
                    self.tesseract_available = True
                    self.ocr_engine = "tesseract"
                except ImportError:
                    self.tesseract_available = False
            
            # Update availability
            self.available = self.paddle_available or self.tesseract_available
    
    def _check_dependencies(self) -> bool:
        # For ImageHandler, we don't want to trigger OCR initialization during dependency check
        # We only check if we can potentially support images (have required base dependencies)
        # Actual OCR engine availability is checked in _lazy_init_ocr when needed
        return True  # ImageHandler can potentially work, actual availability checked lazily
    
    def supports_file(self, file_path: str) -> bool:
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp']
        return any(file_path.lower().endswith(ext) for ext in image_extensions)
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """Extract text from image using OCR"""
        # Lazy initialize OCR engines when actually needed
        self._lazy_init_ocr()
        
        if not self.available:
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "image", "file_path": file_path},
                error="OCR not available. Install: pip install paddleocr or pip install pytesseract",
                handler_used="ImageHandler"
            )
        
        try:
            if self.paddle_available:
                return self._extract_with_paddle(file_path)
            else:
                return self._extract_with_tesseract(file_path)
        except Exception as e:
            logger.error(f"OCR extraction failed for {file_path}: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"format": "image", "file_path": file_path},
                error=str(e),
                handler_used="ImageHandler"
            )
    
    def _extract_with_paddle(self, file_path: str) -> DocumentExtractionResult:
        """Extract text using HardenedPaddleOCR (production) with fallback to plain PaddleOCR (dev)"""
        from mahoun.core.environment import is_production

        # Priority 1: HardenedPaddleOCR with cryptographic integrity guarantees
        try:
            from mahoun.pipelines.ingestion.hardened_paddle_ocr import HardenedPaddleOCR
            if not hasattr(self, "hardened_ocr") or self.hardened_ocr is None:
                self.hardened_ocr = HardenedPaddleOCR(
                    model_dir="/secure/models/paddleocr",
                    checkpoint_dir="/tmp/mahoun_ocr_checkpoints",
                    legal_keyword_threshold=0.85,
                    general_confidence_threshold=0.80,
                )

            import hashlib
            with open(file_path, "rb") as f:
                doc_hash = hashlib.sha256(f.read()).hexdigest()[:16]
            doc_id = f"img_{doc_hash}"

            res = self.hardened_ocr.ocr_image_hardened(
                image_path=file_path,
                document_id=doc_id,
                page_number=0,
                enable_checkpointing=True,
            )
            if res and res.get("success") and res.get("text"):
                text = res["text"]
                merkle_leaf = res.get("merkle_leaf")
                return DocumentExtractionResult(
                    success=len(text.strip()) > 0,
                    text=text,
                    metadata={
                        "format": "image",
                        "file_path": file_path,
                        "file_size": Path(file_path).stat().st_size,
                        "ocr_engine": "hardened_paddleocr",
                        "confidence": res.get("confidence", 0.0),
                        "merkle_leaf": merkle_leaf,
                        "validation_results": res.get("validation_results", {}),
                    },
                    handler_used="ImageHandler (HardenedPaddleOCR)",
                    integrity_verified=True,
                )
        except Exception as e:
            if is_production():
                raise HardenedOCRUnavailableError(
                    f"PRODUCTION FAIL-CLOSED: HardenedPaddleOCR required for image OCR. Error: {e}"
                ) from e
            logger.warning(f"HardenedPaddleOCR unavailable in ImageHandler, falling back to plain PaddleOCR: {e}")

        # Priority 2: Fallback to plain PaddleOCR (development only)
        if self.paddle_ocr is None:
            from paddleocr import PaddleOCR
            self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang='fa')
        
        result = self.paddle_ocr.ocr(file_path, cls=True)
        
        text_parts: List[Any] = []
        confidences: List[Any] = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                    conf = line[1][1] if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 1.0
                    if text:
                        text_parts.append(text)
                        confidences.append(conf)
        
        text = '\n'.join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return DocumentExtractionResult(
            success=len(text.strip()) > 0,
            text=text,
            metadata={
                "format": "image",
                "file_path": file_path,
                "file_size": Path(file_path).stat().st_size,
                "ocr_engine": "paddleocr",
                "lines_extracted": len(text_parts),
                "avg_confidence": round(avg_confidence, 3),
                "warning": "NO_INTEGRITY_PROOF_DEVELOPMENT_ONLY",
            },
            handler_used="ImageHandler",
            integrity_verified=False,
        )
    
    def _extract_with_tesseract(self, file_path: str) -> DocumentExtractionResult:
        """Extract text using Tesseract"""
        import pytesseract
        from PIL import Image
        
        image = Image.open(file_path)
        
        # Get image info
        width, height = image.size
        
        # Extract text (Persian + English)
        text = pytesseract.image_to_string(image, lang='fas+eng')
        
        # Get confidence data
        data = pytesseract.image_to_data(image, lang='fas+eng', output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in data['conf'] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0
        
        return DocumentExtractionResult(
            success=len(text.strip()) > 0,
            text=text,
            metadata={
                "format": "image",
                "file_path": file_path,
                "file_size": Path(file_path).stat().st_size,
                "ocr_engine": "tesseract",
                "image_size": (width, height),
                "avg_confidence": round(avg_confidence, 3)
            },
            handler_used="ImageHandler"
        )


class DocumentHandlerFactory:
    """
    Factory for selecting appropriate document handler.
    
    Implements graceful fallback strategy:
    1. Try format-specific handler (DOCX/PDF/Image)
    2. Fall back to TXT handler if dependencies missing
    3. Never crash - always return a result
    """
    
    def __init__(self):
        """Initialize handlers lazily - only TxtHandler and DocxHandler instantiated here"""
        # Always instantiate TxtHandler (no dependencies)
        self.txt_handler = TxtHandler()
        
        # Instantiate DocxHandler (dependency check happens in constructor)
        self.docx_handler = DocxHandler()
        
        # Instantiate PdfHandler (dependency check happens in constructor)
        self.pdf_handler = PdfHandler()
        
        # Don't instantiate ImageHandler eagerly - only when needed
        self.image_handler = None
        
        # Keep list of handlers for iteration
        self.handlers = [self.txt_handler, self.docx_handler, self.pdf_handler]
        
        # Log availability
        available = [h.__class__.__name__ for h in self.handlers if h.available]
        unavailable = [h.__class__.__name__ for h in self.handlers if not h.available]
        
        logger.info(f"Document handlers available: {available}")
        if unavailable:
            logger.warning(f"Document handlers unavailable: {unavailable}")
    
    def _get_image_handler(self):
        """Lazy initialization of ImageHandler"""
        if self.image_handler is None:
            self.image_handler = ImageHandler()
        return self.image_handler
    
    def get_handler(self, file_path: str) -> Optional[BaseDocumentHandler]:
        """Get appropriate handler for file"""
        # Check non-image handlers first
        for handler in self.handlers:
            if handler.supports_file(file_path) and handler.available:
                return handler
        
        # Only instantiate ImageHandler if file is an image
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp']
        if any(file_path.lower().endswith(ext) for ext in image_extensions):
            image_handler = self._get_image_handler()
            if image_handler.supports_file(file_path) and image_handler.available:
                return image_handler
                
        return None
    
    def extract_text(self, file_path: str) -> DocumentExtractionResult:
        """
        Extract text from document with graceful fallback.
        
        Args:
            file_path: Path to document file
            
        Returns:
            DocumentExtractionResult with extracted text
        """
        if not Path(file_path).exists():
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"file_path": file_path},
                error=f"File not found: {file_path}",
                handler_used="DocumentHandlerFactory"
            )
        
        # Try to get specific handler
        handler = self.get_handler(file_path)
        
        if handler:
            logger.debug(f"Using {handler.__class__.__name__} for {file_path}")
            return handler.extract_text(file_path)
        
        # Graceful fallback: try TXT handler
        logger.warning(
            f"No specific handler available for {file_path}, "
            f"attempting TXT fallback"
        )
        txt_handler = TxtHandler()
        result = txt_handler.extract_text(file_path)
        result.metadata["fallback_used"] = True
        return result


# ============================================================================
# Convenience Functions
# ============================================================================

def chunk_document_text(
    text: str,
    doc_id: str,
    enable_chunking: bool = True,
    chunk_size: int = 512,
    overlap: int = 50,
    allow_failure: bool = False
) -> Optional[List[Any]]:
    """
    Chunk document text using EnhancedChunker if available.
    
    Args:
        text: Document text to chunk
        doc_id: Document ID for chunk identification
        enable_chunking: Whether to enable chunking
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks in characters
        allow_failure: If True, return None on failure (silent failure). 
                      If False (default), raise exception on failure (loud failure).
        
    Returns:
        List of Chunk objects if chunking enabled and available, None if disabled or allow_failure=True
        
    Raises:
        RuntimeError: If chunking fails and allow_failure=False
    """
    if not enable_chunking or not _CHUNKER_AVAILABLE:
        return None
    
    try:
        config = ChunkingConfig(
            chunk_size=chunk_size,
            overlap=overlap,
            dynamic_size=True,
            preserve_sentences=True,
            preserve_paragraphs=True
        )
        chunker = EnhancedChunker(config=config)
        chunks = chunker.chunk_document(text, doc_id)
        logger.info(f"✅ Document {doc_id} chunked into {len(chunks)} chunks")
        return chunks
    except Exception as e:
        logger.error(f"❌ Chunking failed for document {doc_id}: {e}")
        if allow_failure:
            # Silent failure mode - return None
            return None
        else:
            # Loud failure mode - raise exception
            raise RuntimeError(f"Chunking failed for document {doc_id}: {e}") from e


def extract_document_metadata(
    text: str,
    doc_type: str = "general",
    enable_metadata_extraction: bool = True,
    allow_failure: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Extract document metadata using MetadataExtractor if available.
    
    Args:
        text: Document text to extract metadata from
        doc_type: Document type (contract, letter, report, verdict, law, etc.)
        enable_metadata_extraction: Whether to enable metadata extraction
        allow_failure: If True, return None on failure (silent failure).
                      If False (default), raise exception on failure (loud failure).
        
    Returns:
        Dictionary of extracted metadata if enabled and available, None if disabled or allow_failure=True
        
    Raises:
        RuntimeError: If metadata extraction fails and allow_failure=False
    """
    if not enable_metadata_extraction or not _METADATA_EXTRACTOR_AVAILABLE:
        return None
    
    try:
        extractor = MetadataExtractor()
        # Note: MetadataExtractor.extract is async, but we'll call it synchronously
        # For simplicity, we'll use a simple wrapper
        import asyncio
        
        def run_async_extract():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(extractor.extract(text, doc_type))
            finally:
                loop.close()
        
        metadata = run_async_extract()
        logger.info(f"✅ Metadata extracted for document type: {doc_type}")
        return metadata
    except Exception as e:
        logger.error(f"❌ Metadata extraction failed: {e}")
        if allow_failure:
            # Silent failure mode - return None
            return None
        else:
            # Loud failure mode - raise exception
            raise RuntimeError(f"Metadata extraction failed: {e}") from e


def extract_document_text(
    file_path: str,
    enable_chunking: bool = False,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    enable_metadata_extraction: bool = False,
    doc_type: str = "general",
    enable_monitoring: bool = True,
    allow_chunking_failure: bool = False,
    allow_metadata_failure: bool = False
) -> DocumentExtractionResult:
    """
    Convenience function to extract text from any supported document format.
    
    Supported formats:
    - TXT, MD: Plain text
    - DOCX: Microsoft Word (requires python-docx)
    - PDF: Portable Document Format (requires pdfplumber or pypdf)
    - Images (JPG, PNG, etc.): OCR (requires paddleocr or pytesseract)
    
    Args:
        file_path: Path to document file
        enable_chunking: Whether to chunk the extracted text
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        enable_metadata_extraction: Whether to extract document metadata
        doc_type: Document type for metadata extraction (contract, letter, report, verdict, law, etc.)
        enable_monitoring: Whether to enable performance monitoring
        allow_chunking_failure: If True, chunking failures are silent (return None). 
                                 If False (default), chunking failures raise exceptions (loud failure).
        allow_metadata_failure: If True, metadata extraction failures are silent (return None).
                                   If False (default), metadata extraction failures raise exceptions (loud failure).
        
    Returns:
        DocumentExtractionResult with extracted text and metadata
        
    Raises:
        RuntimeError: If chunking or metadata extraction fails and corresponding allow_*_failure=False
        
    Example:
        >>> result = extract_document_text("verdict.pdf", enable_chunking=True, enable_metadata_extraction=True)
        >>> if result.success:
        ...     print(result.text)
        ...     print(f"Used: {result.handler_used}")
        ...     print(f"Method: {result.metadata.get('extraction_method')}")
        ...     if result.chunks:
        ...         print(f"Chunks: {len(result.chunks)}")
        ...     if result.metadata.get("metadata_extracted"):
        ...         print(f"Document number: {result.metadata.get('document_number')}")
    """
    import time
    
    # Start monitoring if enabled
    metrics = get_global_metrics() if enable_monitoring else None
    start_time = time.time() if metrics else None
    
    try:
        factory = DocumentHandlerFactory()
        result = factory.extract_text(file_path)
        
        # Record extraction time
        if metrics and start_time:
            extraction_time = time.time() - start_time
            metrics.record_query(extraction_time)
            result.metadata["extraction_time_ms"] = extraction_time * 1000
        
        # Add chunking if enabled and extraction succeeded
        if enable_chunking and result.success and result.text:
            chunk_start = time.time() if metrics else None
            doc_id = Path(file_path).stem
            chunks = chunk_document_text(
                result.text,
                doc_id,
                enable_chunking=True,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
                allow_failure=allow_chunking_failure
            )
            result.chunks = chunks
            # Only set chunking metadata if chunking actually succeeded (chunks generated and not None)
            if chunks is not None and len(chunks) > 0:
                result.metadata["chunking_enabled"] = True
                result.metadata["chunk_count"] = len(chunks)
                result.metadata["chunk_size"] = chunk_size
                result.metadata["chunk_overlap"] = chunk_overlap
                
                # Record chunking time
                if metrics and chunk_start:
                    chunking_time = time.time() - chunk_start
                    result.metadata["chunking_time_ms"] = chunking_time * 1000
        
        # Add metadata extraction if enabled and extraction succeeded
        if enable_metadata_extraction and result.success and result.text:
            metadata_start = time.time() if metrics else None
            extracted_metadata = extract_document_metadata(
                result.text,
                doc_type=doc_type,
                enable_metadata_extraction=True,
                allow_failure=allow_metadata_failure
            )
            if extracted_metadata:
                result.metadata.update(extracted_metadata)
                result.metadata["metadata_extracted"] = True
                result.metadata["metadata_doc_type"] = doc_type
            
            # Record metadata extraction time
            if metrics and metadata_start:
                metadata_time = time.time() - metadata_start
                result.metadata["metadata_extraction_time_ms"] = metadata_time * 1000
        
        return result
        
    except Exception as e:
        # Record error if monitoring enabled
        if metrics:
            metrics.record_error()
        raise


def check_handler_availability() -> Dict[str, Dict[str, Any]]:
    """
    Check which document handlers are available and their capabilities.
    
    Returns:
        Dictionary mapping handler name to availability and details
        
    Example:
        >>> availability = check_handler_availability()
        >>> print(f"PDF support: {availability['PdfHandler']['available']}")
        >>> print(f"PDF methods: {availability['PdfHandler']['methods']}")
    """
    result: Dict[str, Any] = {}
    # TXT Handler
    result['TxtHandler'] = {
        'available': True,
        'formats': ['.txt', '.md'],
        'methods': ['native']
    }
    
    # DOCX Handler
    try:
        import docx
        result['DocxHandler'] = {
            'available': True,
            'formats': ['.docx'],
            'methods': ['python-docx']
        }
    except ImportError:
        result['DocxHandler'] = {
            'available': False,
            'formats': ['.docx'],
            'install': 'pip install python-docx'
        }
    
    # PDF Handler
    pdf_methods: List[Any] = []
    try:
        import pdfplumber
        pdf_methods.append('pdfplumber')
    except ImportError:
        pass
    try:
        import pypdfium2
        pdf_methods.append('pypdfium2')
    except ImportError:
        pass
    try:
        import pypdf
        pdf_methods.append('pypdf')
    except ImportError:
        pass
    import shutil
    if shutil.which("pdftotext"):
        pdf_methods.append('pdftotext')
    try:
        from pdf2image import convert_from_path
        pdf_methods.append('pdf2image')
    except ImportError:
        pass
    
    result['PdfHandler'] = {
        'available': len(pdf_methods) > 0,
        'formats': ['.pdf'],
        'methods': pdf_methods if pdf_methods else None,
        'install': 'pip install pdfplumber pypdfium2 pypdf pdf2image' if not pdf_methods else None
    }
    
    # Image/OCR Handler
    ocr_methods: List[Any] = []
    try:
        from paddleocr import PaddleOCR
        ocr_methods.append('paddleocr')
    except ImportError:
        pass
    try:
        import pytesseract
        ocr_methods.append('tesseract')
    except ImportError:
        pass
    
    result['ImageHandler'] = {
        'available': len(ocr_methods) > 0,
        'formats': ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif'],
        'methods': ocr_methods if ocr_methods else None,
        'install': 'pip install paddleocr or pip install pytesseract' if not ocr_methods else None
    }
    
    return result
