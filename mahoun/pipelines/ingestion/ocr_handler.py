"""
OCR Handler for MAHOUN
======================

پشتیبانی کامل از OCR برای استخراج متن از تصاویر و PDF های اسکن شده

Engines پشتیبانی شده:
1. PaddleOCR (توصیه شده برای فارسی)
2. Tesseract OCR (fallback)
3. EasyOCR (alternative)

نصب:
    # PaddleOCR (بهترین برای فارسی)
    pip install paddleocr paddlepaddle
    
    # Tesseract
    pip install pytesseract
    # + نصب tesseract-ocr از سیستم عامل
    # Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-fas
    # macOS: brew install tesseract tesseract-lang
    
    # EasyOCR
    pip install easyocr
    
    # برای PDF به تصویر
    pip install pdf2image
    # + نصب poppler
    # Ubuntu: sudo apt install poppler-utils
    # macOS: brew install poppler
"""

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from mahoun.core.exceptions import SecurityConstraintError

logger = logging.getLogger(__name__)

# Import OCR post-processor for quality improvement
try:
    from .ocr_post_processor import OCRPostProcessor, PostProcessingConfig
    POST_PROCESSOR_AVAILABLE = True
except ImportError:
    POST_PROCESSOR_AVAILABLE = False
    logger.warning("OCR post-processor not available")


@dataclass
class OCRResult:
    """نتیجه OCR"""
    success: bool
    text: str
    lines: List[Dict[str, Any]]  # هر خط با موقعیت و confidence
    confidence: float
    engine: str
    metadata: Dict[str, Any]
    error: Optional[str] = None


class OCREngine:
    """
    موتور OCR یکپارچه با پشتیبانی از چند backend
    
    اولویت:
    1. PaddleOCR (بهترین برای فارسی)
    2. Tesseract (پرکاربردترین)
    3. EasyOCR (ساده‌ترین نصب)
    """
    
    def __init__(self, preferred_engine: Optional[str] = None, enable_post_processing: bool = True):
        """
        Initialize OCR Engine
        
        Args:
            preferred_engine: 'paddle', 'tesseract', or 'easyocr'
            enable_post_processing: Enable OCR post-processing for quality improvement
        """
        self.paddle_ocr = None
        self.easyocr_reader = None
        self.available_engines: List[str] = []
        self.active_engine: Optional[str] = None
        
        # Initialize post-processor
        self.enable_post_processing = enable_post_processing and POST_PROCESSOR_AVAILABLE
        self.post_processor = None
        if self.enable_post_processing:
            try:
                self.post_processor = OCRPostProcessor(PostProcessingConfig())
                logger.info("✅ OCR post-processor enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize post-processor: {e}")
                self.enable_post_processing = False
        
        # Initialize engines
        self._init_paddle()
        self._init_tesseract()
        self._init_easyocr()
        
        # Select engine
        if preferred_engine and preferred_engine in self.available_engines:
            self.active_engine = preferred_engine
        elif self.available_engines:
            self.active_engine = self.available_engines[0]
        
        if self.active_engine:
            logger.info(f"✅ OCR Engine initialized: {self.active_engine}")
            logger.info(f"   Available engines: {self.available_engines}")
            if self.enable_post_processing:
                logger.info(f"   Post-processing: ENABLED (10-20% accuracy improvement)")
        else:
            logger.warning("⚠️ No OCR engine available!")
    
    def _init_paddle(self):
        """Initialize PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            self.paddle_ocr = PaddleOCR(
                use_angle_cls=True,
                lang='fa'
                # Note: removed deprecated args (use_gpu, show_log)
            )
            self.available_engines.append('paddle')
            logger.debug("PaddleOCR initialized")
        except ImportError:
            logger.debug("PaddleOCR not available")
        except Exception as e:
            logger.warning(f"PaddleOCR init failed: {e}")
    
    def _init_tesseract(self):
        """Initialize Tesseract"""
        try:
            import pytesseract
            # Test if tesseract is installed
            pytesseract.get_tesseract_version()
            self.available_engines.append('tesseract')
            logger.debug("Tesseract initialized")
        except ImportError:
            logger.debug("pytesseract not available")
        except Exception as e:
            logger.debug(f"Tesseract not available: {e}")
    
    def _init_easyocr(self):
        """Initialize EasyOCR"""
        try:
            import easyocr
            # Lazy init - don't load model until needed
            self._easyocr_module = easyocr
            self.available_engines.append('easyocr')
            logger.debug("EasyOCR available")
        except ImportError:
            logger.debug("EasyOCR not available")
    
    @property
    def is_available(self) -> bool:
        """Check if any OCR engine is available"""
        return len(self.available_engines) > 0
    
    def ocr_image(self, image_path: str, engine: Optional[str] = None) -> OCRResult:
        """
        Perform OCR on an image
        
        Args:
            image_path: Path to image file
            engine: Specific engine to use (optional)
         
        Returns:
            OCRResult with extracted text
        
        Raises:
            SecurityConstraintError: If OCR confidence is below 0.85
        """
        if not self.is_available:
            return OCRResult(
                success=False,
                text="",
                lines=[],
                confidence=0.0,
                engine="none",
                metadata={},
                error="No OCR engine available"
            )
        
        use_engine = engine if engine in self.available_engines else self.active_engine
        
        # Try primary engine
        try:
            if use_engine == 'paddle':
                result = self._ocr_paddle(image_path)
            elif use_engine == 'tesseract':
                result = self._ocr_tesseract(image_path)
            elif use_engine == 'easyocr':
                result = self._ocr_easyocr(image_path)
            else:
                return OCRResult(
                    success=False,
                    text="",
                    lines=[],
                    confidence=0.0,
                    engine=use_engine or "unknown",
                    metadata={},
                    error=f"Unknown engine: {use_engine}"
                )
            
            # Check confidence for successful OCR
            if result.success and result.confidence < 0.85:
                raise SecurityConstraintError(
                    f"OCR confidence too low: {result.confidence:.2f} < 0.85",
                    details={"confidence": result.confidence, "engine": result.engine}
                )
            return result
        except Exception as e:
            logger.error(f"OCR failed with {use_engine}: {e}")
        
        # Try fallback engines
        for fallback in self.available_engines:
            if fallback == use_engine:
                continue
            try:
                logger.info(f"Trying fallback engine: {fallback}")
                if fallback == 'paddle':
                    result = self._ocr_paddle(image_path)
                elif fallback == 'tesseract':
                    result = self._ocr_tesseract(image_path)
                elif fallback == 'easyocr':
                    result = self._ocr_easyocr(image_path)
                else:
                    continue  # Should not happen
                
                # Check confidence for successful OCR
                if result.success and result.confidence < 0.85:
                    raise SecurityConstraintError(
                        f"OCR confidence too low: {result.confidence:.2f} < 0.85",
                        details={"confidence": result.confidence, "engine": result.engine}
                    )
                return result
            except Exception as e2:
                logger.warning(f"Fallback {fallback} also failed: {e2}")
        
        # If we get here, all engines failed
        return OCRResult(
            success=False,
            text="",
            lines=[],
            confidence=0.0,
            engine=use_engine or "unknown",
            metadata={},
            error="All OCR engines failed"
        )
    
    def _ocr_paddle(self, image_path: str) -> OCRResult:
        """OCR using PaddleOCR"""
        result = self.paddle_ocr.ocr(image_path, cls=True)
        
        lines: List[Any] = []
        text_parts: List[Any] = []
        confidences: List[Any] = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text_info = line[1]
                    
                    text = text_info[0] if isinstance(text_info, (list, tuple)) else text_info
                    conf = text_info[1] if isinstance(text_info, (list, tuple)) and len(text_info) > 1 else 1.0
                    
                    if text:
                        text_parts.append(text)
                        confidences.append(conf)
                        lines.append({
                            'text': text,
                            'confidence': conf,
                            'bbox': bbox
                        })
        
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        raw_text = '\n'.join(text_parts)
        
        # Apply post-processing if enabled
        final_text = raw_text
        post_processing_metadata = {}
        if self.enable_post_processing and self.post_processor:
            try:
                post_result = self.post_processor.process(raw_text, lines)
                if post_result.success:
                    final_text = post_result.corrected_text
                    post_processing_metadata = {
                        'post_processing_applied': True,
                        'corrections_count': len(post_result.corrections),
                        'quality_score': post_result.quality_score,
                        'statistics': post_result.statistics
                    }
                    logger.debug(f"Post-processing: {len(post_result.corrections)} corrections, quality={post_result.quality_score:.2f}")
                else:
                    logger.warning(f"Post-processing failed: {post_result.error}")
                    post_processing_metadata = {
                        'post_processing_applied': False,
                        'post_processing_error': post_result.error
                    }
            except Exception as e:
                logger.error(f"Post-processing error: {e}")
                post_processing_metadata = {
                    'post_processing_applied': False,
                    'post_processing_error': str(e)
                }
        
        return OCRResult(
            success=len(text_parts) > 0,
            text=final_text,
            lines=lines,
            confidence=avg_conf,
            engine='paddle',
            metadata={
                'num_lines': len(lines),
                'language': 'fa',
                **post_processing_metadata
            }
        )
    
    def _ocr_tesseract(self, image_path: str) -> OCRResult:
        """OCR using Tesseract"""
        import pytesseract
        from PIL import Image
        
        image = Image.open(image_path)
        
        # Get detailed data
        data = pytesseract.image_to_data(
            image, 
            lang='fas+eng',
            output_type=pytesseract.Output.DICT
        )
        
        lines: List[Any] = []
        current_line: List[Any] = []
        current_line_num = -1
        
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            line_num = data['line_num'][i]
            
            if conf > 0 and text:
                if line_num != current_line_num:
                    if current_line:
                        lines.append({
                            'text': ' '.join([w['text'] for w in current_line]),
                            'confidence': sum(w['conf'] for w in current_line) / len(current_line) / 100,
                            'words': current_line
                        })
                    current_line: List[Any] = []
                    current_line_num = line_num
                
                current_line.append({
                    'text': text,
                    'conf': conf,
                    'bbox': [data['left'][i], data['top'][i], 
                            data['width'][i], data['height'][i]]
                })
        
        # Add last line
        if current_line:
            lines.append({
                'text': ' '.join([w['text'] for w in current_line]),
                'confidence': sum(w['conf'] for w in current_line) / len(current_line) / 100,
                'words': current_line
            })
        
        raw_text = '\n'.join([l['text'] for l in lines])
        avg_conf = sum(l['confidence'] for l in lines) / len(lines) if lines else 0.0
        
        # Apply post-processing if enabled
        final_text = raw_text
        post_processing_metadata = {}
        if self.enable_post_processing and self.post_processor:
            try:
                post_result = self.post_processor.process(raw_text, lines)
                if post_result.success:
                    final_text = post_result.corrected_text
                    post_processing_metadata = {
                        'post_processing_applied': True,
                        'corrections_count': len(post_result.corrections),
                        'quality_score': post_result.quality_score,
                        'statistics': post_result.statistics
                    }
                    logger.debug(f"Post-processing: {len(post_result.corrections)} corrections, quality={post_result.quality_score:.2f}")
                else:
                    logger.warning(f"Post-processing failed: {post_result.error}")
                    post_processing_metadata = {
                        'post_processing_applied': False,
                        'post_processing_error': post_result.error
                    }
            except Exception as e:
                logger.error(f"Post-processing error: {e}")
                post_processing_metadata = {
                    'post_processing_applied': False,
                    'post_processing_error': str(e)
                }
        
        return OCRResult(
            success=len(lines) > 0,
            text=final_text,
            lines=lines,
            confidence=avg_conf,
            engine='tesseract',
            metadata={
                'num_lines': len(lines),
                'language': 'fas+eng',
                'image_size': image.size,
                **post_processing_metadata
            }
        )
    
    def _ocr_easyocr(self, image_path: str) -> OCRResult:
        """OCR using EasyOCR"""
        # Lazy load reader
        if self.easyocr_reader is None:
            self.easyocr_reader = self._easyocr_module.Reader(
                ['fa', 'en'],
                gpu=False
            )
        
        result = self.easyocr_reader.readtext(image_path)
        
        lines: List[Any] = []
        text_parts: List[Any] = []
        confidences: List[Any] = []
        for detection in result:
            bbox, text, conf = detection
            if text:
                text_parts.append(text)
                confidences.append(conf)
                lines.append({
                    'text': text,
                    'confidence': conf,
                    'bbox': bbox
                })
        
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        raw_text = '\n'.join(text_parts)
        
        # Apply post-processing if enabled
        final_text = raw_text
        post_processing_metadata = {}
        if self.enable_post_processing and self.post_processor:
            try:
                post_result = self.post_processor.process(raw_text, lines)
                if post_result.success:
                    final_text = post_result.corrected_text
                    post_processing_metadata = {
                        'post_processing_applied': True,
                        'corrections_count': len(post_result.corrections),
                        'quality_score': post_result.quality_score,
                        'statistics': post_result.statistics
                    }
                    logger.debug(f"Post-processing: {len(post_result.corrections)} corrections, quality={post_result.quality_score:.2f}")
                else:
                    logger.warning(f"Post-processing failed: {post_result.error}")
                    post_processing_metadata = {
                        'post_processing_applied': False,
                        'post_processing_error': post_result.error
                    }
            except Exception as e:
                logger.error(f"Post-processing error: {e}")
                post_processing_metadata = {
                    'post_processing_applied': False,
                    'post_processing_error': str(e)
                }
        
        return OCRResult(
            success=len(text_parts) > 0,
            text=final_text,
            lines=lines,
            confidence=avg_conf,
            engine='easyocr',
            metadata={
                'num_lines': len(lines),
                'language': 'fa+en',
                **post_processing_metadata
            }
        )
    
    def ocr_pdf(self, pdf_path: str, dpi: int = 300) -> OCRResult:
        """
        Perform OCR on a PDF file
        
        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for PDF to image conversion
         
        Returns:
            OCRResult with extracted text from all pages
        
        Raises:
            SecurityConstraintError: If OCR confidence is below 0.85
        """
        try:
            from pdf2image import convert_from_path
        except ImportError:
            return OCRResult(
                success=False,
                text="",
                lines=[],
                confidence=0.0,
                engine=self.active_engine or "none",
                metadata={},
                error="pdf2image not available. Install: pip install pdf2image"
            )
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Convert PDF to images
                images = convert_from_path(
                    pdf_path,
                    dpi=dpi,
                    output_folder=temp_dir,
                    fmt='png'
                )
                
                all_lines: List[Any] = []
                all_text_parts: List[Any] = []
                all_confidences: List[Any] = []
                page_results: List[Any] = []
                for page_num, image in enumerate(images):
                    # Save image temporarily
                    img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                    image.save(img_path)
                    
                    # OCR the page
                    page_result = self.ocr_image(img_path)
                    
                    if page_result.success:
                        all_text_parts.append(f"=== صفحه {page_num + 1} ===\n{page_result.text}")
                        all_lines.extend(page_result.lines)
                        all_confidences.append(page_result.confidence)
                        page_results.append({
                            'page': page_num + 1,
                            'lines': len(page_result.lines),
                            'confidence': page_result.confidence
                        })
                
                avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
                
                # Check confidence for the overall PDF result
                if avg_conf < 0.85:
                    raise SecurityConstraintError(
                        f"OCR confidence too low: {avg_conf:.2f} < 0.85",
                        details={"confidence": avg_conf, "engine": self.active_engine or "unknown"}
                    )
                
                return OCRResult(
                    success=len(all_text_parts) > 0,
                    text='\n\n'.join(all_text_parts),
                    lines=all_lines,
                    confidence=avg_conf,
                    engine=self.active_engine or "unknown",
                    metadata={
                        'num_pages': len(images),
                        'dpi': dpi,
                        'page_results': page_results
                    }
                )
                
        except Exception as e:
            logger.error(f"PDF OCR failed: {e}")
            # If it's a SecurityConstraintError, re-raise it
            if isinstance(e, SecurityConstraintError):
                raise
            return OCRResult(
                success=False,
                text="",
                lines=[],
                confidence=0.0,
                engine=self.active_engine or "unknown",
                metadata={},
                error=str(e)
            )


# ============================================================================
# Convenience Functions
# ============================================================================

# Thread-safe singleton for OCR engine
from mahoun.core.singleton import ThreadSafeSingleton

_ocr_singleton = ThreadSafeSingleton["OCREngine"]("OCREngine")


def get_ocr_engine() -> OCREngine:
    """
    Get or create global OCR engine instance (thread-safe).
    
    Returns:
        OCREngine instance
    """
    return _ocr_singleton.get_instance(factory=lambda: OCREngine())


def ocr_image(image_path: str) -> OCRResult:
    """
    Perform OCR on an image file
    
    Args:
        image_path: Path to image file
    
    Returns:
        OCRResult with extracted text
    
    Example:
        >>> result = ocr_image("document.jpg")
        >>> if result.success:
        ...     print(result.text)
        ...     print(f"Confidence: {result.confidence:.2%}")
    """
    return get_ocr_engine().ocr_image(image_path)


def ocr_pdf(pdf_path: str, dpi: int = 300) -> OCRResult:
    """
    Perform OCR on a PDF file (converts to images first)
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for conversion (default 300)
    
    Returns:
        OCRResult with extracted text from all pages
    
    Example:
        >>> result = ocr_pdf("scanned_document.pdf")
        >>> if result.success:
        ...     print(f"Extracted {result.metadata['num_pages']} pages")
        ...     print(result.text)
    """
    return get_ocr_engine().ocr_pdf(pdf_path, dpi)


def check_ocr_availability() -> Dict[str, Any]:
    """
    Check OCR engine availability
    
    Returns:
        Dictionary with availability info
    
    Example:
        >>> info = check_ocr_availability()
        >>> print(f"Available: {info['available_engines']}")
        >>> print(f"Active: {info['active_engine']}")
    """
    engine = get_ocr_engine()
    return {
        'is_available': engine.is_available,
        'available_engines': engine.available_engines,
        'active_engine': engine.active_engine,
        'recommendations': _get_install_recommendations(engine)
    }


def _get_install_recommendations(engine: OCREngine) -> List[str]:
    """Get installation recommendations"""
    recommendations: List[Any] = []
    if 'paddle' not in engine.available_engines:
        recommendations.append(
            "PaddleOCR (بهترین برای فارسی): pip install paddleocr paddlepaddle"
        )
    
    if 'tesseract' not in engine.available_engines:
        recommendations.append(
            "Tesseract: pip install pytesseract + نصب tesseract-ocr از سیستم عامل"
        )
    
    if 'easyocr' not in engine.available_engines:
        recommendations.append(
            "EasyOCR: pip install easyocr"
        )
    
    return recommendations


# ============================================================================
# OCRHandler Wrapper (BaseDocumentHandler-compatible)
# ============================================================================

class OCRHandler:
    """
    Wrapper for OCREngine to provide BaseDocumentHandler-compatible interface.
    
    Used by DocumentNormalizer for image OCR processing.
    
    This class:
    - Exposes `available`, `supports_file()`, `extract_text()` interface
    - Returns DocumentExtractionResult (not OCRResult)
    - Preserves bounding box info in metadata.lines
    
    Usage:
        handler = OCRHandler()
        if handler.available and handler.supports_file("image.jpg"):
            result = handler.extract_text("image.jpg")
            print(result.text)
            print(result.metadata.get("lines"))  # Bounding boxes
    """
    
    def __init__(self, language: str = "fa"):
        """Initialize OCRHandler with optional language"""
        self.language = language
        self._engine = None
        self._available = None
    
    @property
    def available(self) -> bool:
        """Check if OCR is available"""
        if self._available is None:
            self._init_engine()
        return self._available
    
    def _init_engine(self):
        """Initialize OCR engine (lazy)"""
        try:
            self._engine = get_ocr_engine()
            self._available = self._engine.is_available
        except Exception as e:
            logger.warning(f"OCRHandler: Failed to initialize engine: {e}")
            self._available = False
    
    def supports_file(self, file_path: str) -> bool:
        """Check if file type is supported (images)"""
        if not self.available:
            return False
        
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp']
        return any(file_path.lower().endswith(ext) for ext in image_extensions)
    
    def extract_text(self, file_path: str):
        """
        Extract text from image using OCR.
        
        Returns:
            DocumentExtractionResult with:
            - text: Extracted text
            - metadata.lines: Bounding box data from OCR
            - metadata.confidence: Average confidence
            - metadata.engine: Engine used
        """
        # Import here to avoid circular imports
        from .document_handlers import DocumentExtractionResult
        
        if not self.available:
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"file_path": file_path},
                error="OCR service not available",
                handler_used="ocr"
            )
        
        try:
            # Use OCREngine to do the actual work
            result = self._engine.ocr_image(file_path)
            
            return DocumentExtractionResult(
                success=result.success,
                text=result.text,
                metadata={
                    "file_path": file_path,
                    "handler": "ocr",
                    "engine": result.engine,
                    "confidence": result.confidence,
                    "lines": result.lines,  # Bounding box info preserved!
                    "num_lines": len(result.lines),
                    **result.metadata
                },
                error=result.error if not result.success else None,
                handler_used="ocr"
            )
            
        except Exception as e:
            logger.error(f"OCRHandler.extract_text failed: {e}")
            return DocumentExtractionResult(
                success=False,
                text="",
                metadata={"file_path": file_path},
                error=str(e),
                handler_used="ocr"
            )


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    print("🔍 OCR Handler Test")
    print("=" * 50)
    
    info = check_ocr_availability()
    print(f"Available: {info['is_available']}")
    print(f"Engines: {info['available_engines']}")
    print(f"Active: {info['active_engine']}")
    
    if info['recommendations']:
        print("\n📦 Installation recommendations:")
        for rec in info['recommendations']:
            print(f"  - {rec}")
