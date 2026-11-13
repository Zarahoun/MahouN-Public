# -*- coding: utf-8 -*-
"""
Text Utilities for MAHOUN Legal AI
ابزارهای پردازش متن برای سیستم MAHOUN

این ماژول شامل:
- نرمال‌سازی متن فارسی
- پاکسازی و تمیزکاری متن
- حذف اطلاعات شخصی (PII)
- توکنایزیشن ساده
- توابع کمکی متن
"""

import re
from typing import List, Optional, Dict, Tuple
import logging

# تنظیمات
logger = logging.getLogger(__name__)

# ============================================================================
# Import ماژول نرمال‌سازی
# ============================================================================

try:
    from .persian_legal_nlp import (
        Normalizer, 
        normalize, 
        word_tokenize, 
        sent_tokenize,
        is_persian,
        remove_punctuation,
        count_words
    )
    _normalizer = Normalizer()
    _HAS_PERSIAN_NLP = True
except ImportError:
    logger.warning("persian_legal_nlp not found, using fallback normalizer")
    _HAS_PERSIAN_NLP = False
    
    # Fallback: نرمال‌سازی ساده
    class Normalizer:
        def normalize(self, text):
            if not text:
                return ""
            trans = str.maketrans("كي٠١٢٣٤٥٦٧٨٩", "کی0123456789")
            text = text.translate(trans)
            text = re.sub(r"[\u0617-\u061A\u064B-\u065F]", "", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()
    
    _normalizer = Normalizer()
    
    def normalize(text: str) -> str:
        return _normalizer.normalize(text)
    
    def word_tokenize(text: str) -> List[str]:
        return text.split()
    
    def sent_tokenize(text: str) -> List[str]:
        return [s.strip() for s in re.split(r'[.!?؟]+', text) if s.strip()]
    
    def is_persian(text: str) -> bool:
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return persian_chars > len(text) * 0.5
    
    def remove_punctuation(text: str) -> str:
        return re.sub(r'[^\w\s]', '', text)
    
    def count_words(text: str) -> int:
        return len(word_tokenize(text))


# ============================================================================
# الگوهای PII (اطلاعات شخصی)
# ============================================================================

PII_PATTERNS = [
    # کد ملی (10 رقم)
    (re.compile(r'\b\d{10}\b'), '[NATIONAL_ID]'),
    
    # شماره موبایل (09xxxxxxxxx)
    (re.compile(r'\b09\d{9}\b'), '[MOBILE]'),
    
    # شماره تلفن ثابت (021xxxxxxxx)
    (re.compile(r'\b0\d{2,3}\d{7,8}\b'), '[PHONE]'),
    
    # تاریخ (YYYY-MM-DD)
    (re.compile(r'\b\d{4}-\d{2}-\d{2}\b'), '[DATE]'),
    
    # تاریخ فارسی (1400/01/01)
    (re.compile(r'\b\d{4}/\d{2}/\d{2}\b'), '[DATE]'),
    
    # ایمیل
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),
    
    # کد پستی (10 رقم)
    (re.compile(r'\b\d{10}\b'), '[POSTAL_CODE]'),
    
    # شماره کارت بانکی (16 رقم)
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD_NUMBER]'),
    
    # شماره شبا (IR + 24 رقم)
    (re.compile(r'\bIR\d{24}\b'), '[IBAN]'),
]


# ============================================================================
# الگوهای متن ناخواسته
# ============================================================================

UNWANTED_PATTERNS = [
    # URL ها
    re.compile(r'https?://\S+'),
    re.compile(r'www\.\S+'),
    
    # منشن و هشتگ
    re.compile(r'@\w+'),
    re.compile(r'#\w+'),
    
    # ایمیل
    re.compile(r'\S+@\S+'),
    
    # HTML tags
    re.compile(r'<[^>]+>'),
    
    # کاراکترهای تکراری (بیش از 3 بار)
    re.compile(r'(.)\1{3,}'),
]


# ============================================================================
# توابع اصلی
# ============================================================================

def normalize_fa(text: str, 
                 fix_encoding: bool = True,
                 remove_extra_spaces: bool = True) -> str:
    """
    نرمال‌سازی متن فارسی
    
    Args:
        text: متن ورودی
        fix_encoding: اصلاح مشکلات encoding
        remove_extra_spaces: حذف فاصله‌های اضافی
    
    Returns:
        متن نرمال شده
    
    Examples:
        >>> normalize_fa("این متن تست است   كه باید نرمال شود")
        'این متن تست است که باید نرمال شود'
    """
    if not text:
        return ""
    
    # اصلاح encoding (اگر ftfy موجود باشد)
    if fix_encoding:
        try:
            from ftfy import fix_text
            text = fix_text(text)
        except ImportError:
            pass
    
    # نرمال‌سازی با persian_legal_nlp
    text = _normalizer.normalize(text)
    
    # حفظ نیم‌فاصله
    text = text.replace('\u200c', '‌')
    
    # حذف فاصله‌های اضافی
    if remove_extra_spaces:
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()
    
    return text


def clean_text(text: str,
               normalize: bool = True,
               remove_urls: bool = True,
               remove_emails: bool = True,
               remove_extra_spaces: bool = True,
               remove_special_chars: bool = False) -> str:
    """
    پاکسازی کامل متن
    
    Args:
        text: متن ورودی
        normalize: نرمال‌سازی متن
        remove_urls: حذف URL ها
        remove_emails: حذف ایمیل‌ها
        remove_extra_spaces: حذف فاصله‌های اضافی
        remove_special_chars: حذف کاراکترهای خاص
    
    Returns:
        متن پاک شده
    
    Examples:
        >>> clean_text("این متن   دارای    فاصله‌های زیاد است")
        'این متن دارای فاصله‌های زیاد است'
    """
    if not text:
        return ""
    
    # نرمال‌سازی
    if normalize:
        text = normalize_fa(text)
    
    # حذف URL ها
    if remove_urls:
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)
    
    # حذف ایمیل‌ها
    if remove_emails:
        text = re.sub(r'\S+@\S+', '', text)
    
    # حذف HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # حذف کاراکترهای تکراری
    text = re.sub(r'(.)\1{3,}', r'\1\1', text)
    
    # حذف کاراکترهای کنترلی
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    
    # حذف کاراکترهای خاص (اختیاری)
    if remove_special_chars:
        text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text)
    
    # حذف فاصله‌های اضافی
    if remove_extra_spaces:
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
    
    return text


def redact_pii(text: str, 
               patterns: Optional[List[Tuple]] = None) -> str:
    """
    حذف اطلاعات شخصی (PII) از متن
    
    Args:
        text: متن ورودی
        patterns: الگوهای سفارشی (اختیاری)
    
    Returns:
        متن با PII حذف شده
    
    Examples:
        >>> redact_pii("شماره من 09123456789 است")
        'شماره من [MOBILE] است'
    """
    if not text:
        return ""
    
    patterns = patterns or PII_PATTERNS
    
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    
    return text


def remove_unwanted_content(text: str) -> str:
    """
    حذف محتوای ناخواسته (URL، منشن، هشتگ، ...)
    
    Args:
        text: متن ورودی
    
    Returns:
        متن پاک شده
    """
    if not text:
        return ""
    
    for pattern in UNWANTED_PATTERNS:
        text = pattern.sub('', text)
    
    # حذف فاصله‌های اضافی
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


# ============================================================================
# توکنایزیشن
# ============================================================================

def sent_tokenize_simple(text: str) -> List[str]:
    """
    تقسیم ساده متن به جملات
    
    Args:
        text: متن ورودی
    
    Returns:
        لیست جملات
    
    Examples:
        >>> sent_tokenize_simple("این جمله اول است. این جمله دوم است.")
        ['این جمله اول است', 'این جمله دوم است']
    """
    if not text:
        return []
    
    # تقسیم بر اساس علائم فارسی/انگلیسی
    sentences = re.split(r'(?<=[\.!\؟\!])\s+', text)
    
    return [s.strip() for s in sentences if s.strip()]


def word_tokenize_simple(text: str) -> List[str]:
    """
    تقسیم ساده متن به کلمات
    
    Args:
        text: متن ورودی
    
    Returns:
        لیست کلمات
    """
    if not text:
        return []
    
    # حذف علائم نگارشی و تقسیم
    words = re.findall(r'\b\w+\b', text)
    
    return [w for w in words if w.strip()]


# ============================================================================
# توابع تحلیلی
# ============================================================================

def get_text_stats(text: str) -> Dict:
    """
    آمار متن
    
    Args:
        text: متن ورودی
    
    Returns:
        دیکشنری حاوی آمار
    
    Examples:
        >>> stats = get_text_stats("این یک متن تست است.")
        >>> stats['word_count']
        5
    """
    if not text:
        return {
            'char_count': 0,
            'word_count': 0,
            'sentence_count': 0,
            'is_persian': False,
            'avg_word_length': 0,
        }
    
    words = word_tokenize(text)
    sentences = sent_tokenize(text)
    
    return {
        'char_count': len(text),
        'word_count': len(words),
        'sentence_count': len(sentences),
        'is_persian': is_persian(text),
        'avg_word_length': sum(len(w) for w in words) / len(words) if words else 0,
        'unique_words': len(set(words)),
    }


def truncate_text(text: str, 
                  max_length: int = 1000,
                  suffix: str = '...') -> str:
    """
    کوتاه کردن متن
    
    Args:
        text: متن ورودی
        max_length: حداکثر طول
        suffix: پسوند (...)
    
    Returns:
        متن کوتاه شده
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def extract_keywords(text: str, 
                     top_n: int = 10,
                     min_length: int = 3) -> List[str]:
    """
    استخراج کلمات کلیدی (ساده)
    
    Args:
        text: متن ورودی
        top_n: تعداد کلمات برتر
        min_length: حداقل طول کلمه
    
    Returns:
        لیست کلمات کلیدی
    """
    if not text:
        return []
    
    # توکنایز و فیلتر
    words = word_tokenize(text)
    words = [w for w in words if len(w) >= min_length]
    
    # شمارش فراوانی
    from collections import Counter
    word_freq = Counter(words)
    
    # برترین کلمات
    return [word for word, _ in word_freq.most_common(top_n)]


# ============================================================================
# Aliases برای سازگاری
# ============================================================================

def normalize_text(text: str) -> str:
    """Alias for normalize_fa"""
    return normalize_fa(text)


def tokenize_words(text: str) -> List[str]:
    """Alias for word_tokenize"""
    return word_tokenize(text)


def tokenize_sentences(text: str) -> List[str]:
    """Alias for sent_tokenize"""
    return sent_tokenize(text)


# ============================================================================
# تست
# ============================================================================

if __name__ == '__main__':
    # تست نرمال‌سازی
    test_text = "این یک متن تست است   كه باید نرمال شود."
    print("متن اصلی:", test_text)
    print("نرمال شده:", normalize_fa(test_text))
    print("پاک شده:", clean_text(test_text))
    
    # تست PII
    pii_text = "شماره من 09123456789 و کد ملی 1234567890 است"
    print("\nمتن با PII:", pii_text)
    print("بدون PII:", redact_pii(pii_text))
    
    # تست آمار
    stats = get_text_stats(test_text)
    print("\nآمار متن:", stats)
    
    # تست کلمات کلیدی
    long_text = "قانون مدنی ایران شامل مواد متعددی است. ماده 10 قانون مدنی مهم است."
    keywords = extract_keywords(long_text)
    print("\nکلمات کلیدی:", keywords)
