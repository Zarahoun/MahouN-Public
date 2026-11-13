# -*- coding: utf-8 -*-
"""
Persian Legal NLP – Standalone Module
جایگزین کامل و پیشرفته hazm در پروژه MAHOUN

این ماژول شامل:
- نرمال‌سازی کامل متن فارسی (با parsivar)
- استخراج اصطلاحات حقوقی
- توکنایزیشن پیشرفته (با parsivar)
- لماتایزیشن (با parsivar)
- سازگاری کامل با API hazm
"""

import re
import logging
from typing import List, Optional, Dict

# تنظیمات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Import parsivar (اختیاری)
# ============================================================================

try:
    from parsivar import Normalizer as ParsivarNormalizer
    from parsivar import Tokenizer as ParsivarTokenizer
    from parsivar import FindStems

    _HAS_PARSIVAR = True
    logger.info("✅ parsivar loaded successfully")
except ImportError:
    _HAS_PARSIVAR = False
    logger.warning("⚠️  parsivar not found, using fallback methods")
    ParsivarNormalizer = None
    ParsivarTokenizer = None
    FindStems = None


# ============================================================================
# نرمال‌سازی متن فارسی
# ============================================================================

# نقشه تبدیل کاراکترها
CHAR_MAP = {
    # حروف عربی به فارسی
    "ك": "ک",
    "ي": "ی",
    "ى": "ی",
    "ئ": "ی",
    # اعداد عربی به انگلیسی
    "٠": "0",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
    # اعداد فارسی به انگلیسی
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
}

# اعراب و علائم اضافی
DIACRITICS = r"[\u064B-\u065F\u0617-\u061A\u06D6-\u06ED]"

# فاصله‌های مختلف
SPACES = r"[\u200B-\u200D\uFEFF\u00A0]"


def normalize(
    text: str,
    remove_diacritics: bool = True,
    normalize_numbers: bool = True,
    normalize_spaces: bool = True,
    remove_extra_spaces: bool = True,
    use_parsivar: bool = True,
) -> str:
    """
    نرمال‌سازی کامل متن فارسی

    Args:
        text: متن ورودی
        remove_diacritics: حذف اعراب
        normalize_numbers: تبدیل اعداد به انگلیسی
        normalize_spaces: نرمال‌سازی فاصله‌ها
        remove_extra_spaces: حذف فاصله‌های اضافی
        use_parsivar: استفاده از parsivar (اگر موجود باشد)

    Returns:
        متن نرمال شده

    Examples:
        >>> normalize("این یک متن تست است كه باید نرمال شود")
        'این یک متن تست است که باید نرمال شود'

        >>> normalize("ماده ۱۰ قانون مدنی")
        'ماده 10 قانون مدنی'
    """
    if not text:
        return ""

    # استفاده از parsivar اگر موجود باشد
    if use_parsivar and _HAS_PARSIVAR:
        try:
            normalizer = ParsivarNormalizer()
            text = normalizer.normalize(text)
            return text
        except Exception as e:
            logger.warning(f"parsivar normalization failed: {e}, using fallback")

    # Fallback: نرمال‌سازی دستی
    # تبدیل کاراکترها
    for old_char, new_char in CHAR_MAP.items():
        text = text.replace(old_char, new_char)

    # حذف اعراب
    if remove_diacritics:
        text = re.sub(DIACRITICS, "", text)

    # نرمال‌سازی فاصله‌های خاص
    if normalize_spaces:
        text = re.sub(SPACES, " ", text)

    # حذف فاصله‌های اضافی
    if remove_extra_spaces:
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

    # نرمال‌سازی نیم‌فاصله
    text = text.replace("\u200c", "\u200c")  # حفظ نیم‌فاصله

    return text


def clean_text(text: str) -> str:
    """
    پاکسازی و نرمال‌سازی متن

    Args:
        text: متن ورودی

    Returns:
        متن پاک شده
    """
    text = normalize(text)

    # حذف کاراکترهای کنترلی
    text = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", text)

    # حذف فاصله‌های اضافی
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================================
# توکنایزیشن
# ============================================================================


def word_tokenize(text: str, use_parsivar: bool = True) -> List[str]:
    """
    تقسیم متن به کلمات

    Args:
        text: متن ورودی
        use_parsivar: استفاده از parsivar (اگر موجود باشد)

    Returns:
        لیست کلمات

    Examples:
        >>> word_tokenize("این یک متن تست است.")
        ['این', 'یک', 'متن', 'تست', 'است', '.']
    """
    if not text:
        return []

    # استفاده از parsivar اگر موجود باشد
    if use_parsivar and _HAS_PARSIVAR:
        try:
            tokenizer = ParsivarTokenizer()
            tokens = tokenizer.tokenize_words(text)
            return tokens
        except Exception as e:
            logger.warning(f"parsivar tokenization failed: {e}, using fallback")

    # Fallback: توکنایزیشن ساده
    # نرمال‌سازی
    text = normalize(text, use_parsivar=False)

    # الگوی توکنایزیشن
    pattern = r"\b\w+\b|[^\w\s]"
    tokens = re.findall(pattern, text)

    return [t for t in tokens if t.strip()]


def sent_tokenize(text: str, use_parsivar: bool = True) -> List[str]:
    """
    تقسیم متن به جملات

    Args:
        text: متن ورودی
        use_parsivar: استفاده از parsivar (اگر موجود باشد)

    Returns:
        لیست جملات

    Examples:
        >>> sent_tokenize("این جمله اول است. این جمله دوم است.")
        ['این جمله اول است.', 'این جمله دوم است.']
    """
    if not text:
        return []

    # استفاده از parsivar اگر موجود باشد
    if use_parsivar and _HAS_PARSIVAR:
        try:
            tokenizer = ParsivarTokenizer()
            sentences = tokenizer.tokenize_sentences(text)
            return sentences
        except Exception as e:
            logger.warning(
                f"parsivar sentence tokenization failed: {e}, using fallback"
            )

    # Fallback: جداسازی ساده
    # نرمال‌سازی
    text = normalize(text, use_parsivar=False)

    # الگوی جداسازی جملات
    sentences = re.split(r"[.!?؟]+\s+", text)

    return [s.strip() for s in sentences if s.strip()]


# ============================================================================
# استخراج اصطلاحات حقوقی
# ============================================================================

# الگوهای حقوقی پیشرفته (بر اساس تحلیل 1000 سند واقعی)
LEGAL_PATTERNS = {
    # مواد و تبصره‌ها (بر اساس داده‌های واقعی: 358، 2، 348، 257، 353، 22، 197، 177)
    "ماده": r"(?:ماده|مواد)\s+(?:یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|یازده|دوازده|سیزده|چهارده|پانزده|شانزده|هفده|هجده|نوزده|بیست|\d+)(?:\s+(?:و|تا|الی|،)\s+\d+)*",
    "تبصره": r"تبصره\s+(?:\d+|یک|دو|سه|چهار|پنج|الحاقی)(?:\s+ماده\s+\d+)?",
    "بند": r"بند\s+(?:\d+|[آ-یa-z])",
    # قوانین (بر اساس داده‌های واقعی)
    "قانون": r"قانون\s+(?:آیین\s+دادرسی(?:\s+(?:مدنی|کیفری|دادگاه\s*های\s+عمومی\s+و\s+انقلاب))?|مدنی|کیفری|تجارت|مجازات\s+اسلامی|اساسی|کار|تشکیل(?:\s+دادگاه)?|تشدید\s+مجازات|اصلاح|مسئولیت\s+مدنی|ثبت\s+اسناد|املاک|مالیات|بیمه|شهرداری|انتخابات|احزاب|مطبوعات|تعزیرات|دیات|قصاص|حدود|روابط\s+کار)",
    # احکام و آرا (بر اساس داده‌های واقعی: صادره، قطعی، تجدیدنظر، داوری، بدوی، حضوری)
    "حکم": r"(?:حکم|رأی|رای)\s+(?:صادره|قطعی|غیابی|حضوری|ابتدایی|بدوی|تجدیدنظر|دیوان\s+عالی|نهایی|موقت|مقدماتی|داوری)",
    # قرارها (بر اساس داده‌های واقعی: رد، عدم، منع، تأمین، موقوفی، جلب، بازداشت)
    "قرار": r"قرار\s+(?:رد|عدم\s+(?:استماع|پذیرش)|بازداشت|آزادی|تأمین|منع\s+تعقیب|موقوفی\s+تعقیب|جلب|تفهیم\s+اتهام)",
    # دادگاه‌ها (بر اساس داده‌های واقعی: تجدیدنظر استان، بدوی، عمومی حقوقی، عمومی جزایی)
    "دادگاه": r"دادگاه\s+(?:تجدیدنظر(?:\s+استان(?:\s+\w+)?)?|بدوی|عمومی(?:\s+(?:حقوقی|جزایی|کیفری))?|انقلاب|خانواده|عالی\s+کشور|اطفال|نظامی|ویژه(?:\s+روحانیت)?|اداری)",
    # دادسرا و مراجع قضایی
    "دادسرا": r"دادسرا(?:ی)?\s+(?:عمومی|انقلاب|نظامی|ویژه)",
    "دیوان": r"دیوان\s+(?:عالی\s+کشور|عدالت\s+اداری)",
    "شورا": r"شورای\s+(?:حل\s+اختلاف|عالی\s+قضایی|نگهبان)",
    # جرائم (گسترده‌تر)
    "جرم": r"(?:جرم|جنایت|جنحه)\s+(?:کلاهبرداری|سرقت|قتل|خیانت\s+در\s+امانت|اختلاس|ارتشا|رشوه|CTSTR\s+عدوانی|ضرب\s+و\s+جرح|توهین|افترا|تهدید|آدم\s+ربایی|قاچاق|پولشویی|جعل|تزویر|فرار\s+از\s+پرداخت|چک\s+بلامحل)",
    # مجازات‌ها
    "مجازات": r"(?:محکوم\s+به|مجازات|تحمل)\s+(?:حبس|زندان|جزای\s+نقدی|شلاق|تازیانه|دیه|قصاص|اعدام|حد|تعزیر|انفصال|محرومیت)",
    "حبس": r"(?:حبس|زندان)\s+(?:تعزیری|تعلیقی|ابد|موقت)\s*(?:\d+\s*(?:سال|ماه|روز))?",
    "جزای_نقدی": r"جزای\s+نقدی\s+(?:\d+\s*(?:میلیون|هزار|میلیارد)?\s*(?:ریال|تومان))",
    # طرفین دعوا
    "طرفین": r"(?:تجدیدنظرخواه(?:ان)?|تجدیدنظرخوانده|خواهان|خوانده|شاکی|متهم|مدعی|مدعی\s+علیه|محکوم|محکوم\s+له|محکوم\s+علیه|متشاکی|معترض)",
    "وکیل": r"وکیل\s+(?:مدافع|دادگستری|تجدیدنظرخواه)",
    "قاضی": r"(?:قاضی|رئیس\s+(?:دادگاه|شعبه)|مشاور(?:\s+دادگاه)?|دادرس)",
    # پرونده و شعبه (بر اساس داده‌های واقعی)
    "پرونده": r"پرونده\s+(?:شماره|کلاسه|به\s+شماره)\s+[\d/\-]+",
    "شعبه": r"شعبه\s+(?:\d+|یک|دو|سه|چهار|پنج)",
    # دادنامه
    "دادنامه": r"دادنامه\s+(?:شماره|به\s+شماره)\s+[\d/\-]+",
    # اسناد و مدارک
    "سند": r"(?:سند|قرارداد|وکالتنامه|گواهی|اظهارنامه|دادخواست|لایحه|پاسخ\s+لایحه|اجاره\s*نامه)",
    # مفاهیم حقوقی
    "حق": r"حق\s+(?:حضانت|نفقه|مهریه|ارث|شفعه|مرور|اعتراض|تجدیدنظر|فرجام)",
    "دعوا": r"(?:دعوا|دعوی)\s+(?:حقوقی|کیفری|مدنی|خانوادگی|مالی)",
    "اعتراض": r"اعتراض\s+(?:ثالث|به\s+رأی|به\s+حکم|به\s+دادنامه)",
    # مهلت‌ها
    "مهلت": r"مهلت\s+(?:اعتراض|تجدیدنظر|اجرای\s+حکم|پرداخت|قانونی)",
    # اجرای احکام
    "اجرا": r"(?:اجرای\s+احکام|اجرای\s+حکم|اجراییه)",
    # مالی
    "خسارت": r"(?:خسارت|غرامت)\s+(?:مادی|معنوی|تأخیر\s+تأدیه)",
    "مهریه": r"مهریه\s*(?:\d+\s*(?:سکه|تومان|ریال))?",
    "نفقه": r"نفقه\s+(?:زوجه|اطفال|معوقه)",
    # طلاق و خانواده
    "طلاق": r"(?:طلاق|فسخ\s+نکاح|خلع)",
    # ارث
    "ارث": r"(?:ارث|میراث|ترکه|وراث|وارث)",
    # رسیدگی
    "رسیدگی": r"رسیدگی\s+(?:ماهوی|مجدد|مقدماتی)",
    # ابطال و فسخ
    "ابطال": r"(?:ابطال|فسخ|نقض)\s+(?:سند|قرارداد|حکم|دادنامه)",
}


def extract_legal_terms(
    text: str, categories: Optional[List[str]] = None
) -> List[Dict]:
    """
    استخراج اصطلاحات حقوقی از متن

    Args:
        text: متن ورودی
        categories: دسته‌های مورد نظر (None = همه)

    Returns:
        لیست اصطلاحات یافت شده

    Examples:
        >>> terms = extract_legal_terms("ماده 10 قانون مدنی")
        >>> len(terms)
        2
    """
    if not text:
        return []

    entities = []
    patterns = LEGAL_PATTERNS

    # فیلتر دسته‌ها
    if categories:
        patterns = {k: v for k, v in patterns.items() if k in categories}

    # استخراج
    for category, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(
                {
                    "text": match.group(),
                    "type": "LEGAL_TERM",
                    "category": category,
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    # مرتب‌سازی بر اساس موقعیت
    entities.sort(key=lambda x: x["start"])

    return entities


def extract_article_numbers(text: str) -> List[int]:
    """
    استخراج شماره مواد قانونی

    Args:
        text: متن ورودی

    Returns:
        لیست شماره مواد

    Examples:
        >>> extract_article_numbers("ماده 10 و ماده 20 قانون مدنی")
        [10, 20]
    """
    pattern = r"ماده\s+(\d+)"
    matches = re.findall(pattern, text)
    return [int(m) for m in matches]


def extract_case_numbers(text: str) -> List[str]:
    """
    استخراج شماره پرونده‌ها

    Args:
        text: متن ورودی

    Returns:
        لیست شماره پرونده‌ها

    Examples:
        >>> extract_case_numbers("پرونده شماره 1234/98")
        ['1234/98']
    """
    pattern = r"پرونده\s+(?:شماره|کلاسه)\s+([\d/]+)"
    return re.findall(pattern, text)


# ============================================================================
# لماتایزیشن ساده
# ============================================================================

# جدول پسوندهای فارسی
SUFFIXES = [
    "ها",
    "های",
    "ان",
    "ات",
    "ی",
    "یم",
    "ید",
    "ند",
    "م",
    "ت",
    "ش",
    "مان",
    "تان",
    "شان",
]


def lemmatize(word: str, use_parsivar: bool = True) -> str:
    """
    لماتایزیشن کلمه فارسی

    Args:
        word: کلمه ورودی
        use_parsivar: استفاده از parsivar (اگر موجود باشد)

    Returns:
        ریشه کلمه

    Examples:
        >>> lemmatize("کتاب‌ها")
        'کتاب'
    """
    if not word or len(word) < 3:
        return word

    # استفاده از parsivar اگر موجود باشد
    if use_parsivar and _HAS_PARSIVAR:
        try:
            stemmer = FindStems()
            stems = stemmer.convert_to_stem(word)
            if stems:
                return stems[0]
        except Exception as e:
            logger.warning(f"parsivar stemming failed: {e}, using fallback")

    # Fallback: حذف پسوندها
    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]

    return word


# ============================================================================
# کلاس Normalizer (سازگاری با hazm)
# ============================================================================


class Normalizer:
    """
    کلاس نرمال‌ساز سازگار با hazm.Normalizer

    این کلاس API مشابه hazm دارد برای سازگاری با کد قدیمی

    Examples:
        >>> normalizer = Normalizer()
        >>> normalizer.normalize("این متن تست است كه باید نرمال شود")
        'این متن تست است که باید نرمال شود'
    """

    def __init__(
        self,
        remove_diacritics: bool = True,
        normalize_numbers: bool = True,
        normalize_spaces: bool = True,
    ):
        """
        Args:
            remove_diacritics: حذف اعراب
            normalize_numbers: تبدیل اعداد
            normalize_spaces: نرمال‌سازی فاصله‌ها
        """
        self.remove_diacritics = remove_diacritics
        self.normalize_numbers = normalize_numbers
        self.normalize_spaces = normalize_spaces

    def normalize(self, text: str) -> str:
        """
        نرمال‌سازی متن

        Args:
            text: متن ورودی

        Returns:
            متن نرمال شده
        """
        return normalize(
            text,
            remove_diacritics=self.remove_diacritics,
            normalize_numbers=self.normalize_numbers,
            normalize_spaces=self.normalize_spaces,
        )

    def __call__(self, text: str) -> str:
        """امکان استفاده به صورت تابع"""
        return self.normalize(text)


# ============================================================================
# توابع کمکی
# ============================================================================


def is_persian(text: str) -> bool:
    """
    بررسی اینکه متن فارسی است یا نه

    Args:
        text: متن ورودی

    Returns:
        True اگر متن فارسی باشد
    """
    if not text:
        return False

    persian_pattern = r"[\u0600-\u06FF]"
    persian_chars = len(re.findall(persian_pattern, text))
    total_chars = len(re.findall(r"\w", text))

    if total_chars == 0:
        return False

    return (persian_chars / total_chars) > 0.5


def remove_punctuation(text: str) -> str:
    """
    حذف علائم نگارشی

    Args:
        text: متن ورودی

    Returns:
        متن بدون علائم نگارشی
    """
    pattern = r"[^\w\s]"
    return re.sub(pattern, "", text)


def count_words(text: str) -> int:
    """
    شمارش کلمات

    Args:
        text: متن ورودی

    Returns:
        تعداد کلمات
    """
    return len(word_tokenize(text))


# ============================================================================
# تابع اصلی برای تست
# ============================================================================


def process(text: str) -> Dict:
    """
    پردازش کامل متن

    Args:
        text: متن ورودی

    Returns:
        دیکشنری حاوی نتایج پردازش
    """
    return {
        "normalized": normalize(text),
        "tokens": word_tokenize(text),
        "sentences": sent_tokenize(text),
        "legal_terms": extract_legal_terms(text),
        "word_count": count_words(text),
        "is_persian": is_persian(text),
    }


# ============================================================================
# تست سریع
# ============================================================================

if __name__ == "__main__":
    # تست نرمال‌سازی
    test_text = "این یک متن تست است كه باید نرمال شود. ماده ۱۰ قانون مدنی."

    print("متن اصلی:", test_text)
    print("نرمال شده:", normalize(test_text))
    print("توکن‌ها:", word_tokenize(test_text))
    print("اصطلاحات حقوقی:", extract_legal_terms(test_text))

    # تست کلاس
    normalizer = Normalizer()
    print("کلاس Normalizer:", normalizer.normalize(test_text))


# ============================================================================
# توابع اضافی برای سازگاری با utils_text
# ============================================================================


def normalize_fa(text: str) -> str:
    """
    نرمال‌سازی فارسی (سازگار با utils_text)

    این تابع برای سازگاری با کد قدیمی است

    Args:
        text: متن ورودی

    Returns:
        متن نرمال شده

    Examples:
        >>> normalize_fa("این متن تست است كه باید نرمال شود")
        'این متن تست است که باید نرمال شود'
    """
    if not text:
        return ""

    # نرمال‌سازی
    text = normalize(text)

    # حفظ نیم‌فاصله
    text = text.replace("\u200c", "‌")

    # نرمال‌سازی فاصله‌ها
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def sent_tokenize_simple(text: str) -> List[str]:
    """
    تقسیم ساده متن به جملات (سازگار با utils_text)

    این تابع برای سازگاری با کد قدیمی است

    Args:
        text: متن ورودی

    Returns:
        لیست جملات

    Examples:
        >>> sent_tokenize_simple("این جمله اول است. این جمله دوم است.")
        ['این جمله اول است.', 'این جمله دوم است.']
    """
    if not text:
        return []

    # تقسیم بر اساس علائم فارسی و انگلیسی
    sentences = re.split(r"(?<=[\.!\؟\!])\s+", text)

    return [s.strip() for s in sentences if s.strip()]


# ============================================================================
# توابع پیشرفته برای پردازش گراف
# ============================================================================


def extract_entities_for_graph(text: str) -> List[Dict]:
    """
    استخراج موجودیت‌ها برای ساخت گراف

    این تابع موجودیت‌های حقوقی را با اطلاعات کامل استخراج می‌کند

    Args:
        text: متن ورودی

    Returns:
        لیست موجودیت‌ها با اطلاعات کامل
    """
    entities = extract_legal_terms(text)

    # اضافه کردن اطلاعات بیشتر
    for entity in entities:
        entity["confidence"] = 1.0  # اطمینان بالا برای regex
        entity["source"] = "persian_legal_nlp"
        entity["label"] = entity["category"].upper()

    return entities


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    محاسبه شباهت دو متن (ساده)

    Args:
        text1: متن اول
        text2: متن دوم

    Returns:
        امتیاز شباهت (0-1)
    """
    if not text1 or not text2:
        return 0.0

    # نرمال‌سازی
    text1 = normalize(text1).lower()
    text2 = normalize(text2).lower()

    # توکنایز
    tokens1 = set(word_tokenize(text1))
    tokens2 = set(word_tokenize(text2))

    # Jaccard similarity
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    if union == 0:
        return 0.0

    return intersection / union


def extract_keywords(text: str, top_k: int = 10) -> List[str]:
    """
    استخراج کلمات کلیدی از متن

    Args:
        text: متن ورودی
        top_k: تعداد کلمات کلیدی

    Returns:
        لیست کلمات کلیدی
    """
    if not text:
        return []

    # نرمال‌سازی و توکنایز
    text = normalize(text)
    tokens = word_tokenize(text)

    # حذف کلمات کوتاه و علائم
    tokens = [t for t in tokens if len(t) > 2 and t.isalnum()]

    # شمارش فراوانی
    from collections import Counter

    freq = Counter(tokens)

    # برگرداندن top_k
    return [word for word, _ in freq.most_common(top_k)]


def split_into_chunks(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> List[Dict]:
    """
    تقسیم متن به چانک‌ها

    Args:
        text: متن ورودی
        chunk_size: اندازه هر چانک (کاراکتر)
        overlap: همپوشانی بین چانک‌ها

    Returns:
        لیست چانک‌ها با metadata
    """
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)
    chunk_id = 0

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # سعی کنیم در مرز جمله قطع کنیم
        if end < text_len:
            # پیدا کردن آخرین نقطه یا علامت
            last_period = text.rfind(".", start, end)
            last_question = text.rfind("؟", start, end)
            last_exclaim = text.rfind("!", start, end)

            best_end = max(last_period, last_question, last_exclaim)
            if best_end > start + chunk_size // 2:
                end = best_end + 1

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "start": start,
                    "end": end,
                    "length": len(chunk_text),
                    "word_count": count_words(chunk_text),
                }
            )
            chunk_id += 1

        start = end - overlap

    return chunks


# ============================================================================
# توابع کمکی برای validation
# ============================================================================


def validate_legal_document(text: str) -> Dict:
    """
    اعتبارسنجی سند حقوقی

    Args:
        text: متن سند

    Returns:
        نتایج اعتبارسنجی
    """
    result = {"is_valid": True, "errors": [], "warnings": [], "stats": {}}

    # بررسی خالی بودن
    if not text or len(text.strip()) < 10:
        result["is_valid"] = False
        result["errors"].append("متن خیلی کوتاه است")
        return result

    # بررسی فارسی بودن
    if not is_persian(text):
        result["warnings"].append("متن به نظر فارسی نیست")

    # بررسی وجود اصطلاحات حقوقی
    legal_terms = extract_legal_terms(text)
    if len(legal_terms) == 0:
        result["warnings"].append("هیچ اصطلاح حقوقی یافت نشد")

    # آمار
    result["stats"] = {
        "length": len(text),
        "word_count": count_words(text),
        "sentence_count": len(sent_tokenize(text)),
        "legal_terms_count": len(legal_terms),
        "article_numbers": extract_article_numbers(text),
    }

    return result


# ============================================================================
# Export همه توابع
# ============================================================================


class PersianLegalNLP:
    """Wrapper class for Persian Legal NLP processing"""

    def process(self, text: str) -> Dict:
        return process(text)

    def extract_legal_entities(self, text: str) -> List[Dict]:
        return extract_legal_terms(text)

    def extract_article_references(self, text: str) -> List[int]:
        return extract_article_numbers(text)

    def normalize(self, text: str) -> str:
        return normalize(text)


__all__ = [
    # نرمال‌سازی
    "normalize",
    "normalize_fa",
    "clean_text",
    "Normalizer",
    "PersianLegalNLP",
    # توکنایزیشن
    "word_tokenize",
    "sent_tokenize",
    "sent_tokenize_simple",
    # استخراج
    "extract_legal_terms",
    "extract_article_numbers",
    "extract_case_numbers",
    "extract_entities_for_graph",
    "extract_keywords",
    # لماتایزیشن
    "lemmatize",
    # کمکی
    "is_persian",
    "remove_punctuation",
    "count_words",
    "compute_text_similarity",
    "split_into_chunks",
    "validate_legal_document",
    # پردازش
    "process",
]
