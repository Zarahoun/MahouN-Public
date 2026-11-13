"""
Persian Legal Text Normalizer
==============================
Specialized normalizer for Persian legal documents (Iranian judicial system).

This module handles ALL variants of Persian/Arabic characters and digits
to ensure consistent parsing and semantic correctness across the MAHOUN system.

Key Features:
- Arabic digits (٠١٢٣٤٥٦٧٨٩) → English (0123456789)
- Persian digits (۰۱۲۳۴۵۶۷۸۹) → English (0123456789)
- Persian/Arabic character normalization (ی/ي, ک/ك, etc.)
- Legal-specific typo correction
- Whitespace normalization

Usage:
    from mahoun.pipelines.ingestion.persian_normalizer import PersianLegalNormalizer
    
    normalizer = PersianLegalNormalizer()
    clean_text = normalizer.normalize_legal_text(raw_text)
    
    # Or use static methods:
    clean_digits = PersianLegalNormalizer.normalize_digits("شماره ٩٨۰١٢٣")
    # → "شماره 980123"
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PersianLegalNormalizer:
    """
    Comprehensive Persian legal text normalizer.
    
    Handles all variants of Persian, Arabic, and hybrid text to ensure
    semantic correctness in extraction, parsing, and indexing.
    
    Design Principle:
    - NEVER lose information
    - ALWAYS preserve semantic meaning
    - Be conservative: only normalize what's necessary
    """
    
    # ========================================================================
    # Character Mappings
    # ========================================================================
    
    # Persian digits
    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    
    # Arabic-Indic digits (commonly used in older legal documents)
    ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
    
    # Target: English digits
    ENGLISH_DIGITS = "0123456789"
    
    # Build translation tables
    PERSIAN_TO_ENGLISH = str.maketrans(PERSIAN_DIGITS, ENGLISH_DIGITS)
    ARABIC_TO_ENGLISH = str.maketrans(ARABIC_DIGITS, ENGLISH_DIGITS)
    
    # Character normalization map
    # Maps Arabic variants → Standard Persian
    CHAR_NORMALIZATIONS = {
        # ی variants (Ya)
        'ي': 'ی',  # Arabic Ya → Persian Ya
        'ئ': 'ی',  # Hamza on Ya → Persian Ya (context-dependent, but safe for search)
        
        # ک variants (Kaf)
        'ك': 'ک',  # Arabic Kaf → Persian Kaf
        
        # Alef variants
        'إ': 'ا',  # Alef with Hamza below
        'أ': 'ا',  # Alef with Hamza above
        'آ': 'ا',  # Alef with Madda (keep as-is in most cases, but normalize for search)
        
        # Waw variants
        'ؤ': 'و',  # Waw with Hamza above
        
        # Zero-width characters (remove these)
        '\u200c': '',  # Zero-width non-joiner (ZWNJ) - نیم‌فاصله
        '\u200d': '',  # Zero-width joiner (ZWJ)
        '\u200e': '',  # Left-to-right mark
        '\u200f': '',  # Right-to-left mark
    }
    
    # ========================================================================
    # Static Methods (Core Normalizers)
    # ========================================================================
    
    @staticmethod
    def normalize_digits(text: str) -> str:
        """
        Normalize all digit variants to English digits.
        
        Handles:
        - Persian digits: ۰۱۲۳۴۵۶۷۸۹
        - Arabic digits: ٠١٢٣٤٥٦٧٨٩
        - Mixed: "۱٢٣" → "123"
        
        Args:
            text: Input text
        
        Returns:
            Text with all digits normalized to English (0-9)
        
        Examples:
            >>> normalize_digits("شماره ٩٨۰١٢٣")
            "شماره 980123"
            
            >>> normalize_digits("ماده ۲۱۹")
            "ماده 219"
        """
        if not text:
            return text
        
        # Apply both translations
        text = text.translate(PersianLegalNormalizer.PERSIAN_TO_ENGLISH)
        text = text.translate(PersianLegalNormalizer.ARABIC_TO_ENGLISH)
        
        return text
    
    @staticmethod
    def normalize_chars(text: str) -> str:
        """
        Normalize Persian/Arabic character variants.
        
        Handles:
        - ي (Arabic Ya) → ی (Persian Ya)
        - ك (Arabic Kaf) → ک (Persian Kaf)
        - إ/أ/آ (Alef variants) → ا
        - ؤ (Waw with Hamza) → و
        - Zero-width characters (removed)
        
        Args:
            text: Input text
        
        Returns:
            Text with normalized characters
        
        Examples:
            >>> normalize_chars("دادگاه كیفري")
            "دادگاه کیفری"
        """
        if not text:
            return text
        
        # Apply character normalizations
        for old_char, new_char in PersianLegalNormalizer.CHAR_NORMALIZATIONS.items():
            text = text.replace(old_char, new_char)
        
        return text
    
    @staticmethod
    def normalize_legal_typos(text: str) -> str:
        """
        Correct common typos in Persian legal documents.
        
        This is based on real-world patterns observed in Iranian court documents.
        
        Args:
            text: Input text
        
        Returns:
            Text with common typos corrected
        
        Examples:
            >>> normalize_legal_typos("اقای احمد")
            "آقای احمد"
        """
        if not text:
            return text
        
        # Common typo patterns
        typo_corrections = [
            ("اقای", "آقای"),        # Mr. (common typo)
            ("اقا ", "آقای "),       # Mr. with space
            ("خانم ", "خانم "),      # Ensure spacing (already correct, but defensive)
            ("  ", " "),            # Multiple spaces → single space (will be handled by whitespace norm)
        ]
        
        for wrong, correct in typo_corrections:
            text = text.replace(wrong, correct)
        
        return text
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """
        Normalize whitespace in text.
        
        - Collapse multiple spaces → single space
        - Trim leading/trailing whitespace
        - Normalize tabs/newlines to spaces (context-dependent)
        
        Args:
            text: Input text
        
        Returns:
            Text with normalized whitespace
        
        Examples:
            >>> normalize_whitespace("شعبه   ۱۲  دادگاه")
            "شعبه ۱۲ دادگاه"
        """
        if not text:
            return text
        
        # Collapse multiple whitespace characters
        text = re.sub(r'\s+', ' ', text)
        
        # Trim
        text = text.strip()
        
        return text
    
    @staticmethod
    def remove_document_noise(text: str) -> str:
        """
        Remove common OCR/Document noise.
        
        Handles:
        - Page numbers (e.g., "صفحه ۱ از ۵")
        - Repeated headers/footers
        - Common OCR artifacts
        
        Args:
            text: Input text
            
        Returns:
            Cleaned text
        """
        if not text:
            return text
            
        # Remove page numbers
        # Patterns: "صفحه X از Y", "صفحه X", "Page X of Y"
        page_patterns = [
            r'صفحه\s+\d+\s+از\s+\d+',
            r'صفحه\s+\d+',
            r'Page\s+\d+\s+of\s+\d+',
        ]
        
        for pattern in page_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
            
        # Remove common header/footer noise (simple heuristics)
        # Example: "شماره دادنامه: ..." repeated
        # This is tricky without layout analysis, but we can remove standalone numbers that look like page numbers
        # text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        return text

    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        """
        Standardize Persian dates to ISO format (YYYY-MM-DD).
        
        Handles:
        - YYYY/MM/DD
        - YYYY-MM-DD
        - DD/MM/YYYY (heuristic)
        
        Args:
            date_str: Input date string
            
        Returns:
            ISO formatted date string or None if invalid
        """
        if not date_str:
            return None
            
        # Normalize digits first
        date_str = PersianLegalNormalizer.normalize_digits(date_str)
        
        # Pattern: YYYY/MM/DD or YYYY-MM-DD
        # 1399/01/02, 1399-1-2
        match = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', date_str)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
            
        return None  # Return None if pattern doesn't match (or keep original? Checklist says standardize)
    
    @staticmethod
    def normalize_legal_text(text: str, *, 
                            digits: bool = True,
                            chars: bool = True,
                            typos: bool = True,
                            whitespace: bool = True) -> str:
        """
        Full normalization pipeline for Persian legal text.
        
        This is the main entry point for normalizing legal documents.
        
        Args:
            text: Input text
            digits: Normalize digits (default: True)
            chars: Normalize characters (default: True)
            typos: Fix common typos (default: True)
            whitespace: Normalize whitespace (default: True)
        
        Returns:
            Fully normalized text
        
        Examples:
            >>> text = "شماره پرونده: ٩٨۰١٢٣ - دادگاه كیفري - اقای احمد"
            >>> normalize_legal_text(text)
            "شماره پرونده: 980123 - دادگاه کیفری - آقای احمد"
        """
        if not text:
            return text
        
        # Apply normalizations in order
        if digits:
            text = PersianLegalNormalizer.normalize_digits(text)
        
        if chars:
            text = PersianLegalNormalizer.normalize_chars(text)
        
        if typos:
            text = PersianLegalNormalizer.normalize_legal_typos(text)
        
        if whitespace:
            text = PersianLegalNormalizer.normalize_whitespace(text)
        
        return text
    
    # ========================================================================
    # Instance Methods (for stateful usage)
    # ========================================================================
    
    def __init__(self, *, 
                 enable_digits: bool = True,
                 enable_chars: bool = True,
                 enable_typos: bool = True,
                 enable_whitespace: bool = True):
        """
        Initialize normalizer with configuration.
        
        Args:
            enable_digits: Enable digit normalization
            enable_chars: Enable character normalization
            enable_typos: Enable typo correction
            enable_whitespace: Enable whitespace normalization
        """
        self.enable_digits = enable_digits
        self.enable_chars = enable_chars
        self.enable_typos = enable_typos
        self.enable_whitespace = enable_whitespace
        
        logger.debug(
            f"PersianLegalNormalizer initialized: "
            f"digits={enable_digits}, chars={enable_chars}, "
            f"typos={enable_typos}, whitespace={enable_whitespace}"
        )
    
    def normalize(self, text: str) -> str:
        """
        Normalize text using instance configuration.
        
        Args:
            text: Input text
        
        Returns:
            Normalized text based on instance settings
        """
        return self.normalize_legal_text(
            text,
            digits=self.enable_digits,
            chars=self.enable_chars,
            typos=self.enable_typos,
            whitespace=self.enable_whitespace
        )
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    @staticmethod
    def has_arabic_digits(text: str) -> bool:
        """Check if text contains Arabic-Indic digits."""
        return any(c in PersianLegalNormalizer.ARABIC_DIGITS for c in text)
    
    @staticmethod
    def has_persian_digits(text: str) -> bool:
        """Check if text contains Persian digits."""
        return any(c in PersianLegalNormalizer.PERSIAN_DIGITS for c in text)
    
    @staticmethod
    def has_mixed_digits(text: str) -> bool:
        """Check if text has mixed digit systems."""
        has_arabic = PersianLegalNormalizer.has_arabic_digits(text)
        has_persian = PersianLegalNormalizer.has_persian_digits(text)
        has_english = any(c.isdigit() for c in text)
        
        # Mixed if more than one system present
        return sum([has_arabic, has_persian, has_english]) > 1
    
    @staticmethod
    def detect_normalization_needed(text: str) -> dict:
        """
        Analyze text and determine what normalizations are needed.
        
        Returns:
            Dict with boolean flags for each normalization type
        
        Example:
            >>> detect_normalization_needed("شماره ٩٨۰١٢٣")
            {'digits': True, 'chars': False, 'typos': False, 'whitespace': False}
        """
        return {
            'digits': (
                PersianLegalNormalizer.has_arabic_digits(text) or
                PersianLegalNormalizer.has_persian_digits(text)
            ),
            'chars': any(c in PersianLegalNormalizer.CHAR_NORMALIZATIONS for c in text),
            'typos': 'اقای' in text or 'اقا ' in text,
            'whitespace': '  ' in text or text != text.strip(),
        }


# ============================================================================
# Convenience Functions (for backward compatibility)
# ============================================================================

def normalize_text(text: str) -> str:
    """
    Convenience function for full normalization.
    
    This is a drop-in replacement for the old normalize_text() function
    in minimal_verdict_parser.py.
    
    Args:
        text: Input text
    
    Returns:
        Fully normalized text
    """
    return PersianLegalNormalizer.normalize_legal_text(text)


def persian_digits_to_english(text: str) -> str:
    """
    Convenience function for digit normalization only.
    
    Backward compatible with old minimal_verdict_parser function.
    
    Args:
        text: Input text
    
    Returns:
        Text with all digit variants → English digits
    """
    return PersianLegalNormalizer.normalize_digits(text)
