"""
Minimal Verdict Parser - Bootstrap Edition
===========================================
Rule-based parser for Persian legal verdicts (NO LLM required).

This parser extracts structured information from raw verdict text files
using regex patterns and heuristics tuned for Iranian legal documents.

Usage:
    from mahoun.pipelines.ingestion.minimal_verdict_parser import parse_verdict_file
    
    verdict_struct = parse_verdict_file("path/to/verdict.txt")
    # Returns a JSON-compatible dict with structured verdict data
"""

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .persian_normalizer import PersianLegalNormalizer
from .ingestion_logger import IngestionLogger

# NER Integration (Enterprise NER Subsystem)
try:
    from .legal_ner import extract_entities as extract_ner_entities
    HAS_NER = True
except ImportError:
    HAS_NER = False
    extract_ner_entities: Optional[Any] = None
logger = logging.getLogger(__name__)

# ============================================================================
# Text Normalization & Utilities
# ============================================================================

def persian_digits_to_english(text: str) -> str:
    """
    Convert Persian/Arabic digits to English digits.
    
    Delegates to PersianLegalNormalizer for comprehensive handling.
    """
    return PersianLegalNormalizer.normalize_digits(text)


def normalize_text(text: str) -> str:
    """
    Normalize Persian text for consistent parsing.
    
    Uses PersianLegalNormalizer to handle:
    - Persian/Arabic digits
    - Character variants (y/k/alef)
    - Legal typos
    - Whitespace
    - Document noise (headers/footers)
    """
    # Step 1: Basic normalization
    text = PersianLegalNormalizer.normalize_legal_text(text)
    
    # Step 2: Remove document noise (Phase 3)
    text = PersianLegalNormalizer.remove_document_noise(text)
    
    return text


def clean_name(name: str) -> str:
    """Clean and normalize person names"""
    name = name.strip()
    # Remove extra dots
    name = re.sub(r'\.{2,}', '.', name)
    return name


# ============================================================================
# Extraction Helpers
# ============================================================================

def extract_court_details(text: str) -> Dict[str, Any]:
    """
    Extract detailed court information (Level, Branch, Location).
    
    Handles diverse patterns like:
    - "شعبه 10 دادگاه عمومی حقوقی تهران"
    - "دادگاه تجدیدنظر استان مازندران شعبه 5"
    """
    details = {
        "level": None,
        "branch": None,
        "city": None,
        "province": None,
        "full_name": None
    }
    
    # Pattern 1: Branch X of Court Y in Location Z
    # Example: شعبه 10 دادگاه عمومی حقوقی تهران
    # City is either prefixed (شهرستان ...) or just the last word (تهران)
    pat1 = r'شعبه\s+(\d+)\s+(دادگاه\s+.+?)\s+((?:شهرستان|شهر|استان)\s+[^،\n]+|[^،\n\s]+)$'
    m1 = re.search(pat1, text)
    if m1:
        details["branch"] = m1.group(1)
        details["level"] = m1.group(2).strip()
        details["city"] = m1.group(3).strip() # heuristic
        details["full_name"] = m1.group(0)
        return details

    # Pattern 2: Court Y Province Z Branch X
    # Example: دادگاه تجدیدنظر استان تهران شعبه 12
    pat2 = r'(دادگاه\s+[^،\n]+?)\s+استان\s+([^،\n]+?)\s+شعبه\s+(\d+)'
    m2 = re.search(pat2, text)
    if m2:
        details["level"] = m2.group(1).strip()
        details["province"] = m2.group(2).strip()
        details["branch"] = m2.group(3)
        details["full_name"] = m2.group(0)
        return details

    # Fallback: Simple level extraction (existing logic)
    patterns = [
        r'(دادگاه\s+تجدیدنظر\s+استان)',
        r'(دادگاه\s+تجدیدنظر)',
        r'(دیوان\s+عالی\s+کشور)',
        r'(دادگاه\s+بدوی)',
        r'(شعبه\s+\d+\s+دادگاه)',
        r'(دادگاه\s+عمومی\s+حقوقی)',
        r'(دادگاه\s+کیفری\s+یک)',
        r'(دادگاه\s+کیفری\s+دو)',
        r'(دادگاه\s+انقلاب)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            details["level"] = match.group(1)
            return details
            
    return details


def extract_court_level(text: str) -> Optional[str]:
    """
    Extract court level (Backward Compatibility Wrapper).
    """
    details = extract_court_details(text)
    if details["level"]:
        if details["branch"]:
            return f"{details['level']} شعبه {details['branch']}"
        return details["level"]
    
    logger.warning("Could not extract court_level from text")
    return None


def detect_finality(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if the verdict is final (قطعی).
    
    Returns:
        (is_final: bool, basis: str or None)
    """
    finality_patterns = [
        (r'این\s+رأی\s+[^.]*قطعی\s+است', 'ذکر صریح قطعیت'),
        (r'این\s+دادنامه\s+[^.]*قطعی\s+است', 'ذکر صریح قطعیت'),
        (r'قطعی\s+بودن\s+رأی', 'اشاره به قطعیت'),
        (r'غیرقابل\s+تجدیدنظر', 'غیرقابل تجدیدنظر'),
    ]
    
    for pattern, basis in finality_patterns:
        if re.search(pattern, text):
            return True, basis
    
    # Check if it's a تجدیدنظر court (usually final)
    # Improved logic: Ensure context implies it's the court issuing the verdict
    if re.search(r'رأی\s+دادگاه\s+تجدیدنظر', text) or re.search(r'در\s+دادگاه\s+تجدیدنظر', text):
        return True, 'رأی دادگاه تجدیدنظر'
    
    return False, None


def detect_case_type(text: str) -> str:
    """
    Detect case type from verdict text.
    
    Returns:
        String describing case type (e.g., "اعتراض ثالث اجرایی / رفع توقیف")
    """
    types: List[Any] = []
    # اعتراض ثالث و توقیف
    if re.search(r'اعتراض\s+ثالث', text):
        types.append('اعتراض ثالث')
    
    if re.search(r'توقیف\s+عملیات\s+اجرایی', text) or re.search(r'رفع\s+توقیف', text):
        types.append('توقیف عملیات اجرایی')
    
    if re.search(r'اجرای\s+احکام', text):
        types.append('اجرای احکام')
    
    # دعاوی مالی
    if re.search(r'مطالبه\s+وجه', text) or re.search(r'مطالبه\s+خسارت', text):
        types.append('مطالبه وجه/خسارت')
    
    if re.search(r'مطالبه\s+نفقه', text):
        types.append('مطالبه نفقه')
    
    # دعاوی املاک
    if re.search(r'خلع\s+ید', text):
        types.append('خلع ید')
    
    if re.search(r'تخلیه', text):
        types.append('تخلیه')
    
    if re.search(r'الزام\s+به\s+تنظیم\s+سند', text) or re.search(r'الزام\s+به\s+انتقال', text):
        types.append('الزام به تنظیم سند')
    
    if re.search(r'بیع', text) or re.search(r'معامله', text):
        types.append('بیع و معاملات')
    
    # دعاوی ابطال و فسخ
    if re.search(r'ابطال\s+سند', text) or re.search(r'ابطال\s+عقد', text):
        types.append('ابطال سند')
    
    if re.search(r'فسخ\s+معامله', text) or re.search(r'فسخ\s+قرارداد', text):
        types.append('فسخ معامله')
    
    # دعاوی خانواده
    if re.search(r'طلاق', text):
        types.append('طلاق')
    
    if re.search(r'حضانت', text):
        types.append('حضانت')
    
    if re.search(r'نفقه', text):
        types.append('نفقه')
    
    if re.search(r'مهریه', text):
        types.append('مهریه')
    
    # دعاوی ارث و وصیت
    if re.search(r'ارث', text) or re.search(r'میراث', text):
        types.append('ارث و میراث')
    
    if re.search(r'انحصار\s+وراثت', text) or re.search(r'گواهی\s+حصر\s+وراثت', text):
        types.append('انحصار وراثت')
    
    if re.search(r'وصیت', text) or re.search(r'افتتاح\s+وصیت', text):
        types.append('وصیت')
    
    # دعاوی جزایی و دیه
    if re.search(r'دیه', text):
        types.append('دیه')
    
    if re.search(r'قصاص', text):
        types.append('قصاص')
    
    # دعاوی شرکتی و تجاری
    if re.search(r'انحلال\s+شرکت', text):
        types.append('انحلال شرکت')
    
    if re.search(r'ورشکستگی', text):
        types.append('ورشکستگی')
    
    if re.search(r'چک', text) or re.search(r'برات', text) or re.search(r'سفته', text):
        types.append('اوراق تجاری')
    
    # دعاوی کار
    if re.search(r'کار\s+و\s+کارگر', text) or re.search(r'روابط\s+کار', text):
        types.append('کار و کارگر')
    
    if re.search(r'مزد', text) or re.search(r'حق\s+سنوات', text):
        types.append('مزد و مطالبات کارگری')
    
    # دعاوی مالیاتی و اداری
    if re.search(r'مالیات', text):
        types.append('مالیات')
    
    if re.search(r'تأمین\s+اجتماعی', text):
        types.append('تأمین اجتماعی')
    
    # دعاوی جرائم
    if re.search(r'کلاهبرداری', text):
        types.append('کلاهبرداری')
    
    if re.search(r'خیانت\s+در\s+امانت', text):
        types.append('خیانت در امانت')
    
    if types:
        return ' / '.join(types)
    
    logger.warning("Could not detect case_type from text")
    return None


def extract_parties(text: str) -> Dict[str, Any]:
    """
    Extract parties (plaintiffs, defendants, attorneys) from verdict.
    
    Pattern: (خانم|آقای) [name] فرزند [father_name]
    """
    parties = {
        "third_party_objector": None,
        "third_party_objector_attorney": None,
        "respondents": [],
        "respondents_attorneys": [],
    }
    
    # Pattern for person: (خانم|آقای) NAME فرزند FATHER
    person_pattern = r'(خانم|آقای)\s+([^،\.\n]+?)\s+فرزند\s+([^،\.\n]+?)(?:\s|،|\.|$)'
    
    matches = list(re.finditer(person_pattern, text))
    
    if not matches:
        return parties
    
    # First match: third party objector
    if len(matches) >= 1:
        m = matches[0]
        parties["third_party_objector"] = {
            "title": m.group(1),
            "name": clean_name(m.group(2)),
            "father_name": clean_name(m.group(3)),
        }
    
    # Second match: attorney for third party objector
    if len(matches) >= 2:
        m = matches[1]
        # Check if this is labeled as attorney
        snippet = text[max(0, m.start()-50):m.start()+100]
        if 'وکیل' in snippet or 'با وکالت' in snippet:
            parties["third_party_objector_attorney"] = {
                "title": m.group(1),
                "name": clean_name(m.group(2)),
                "father_name": clean_name(m.group(3)),
            }
        else:
            # First respondent
            parties["respondents"].append({
                "title": m.group(1),
                "name": clean_name(m.group(2)),
                "father_name": clean_name(m.group(3)),
            })
    
    # Remaining matches: respondents and their attorneys
    for i, m in enumerate(matches[2:], start=2):
        snippet = text[max(0, m.start()-50):m.start()+100]
        
        person = {
            "title": m.group(1),
            "name": clean_name(m.group(2)),
            "father_name": clean_name(m.group(3)),
        }
        
        if 'وکیل' in snippet or 'با وکالت' in snippet:
            parties["respondents_attorneys"].append(person)
        else:
            parties["respondents"].append(person)
    
    return parties


def extract_legal_articles(text: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Extract legal article references from text with validity enforcement.
    
    LEGAL INTEGRITY FIX: Added REPEALED_LAWS check to prevent citing invalid laws.
    
    Returns:
        (substantive_law, procedural_law, fiqh_principles)
    """
    substantive_law: List[Any] = []
    procedural_law: List[Any] = []
    fiqh_principles: List[Any] = []
    
    # REPEALED LAWS DATABASE - Laws that are no longer valid
    REPEALED_LAWS = {
        # Add known repealed laws - this should be maintained by legal team
        "قانون مدنی سابق": "1307",  # Replaced by current civil code
        "قانون تجارت قدیم": "1311",  # Old commercial code
        "قانون آیین دادرسی مدنی سابق": "1379",  # Old civil procedure
        # Add more as needed by legal experts
    }
    
    def is_law_active(law_name: str, article_num: str) -> bool:
        """
        Check if a law is currently active (not repealed).
        
        Args:
            law_name: Name of the law
            article_num: Article number
            
        Returns:
            True if law is active, False if repealed
        """
        # Normalize law name for comparison
        law_normalized = law_name.strip().lower()
        
        # Check against repealed laws database
        for repealed_law, repeal_year in REPEALED_LAWS.items():
            if repealed_law.lower() in law_normalized:
                logger.warning(f"LEGAL_INTEGRITY_WARNING: Citing repealed law - {law_name} (repealed {repeal_year})")
                return False
        
        # Additional heuristics for detecting potentially invalid references
        suspicious_patterns = [
            "سابق", "قدیم", "منسوخ", "ملغی", "لغو شده"
        ]
        
        if any(pattern in law_normalized for pattern in suspicious_patterns):
            logger.warning(f"LEGAL_INTEGRITY_WARNING: Potentially invalid law reference - {law_name}")
            return False
            
        return True
    
    # Convert Persian digits
    text_normalized = persian_digits_to_english(text)
    
    # Pattern: ماده NUMBER قانون LAW_NAME
    article_pattern = r'ماده\s+([0-9۰-۹\s]+)\s+قانون\s+([^\.\،\)]+?)(?:\.|،|\)|$)'
    
    matches = re.findall(article_pattern, text)
    
    for article_nums, law_name in matches:
        # Clean article numbers
        article_nums = persian_digits_to_english(article_nums.strip())
        law_name = law_name.strip()
        
        # VALIDITY CHECK: Skip if law is repealed or invalid
        if not is_law_active(law_name, article_nums):
            continue
        
        # Split multiple articles (e.g., "146 147")
        numbers = re.findall(r'\d+', article_nums)
        
        for num in numbers:
            ref = f"ماده {num} {law_name}"
            
            # Classify - بهبود یافته برای قوانین مختلف
            # قوانین موضوعی (substantive law)
            if any(keyword in law_name for keyword in [
                'مدنی',  # اما نه آیین دادرسی مدنی
                'تجارت',
                'کار',
                'مجازات',
                'دیات',
                'امور حسبی',
                'ثبت',
                'روابط موجر و مستأجر',
                'صدور چک',
                'مالیات',
                'تأمین اجتماعی',
                'بیمه',
                'حمایت خانواده',
            ]) and not any(exclude in law_name for exclude in [
                'آیین دادرسی',
                'اجرای احکام',
                'دادگاه',
            ]):
                if ref not in substantive_law:
                    substantive_law.append(ref)
            # قوانین آیین دادرسی (procedural law)
            else:
                if ref not in procedural_law:
                    procedural_law.append(ref)
    
    # Extract fiqh principles - گسترده‌تر
    fiqh_patterns = [
        r'(اصاله\s+الصحه)',
        r'(اصل\s+صحت)',
        r'(قاعده\s+لاضرر)',
        r'(قاعده\s+لاضرار)',
        r'(قاعده\s+ید)',
        r'(قاعده\s+تسلیط)',
        r'(قاعده\s+ضمان)',
        r'(قاعده\s+حیازت)',
        r'(قاعده\s+اتلاف)',
        r'(قاعده\s+غرور)',
        r'(اصل\s+برائت)',
        r'(اصل\s+احترام)',
        r'(اصل\s+حریت)',
        r'(استصحاب)',
    ]
    
    for pattern in fiqh_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if match not in fiqh_principles:
                fiqh_principles.append(match)
    
    return substantive_law, procedural_law, fiqh_principles


def extract_first_instance_info(text: str) -> Dict[str, Any]:
    """
    Extract information about the first instance court decision.
    """
    info = {
        "decision": None,
        "reasoning_keywords": [],
    }
    
    # Try to find decision
    decision_patterns = [
        r'(وارد\s+دانستن\s+اعتراض[^\.]+)',
        r'(حکم\s+به\s+رفع\s+توقیف[^\.]+)',
        r'(رد\s+دعوای[^\.]+)',
    ]
    
    for pattern in decision_patterns:
        match = re.search(pattern, text)
        if match:
            info["decision"] = match.group(1).strip()
            break
    
    # Extract reasoning keywords
    reasoning_phrases = [
        "تحقق عقد بیع",
        "سبب تملیک",
        "اصاله الصحه",
        "اصل صحت",
        "صوری بودن معامله",
        "عدم انتقال مالکیت",
        "مالک واقعی",
    ]
    
    for phrase in reasoning_phrases:
        if phrase in text:
            info["reasoning_keywords"].append(phrase)
    
    return info


def extract_appeal_court_info(text: str) -> Dict[str, Any]:
    """
    Extract appeal court (تجدیدنظر) reasoning and decision.
    """
    info = {
        "result": None,
        "key_points": [],
    }
    
    # Detect appeal result
    result_patterns = [
        (r'رد\s+تجدیدنظرخواهی\s+و\s+تأیید\s+دادنامه\s+بدوی', 'رد تجدیدنظرخواهی و تأیید دادنامه بدوی'),
        (r'تأیید\s+رأی\s+بدوی', 'تأیید رأی بدوی'),
        (r'نقض\s+رأی\s+بدوی', 'نقض رأی بدوی'),
    ]
    
    for pattern, result in result_patterns:
        if re.search(pattern, text):
            info["result"] = result
            break
    
    # Extract key points
    key_phrases = [
        "عدم ایراد مؤثر",
        "ایراد وارد نیست",
        "لایحه تجدیدنظرخواهی",
        "ماده 348",
        "ماده 358",
        "آیین دادرسی مدنی",
    ]
    
    for phrase in key_phrases:
        if phrase in text:
            info["key_points"].append(phrase)
    
    return info


def detect_claims(text: str) -> Dict[str, Any]:
    """
    Detect main claims and execution file references.
    """
    claims = {
        "main": [],
        "execution_files": [],
    }
    
    # Main claims - گسترده‌تر برای انواع دعاوی
    claim_patterns = [
        # دعاوی اعتراض و توقیف
        "اعتراض ثالث به عملیات اجرایی",
        "توقیف عملیات اجرایی",
        "رفع توقیف",
        
        # دعاوی املاک و معاملات
        "الزام به تنظیم سند",
        "الزام به انتقال سند",
        "خلع ید",
        "تخلیه",
        "تحویل عین مبیع",
        "ابطال سند",
        "ابطال عقد",
        "فسخ معامله",
        "فسخ قرارداد",
        "اعلام بطلان",
        
        # دعاوی مطالبه
        "مطالبه وجه",
        "مطالبه خسارت",
        "مطالبه خسارت تأخیر تأدیه",
        "مطالبه وجه چک",
        "مطالبه نفقه",
        "مطالبه مهریه",
        "مطالبه اجرت المثل",
        "مطالبه حق مسلم",
        "مطالبه مزد",
        "مطالبه حق سنوات",
        
        # دعاوی خانوادگی
        "طلاق",
        "حضانت فرزند",
        "ملاقات با فرزند",
        "نفقه",
        "مهریه",
        
        # دعاوی ارث و وصیت
        "تقسیم ترکه",
        "تعیین سهم الارث",
        "صدور گواهی حصر وراثت",
        "انحصار وراثت",
        "افتتاح وصیت‌نامه",
        "ابطال وصیت‌نامه",
        
        # دعاوی شرکتی و تجاری
        "انحلال شرکت",
        "تعیین مدیر",
        "ابطال مصوبات",
        "ورشکستگی",
        
        # دعاوی دیه و قصاص
        "مطالبه دیه",
        "قصاص",
        "ارش",
        
        # دعاوی کیفری
        "کلاهبرداری",
        "خیانت در امانت",
        "تصرف عدوانی",
        
        # دعاوی اداری و مالیاتی
        "اعتراض به رأی مالیاتی",
        "ابطال رأی هیأت حل اختلاف",
        
        # دعاوی کارگری
        "اعتراض به اخراج",
        "بازگشت به کار",
    ]
    
    for claim in claim_patterns:
        if claim in text:
            if claim not in claims["main"]:
                claims["main"].append(claim)
    
    # Additional regex-based patterns for variable claims
    # Pattern: الزام به [something]
    elzam_pattern = r'الزام\s+به\s+([^\.\،\n]{5,40})'
    matches = re.findall(elzam_pattern, text)
    for match in matches:
        claim = f"الزام به {match.strip()}"
        if claim not in claims["main"] and len(claims["main"]) < 10:
            claims["main"].append(claim)
    
    # Pattern: مطالبه [something]
    motalebe_pattern = r'مطالبه\s+([^\.\،\n]{5,40})'
    matches = re.findall(motalebe_pattern, text)
    for match in matches:
        claim = f"مطالبه {match.strip()}"
        if claim not in claims["main"] and len(claims["main"]) < 10:
            claims["main"].append(claim)
    
    # Execution files: پرونده شماره ... شعبه ...
    file_pattern = r'پرونده\s+(?:شماره|کلاسه)\s+([^\s]+)\s+[^\.]{0,50}شعبه\s+([^\s\.]+)'
    matches = re.findall(file_pattern, text)
    
    for case_num, branch in matches:
        file_ref = f"پرونده {case_num} شعبه {branch}"
        if file_ref not in claims["execution_files"]:
            claims["execution_files"].append(file_ref)
    
    return claims


def build_tags(text: str) -> List[str]:
    """
    Build system tags for categorization.
    
    Returns a list of relevant tags extracted from the text.
    Comprehensive coverage of 150+ legal concepts.
    """
    tags: List[Any] = []
    # Domain tags - COMPREHENSIVE LEGAL TAXONOMY (150+ patterns)
    tag_patterns = {
        # =====================================================================
        # دعاوی اعتراض و توقیف - Objection & Seizure
        # =====================================================================
        "اعتراض ثالث اجرایی": r'اعتراض\s+ثالث',
        "اعتراض ثالث اصلی": r'اعتراض\s+ثالث\s+اصلی',
        "اعتراض ثالث طاری": r'اعتراض\s+ثالث\s+طاری',
        "رفع توقیف": r'رفع\s+توقیف',
        "توقیف اموال": r'توقیف\s+(?:اموال|ملک|حساب)',
        "اجرای احکام مدنی": r'اجرای?\s+احکام',
        "عملیات اجرایی": r'عملیات\s+اجرایی',
        
        # =====================================================================
        # دعاوی املاک - Property
        # =====================================================================
        "الزام به تنظیم سند": r'الزام\s+به\s+تنظیم\s+سند',
        "الزام به انتقال سند": r'الزام\s+به\s+انتقال',
        "خلع ید": r'خلع\s+ید',
        "تخلیه": r'\bتخلیه\b',
        "تصرف عدوانی": r'تصرف\s+عدوانی',
        "مزاحمت": r'\bمزاحمت\b',
        "ممانعت از حق": r'ممانعت\s+از\s+حق',
        "ابطال سند": r'ابطال\s+سند',
        "ابطال معامله": r'ابطال\s+(?:معامله|عقد)',
        "فسخ معامله": r'فسخ\s+(?:معامله|قرارداد)',
        "تنفیذ معامله": r'تنفیذ\s+(?:معامله|قرارداد)',
        "صوری بودن معامله": r'صوری\s+بودن',
        "اثبات مالکیت": r'اثبات\s+مالکیت',
        "افراز": r'\bافراز\b',
        "تفکیک": r'\bتفکیک\b',
        "فروش مال مشاع": r'فروش\s+مال\s+مشاع',
        
        # =====================================================================
        # عقود و قراردادها - Contracts
        # =====================================================================
        "بیع": r'\bبیع\b',
        "اجاره": r'\bاجاره\b',
        "صلح": r'\bصلح\b',
        "هبه": r'\bهبه\b',
        "وکالت": r'\bوکالت\b',
        "ودیعه": r'\bودیعه\b',
        "عاریه": r'\bعاریه\b',
        "قرض": r'\bقرض\b',
        "مضاربه": r'\bمضاربه\b',
        "رهن": r'\bرهن\b',
        "ضمان": r'\bضمان\b',
        "کفالت": r'\bکفالت\b',
        "حواله": r'\bحواله\b',
        
        # =====================================================================
        # خیارات - Options
        # =====================================================================
        "خیار غبن": r'خیار\s+غبن',
        "خیار عیب": r'خیار\s+عیب',
        "خیار تدلیس": r'خیار\s+تدلیس',
        "خیار شرط": r'خیار\s+شرط',
        "خیار رؤیت": r'خیار\s+رؤیت',
        
        # =====================================================================
        # عیوب اراده - Defects of Will
        # =====================================================================
        "غبن فاحش": r'غبن\s+فاحش',
        "غبن افحش": r'غبن\s+افحش',
        "اشتباه": r'\bاشتباه\b',
        "اکراه": r'\bاکراه\b',
        "تدلیس": r'\bتدلیس\b',
        "معامله فضولی": r'معامله\s+فضولی',
        
        # =====================================================================
        # دعاوی مطالبه - Claims
        # =====================================================================
        "مطالبه وجه": r'مطالبه\s+وجه',
        "مطالبه خسارت": r'مطالبه\s+خسارت',
        "خسارت تأخیر تأدیه": r'خسارت\s+تأخیر',
        "مطالبه نفقه": r'مطالبه\s+نفقه',
        "مطالبه مهریه": r'مطالبه\s+مهریه',
        "مطالبه مزد": r'مطالبه\s+مزد',
        "مطالبه اجرت المثل": r'مطالبه\s+اجرت\s*المثل',
        "مطالبه دیه": r'مطالبه\s+دیه',
        "استرداد": r'\bاسترداد\b',
        
        # =====================================================================
        # دعاوی خانوادگی - Family
        # =====================================================================
        "طلاق": r'\bطلاق\b',
        "طلاق توافقی": r'طلاق\s+توافقی',
        "عسر و حرج": r'عسر\s+و\s+حرج',
        "حضانت": r'\bحضانت\b',
        "ملاقات فرزند": r'ملاقات\s+(?:فرزند|طفل)',
        "نفقه": r'\bنفقه\b',
        "تمکین": r'\bتمکین\b',
        "نشوز": r'\bنشوز\b',
        "مهریه": r'\bمهریه\b',
        "جهیزیه": r'\bجهیزیه\b',
        "اثبات نسب": r'اثبات\s+نسب',
        "نفی ولد": r'نفی\s+ولد',
        "اجرت المثل ایام زوجیت": r'اجرت\s*المثل\s+ایام',
        
        # =====================================================================
        # دعاوی ارث - Inheritance
        # =====================================================================
        "ارث و میراث": r'\bارث\b|\bمیراث\b',
        "انحصار وراثت": r'انحصار\s+وراثت|حصر\s+وراثت',
        "تقسیم ترکه": r'تقسیم\s+ترکه',
        "وصیت": r'\bوصیت',
        "وصیت‌نامه": r'وصیت\s*نامه',
        "ثلث ترکه": r'ثلث\s+ترکه',
        
        # =====================================================================
        # دعاوی تجاری - Commercial
        # =====================================================================
        "چک": r'\bچک\b',
        "چک بلامحل": r'چک\s+بلامحل',
        "سفته": r'\bسفته\b',
        "برات": r'\bبرات\b',
        "ظهرنویسی": r'\bظهرنویسی\b',
        "واخواست": r'\bواخواست\b',
        "شرکت تجاری": r'شرکت\s+(?:سهامی|تضامنی|تجاری)',
        "انحلال شرکت": r'انحلال\s+شرکت',
        "ورشکستگی": r'ورشکستگی',
        
        # =====================================================================
        # دعاوی کیفری - Criminal
        # =====================================================================
        "کلاهبرداری": r'کلاهبرداری',
        "خیانت در امانت": r'خیانت\s+در\s+امانت',
        "جعل": r'\bجعل\b',
        "استفاده از سند مجعول": r'استفاده\s+از\s+سند\s+مجعول',
        "سرقت": r'\bسرقت\b',
        "ضرب و جرح": r'ضرب\s+و\s+جرح',
        "قتل": r'\bقتل\b',
        "توهین": r'\bتوهین\b',
        "افترا": r'\bافترا\b',
        "ترک انفاق": r'ترک\s+انفاق',
        
        # =====================================================================
        # دیات و قصاص - Diyat
        # =====================================================================
        "دیه": r'\bدیه\b',
        "دیه کامل": r'دیه\s+کامل',
        "قصاص": r'\bقصاص\b',
        "ارش": r'\bارش\b',
        "حکومت": r'\bحکومت\b',
        
        # =====================================================================
        # دعاوی کار - Labor
        # =====================================================================
        "کار و کارگر": r'کار\s+و\s+کارگر|روابط\s+کار',
        "اخراج": r'\bاخراج\b',
        "بازگشت به کار": r'بازگشت\s+به\s+کار',
        "حق سنوات": r'حق\s+سنوات',
        "سنوات خدمت": r'سنوات\s+خدمت',
        "بیمه بیکاری": r'بیمه\s+بیکاری',
        "تأمین اجتماعی": r'تأمین\s+اجتماعی',
        "هیأت تشخیص": r'هیأت\s+تشخیص',
        "هیأت حل اختلاف کار": r'هیأت\s+حل\s+اختلاف',
        
        # =====================================================================
        # اصول و قواعد فقهی - Fiqh
        # =====================================================================
        "اصاله الصحه": r'اصاله\s+الصحه|اصل\s+صحت',
        "اصل لزوم": r'اصل\s+لزوم|اصاله\s+اللزوم',
        "اصل برائت": r'اصل\s+برائت',
        "استصحاب": r'\bاستصحاب\b',
        "قاعده لاضرر": r'قاعده\s+لاضرر|لاضرر\s+و\s+لاضرار',
        "قاعده ید": r'قاعده\s+ید',
        "قاعده تسلیط": r'قاعده\s+تسلیط',
        "قاعده اتلاف": r'قاعده\s+اتلاف',
        "قاعده تسبیب": r'قاعده\s+تسبیب',
        "قاعده غرور": r'قاعده\s+غرور',
        "قاعده احسان": r'قاعده\s+احسان',
        "قاعده درء": r'قاعده\s+درء',
        
        # =====================================================================
        # آیین دادرسی - Procedure
        # =====================================================================
        "واخواهی": r'\bواخواهی\b',
        "تجدیدنظرخواهی": r'تجدیدنظرخواهی',
        "فرجام‌خواهی": r'فرجام\s*خواهی',
        "اعاده دادرسی": r'اعاده\s+دادرسی',
        "قرار تأمین خواسته": r'قرار\s+تأمین\s+خواسته',
        "دستور موقت": r'دستور\s+موقت',
        "ابلاغ": r'\bابلاغ\b',
        
        # =====================================================================
        # نتایج رسیدگی - Outcomes
        # =====================================================================
        "تجدیدنظرخواهی مردود": r'رد\s+تجدیدنظرخواهی|تجدیدنظرخواهی\s+مردود',
        "تأیید رأی بدوی": r'تأیید\s+(?:رأی|دادنامه)\s+بدوی',
        "نقض رأی بدوی": r'نقض\s+(?:رأی|دادنامه)\s+بدوی',
        "رد دعوا": r'رد\s+دعوا|رد\s+خواسته',
        "وارد دانستن دعوا": r'وارد\s+دانستن|دعوا\s+وارد',
        "محکومیت": r'\bمحکومیت\b',
        "برائت": r'\bبرائت\b',
        "قرار رد دعوا": r'قرار\s+رد\s+دعوا',
        "قرار عدم استماع": r'قرار\s+عدم\s+استماع',
        "قرار سقوط دعوا": r'قرار\s+سقوط',
        
        # =====================================================================
        # مواد مهم قانونی - Key Articles
        # =====================================================================
        "ماده 10 قانون مدنی": r'ماده\s+(?:۱۰|10)\s+(?:قانون\s+)?مدنی',
        "ماده 190 قانون مدنی": r'ماده\s+(?:۱۹۰|190)',
        "ماده 219 قانون مدنی": r'ماده\s+(?:۲۱۹|219)',
        "ماده 339 قانون مدنی": r'ماده\s+(?:۳۳۹|339)',
        "ماده 348 آیین دادرسی": r'ماده\s+(?:۳۴۸|348)',
        "ماده 358 آیین دادرسی": r'ماده\s+(?:۳۵۸|358)',
        "ماده 515 آیین دادرسی": r'ماده\s+(?:۵۱۵|515)',
        "ماده 519 آیین دادرسی": r'ماده\s+(?:۵۱۹|519)',
        
        # =====================================================================
        # اداری و مالیاتی - Administrative
        # =====================================================================
        "دیوان عدالت اداری": r'دیوان\s+عدالت\s+اداری',
        "مالیات": r'\bمالیات',
        "عوارض": r'\bعوارض\b',
        "کمیسیون ماده 100": r'کمیسیون\s+ماده\s+(?:۱۰۰|100)',
        "تخلفات ساختمانی": r'تخلفات\s+ساختمانی',
        
        # =====================================================================
        # تأمینات - Securities
        # =====================================================================
        "وثیقه": r'\bوثیقه\b',
        "ضمانت‌نامه بانکی": r'ضمانت\s*نامه\s+بانکی',
        
        # =====================================================================
        # بیمه - Insurance
        # =====================================================================
        "بیمه": r'\bبیمه\b',
        "بیمه شخص ثالث": r'بیمه\s+شخص\s+ثالث',
        "خسارت بیمه‌ای": r'خسارت\s+بیمه',
    }
    
    for tag, pattern in tag_patterns.items():
        if re.search(pattern, text):
            tags.append(tag)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags: List[Any] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def detect_procedure_stage(text: str) -> str:
    """
    Detect the procedural stage of the case.
    """
    if 'تجدیدنظر' in text:
        return "تجدیدنظر"
    elif 'بدوی' in text or 'نخستین' in text:
        return "بدوی"
    elif 'دیوان عالی' in text:
        return "دیوان عالی کشور"
    
    logger.warning("Could not detect procedure_stage from text")
    return None

def split_verdict_sections(text: str) -> Dict[str, str]:
    """
    Split verdict into semantic sections: Summary (Ghardeshkar) and Verdict (Raye Dadgah).
    """
    sections = {
        "summary": None,
        "verdict": None
    }
    
    # Normalize newlines for easier splitting
    text_clean = text.replace('\r\n', '\n')
    
    # Detect "Raye Dadgah" (The most critical split point)
    # Patterns: "رأی دادگاه", "رأی قاضی", "نظریه دادگاه"
    verdict_start_patterns = [
        r'\n\s*(?:رأی|رای)\s+دادگاه\s*[:\n]',
        r'\n\s*نظریه\s+دادگاه\s*[:\n]',
        r'\n\s*رأی\s+قاضی\s*[:\n]',
        r'\n\s*ختم\s+رسیدگی\s+را\s+اعلام\s+و\s+.*?\s+مبادرت\s+به\s+صدور\s+رأی\s+.*?\s+می\s*نماید',
    ]
    
    split_index = -1
    for pat in verdict_start_patterns:
        # Find all matches
        for m in re.finditer(pat, text_clean):
            idx = m.start()
            # Heuristic: The actual Raye Dadgah is almost never in the first 25% of the text.
            if idx < len(text_clean) * 0.25:
                continue
            
            # Check if match is inside quotes
            before = text_clean[:idx]
            in_guillemets = before.count("«") > before.count("»")
            in_quotes = before.count('"') % 2 != 0
            if in_guillemets or in_quotes:
                continue
            
            split_index = idx
            break
        if split_index != -1:
            break
    
    if split_index != -1:
        sections["summary"] = text_clean[:split_index].strip()
        sections["verdict"] = text_clean[split_index:].strip()
    else:
        logger.warning("SECTION_SPLITTING_WARNING: Could not find explicit verdict header. File flagged for manual review.")
        sections["summary"] = text_clean
    
    return sections


def extract_dates(text: str) -> Dict[str, str]:
    """
    Extract and standardize dates (Decision Date, Finality Date) with robust Persian/Jalali support.
    
    LEGAL INTEGRITY FIX: Proper Jalali date parsing instead of datetime.now() fallback.
    """
    dates = {
        "decision_date": None,
        "finality_date": None
    }
    
    def parse_persian_date(date_str: str) -> Optional[str]:
        """
        Parse Persian/Jalali date string to standardized format.
        
        Handles formats like:
        - 1403/05/15
        - ۱۴۰۳/۰۵/۱۵  
        - 15 مرداد 1403
        - پانزدهم مرداد یکهزار و چهارصد و سه
        """
        if not date_str:
            return None
            
        # Normalize Persian digits first
        date_normalized = persian_digits_to_english(date_str.strip())
        
        # Pattern 1: YYYY/MM/DD or YY/MM/DD
        numeric_pattern = r'(\d{2,4})[/\-](\d{1,2})[/\-](\d{1,2})'
        match = re.search(numeric_pattern, date_normalized)
        if match:
            year, month, day = match.groups()
            year_int = int(year)
            month_int = int(month)
            day_int = int(day)
            
            # Normalize 2-digit years
            if year_int < 100:
                if year_int <= 50:
                    year_int += 1400
                else:
                    year_int += 1300
            
            if 1300 <= year_int <= 1500 and 1 <= month_int <= 12 and 1 <= day_int <= 31:
                return f"{year_int:04d}/{month_int:02d}/{day_int:02d}"
        
        # Pattern 2: DD MonthName YYYY (Persian month names)
        persian_months = {
            'فروردین': '01', 'اردیبهشت': '02', 'خرداد': '03',
            'تیر': '04', 'مرداد': '05', 'شهریور': '06',
            'مهر': '07', 'آبان': '08', 'آذر': '09',
            'دی': '10', 'بهمن': '11', 'اسفند': '12'
        }
        
        for month_name, month_num in persian_months.items():
            pattern = rf'(\d{{1,2}})\s+{month_name}\s+(\d{{2,4}})'
            match = re.search(pattern, date_normalized)
            if match:
                day, year = match.groups()
                day_int = int(day)
                year_int = int(year)
                
                if year_int < 100:
                    if year_int <= 50:
                        year_int += 1400
                    else:
                        year_int += 1300
                
                if 1300 <= year_int <= 1500 and 1 <= day_int <= 31:
                    return f"{year_int:04d}/{month_num}/{day_int:02d}"
        
        # Pattern 3: Written numbers (basic support)
        # This is complex, so we'll handle the most common cases
        written_numbers = {
            'یک': '1', 'دو': '2', 'سه': '3', 'چهار': '4', 'پنج': '5',
            'شش': '6', 'هفت': '7', 'هشت': '8', 'نه': '9', 'ده': '10',
            'یازده': '11', 'دوازده': '12', 'سیزده': '13', 'چهارده': '14', 'پانزده': '15',
            'شانزده': '16', 'هفده': '17', 'هجده': '18', 'نوزده': '19', 'بیست': '20',
            'بیست و یک': '21', 'بیست و دو': '22', 'بیست و سه': '23', 'بیست و چهار': '24',
            'بیست و پنج': '25', 'بیست و شش': '26', 'بیست و هفت': '27', 'بیست و هشت': '28',
            'بیست و نه': '29', 'سی': '30', 'سی و یک': '31'
        }
        
        # Try to convert written day numbers
        for written, numeric in written_numbers.items():
            for month_name, month_num in persian_months.items():
                pattern = rf'{written}\s+{month_name}\s+.*?(\d{{2,4}})'
                match = re.search(pattern, date_normalized)
                if match:
                    year = match.group(1)
                    year_int = int(year)
                    day_int = int(numeric)
                    
                    if year_int < 100:
                        if year_int <= 50:
                            year_int += 1400
                        else:
                            year_int += 1300
                    
                    if 1300 <= year_int <= 1500 and 1 <= day_int <= 31:
                        return f"{year_int:04d}/{month_num}/{day_int:02d}"
        
        # If no pattern matches, log warning and return None (no fallback to current date)
        logger.warning(f"TEMPORAL_PARSING_WARNING: Could not parse Persian date: '{date_str}'")
        return None
    
    # 1. Decision Date Context
    decision_context_patterns = [
        r'(?:صادر\s+شده\s+در\s+تاریخ|مورخ)\s*[:\s]\s*([^،\.\n]{5,30})',
        r'رأی\s+مورخ\s*([^،\.\n]{5,30})',
        r'دادنامه\s+شماره\s+\d+\s+مورخ\s*([^،\.\n]{5,30})',
    ]
    for pattern in decision_context_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            d = parse_persian_date(m)
            if d:
                dates["decision_date"] = d
                break
        if dates["decision_date"]:
            break
            
    # Fallback to general date patterns for decision_date if still None
    if not dates["decision_date"]:
        general_patterns = [
            r'(?:تاریخ|مورخ)\s*[:\s]\s*([^،\.\n]{5,30})',
            r'در\s+تاریخ\s+([^،\.\n]{5,30})',
            r'به\s+تاریخ\s+([^،\.\n]{5,30})',
        ]
        for pattern in general_patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                d = parse_persian_date(m)
                if d:
                    dates["decision_date"] = d
                    break
            if dates["decision_date"]:
                break
                
    # 2. Finality Date Context
    finality_context_patterns = [
        r'(?:تأیید\s+و\s+)?قطعی\s+در\s+تاریخ\s+([^،\.\n]{5,30})',
        r'قطعیت\s+در\s+تاریخ\s+([^،\.\n]{5,30})',
        r'مورخ\s+([^،\.\n]{5,30})\s+به\s+قطعیت\s+رسید',
    ]
    for pattern in finality_context_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            d = parse_persian_date(m)
            if d:
                dates["finality_date"] = d
                break
        if dates["finality_date"]:
            break
            
    return dates
# ============================================================================
# Main Parser
# ============================================================================

def parse_verdict_text(raw_text: str) -> Dict[str, Any]:
    """
    Parse raw verdict text into structured dictionary.
    
    Args:
        raw_text: Raw Persian verdict text
    
    Returns:
        Dictionary with structured verdict information (JSON-compatible)
    
    Structure:
        {
          "case_meta": {...},
          "parties": {...},
          "claims": {...},
          "first_instance_summary": {...},
          "appeal_court_reasoning": {...},
          "legal_references": {...},
          "final_decision": {...},
          "system_tags": [...]
        }
    """
    # Normalize text
    text = normalize_text(raw_text)
    
    # Extract court details (Phase 3)
    court_details = extract_court_details(text)
    court_level = court_details["level"]
    if court_details["branch"]:
        court_level = f"{court_level} شعبه {court_details['branch']}" if court_level else f"شعبه {court_details['branch']}"
    
    # Detect finality
    is_final, finality_basis = detect_finality(text)
    
    # Detect case type
    case_type = detect_case_type(text)
    
    # Detect procedure stage
    procedure_stage = detect_procedure_stage(text)
    
    # Extract parties
    parties = extract_parties(text)
    
    # Extract legal references
    substantive, procedural, fiqh = extract_legal_articles(text)
    
    # Extract first instance info
    first_instance = extract_first_instance_info(text)
    
    # Extract appeal court info
    appeal_info = extract_appeal_court_info(text)
    
    # Detect claims
    claims = detect_claims(text)
    
    # Build tags
    tags = build_tags(text)
    
    # Split sections (Phase 3)
    sections = split_verdict_sections(text)
    
    # ========================================================================
    # NER Entity Extraction (Enterprise NER Subsystem Integration)
    # ========================================================================
    entities = {
        "persons": [],
        "organizations": [],
        "courts": [],
        "laws": [],
        "topics": []
    }
    
    if HAS_NER and extract_ner_entities is not None:
        try:
            entities = extract_ner_entities(text)
            logger.debug(
                f"NER_PIPELINE: Extracted entities - "
                f"persons={len(entities.get('persons', []))}, "
                f"organizations={len(entities.get('organizations', []))}, "
                f"courts={len(entities.get('courts', []))}, "
                f"laws={len(entities.get('laws', []))}, "
                f"topics={len(entities.get('topics', []))}"
            )
        except Exception as e:
            logger.critical(f"NER extraction failed under strict execution: {e}")
            raise RuntimeError(f"NER extraction failed: {e}") from e
    
    # Extract dates (Phase 3)
    dates = extract_dates(text)
    
    # Detect objection acceptance (Improved Logic)
    # Look for explicit acceptance of objection
    objection_accepted = False
    if "وارد" in text or "ورود" in text:
        # Strict pattern: objection ... accepted
        # Examples: "اعتراض وارد است", "تجدیدنظرخواهی را وارد دانسته", "حکم به ورود اعتراض"
        acceptance_patterns = [
            r'(?:اعتراض|تجدیدنظرخواهی|دعوی|خواسته).*?(?:را\s+)?وارد\s+(?:دانست|می\s*دانیم|است|تشخیص)',
            r'وارد\s+بودن\s+(?:اعتراض|تجدیدنظرخواهی)',
            r'حکم\s+به\s+ورود\s+(?:اعتراض|تجدیدنظرخواهی)',
        ]
        for pat in acceptance_patterns:
            if re.search(pat, text):
                objection_accepted = True
                break

    # Calculate Parsing Quality / Confidence (Strict Hardened Heuristic)
    confidence_score = 1.0
    quality_metrics = {
        "court_level_found": court_level is not None,
        "case_type_found": case_type is not None,
        "parties_found": len(parties.get("respondents", [])) > 0 or parties.get("third_party_objector") is not None,
        "articles_found": len(substantive) + len(procedural) > 0,
        "claims_found": len(claims.get("main", [])) > 0,
        "decision_date_found": dates["decision_date"] is not None,
        "verdict_section_found": sections["verdict"] is not None,
    }
    
    # Penalize for missing critical fields
    if not quality_metrics["court_level_found"]: confidence_score -= 0.2
    if not quality_metrics["case_type_found"]: confidence_score -= 0.2
    if not quality_metrics["parties_found"]: confidence_score -= 0.2
    if not quality_metrics["claims_found"]: confidence_score -= 0.1
    if not quality_metrics["decision_date_found"]: confidence_score -= 0.2
    if not quality_metrics["verdict_section_found"]: confidence_score -= 0.3
    
    # Contextual consistency checks
    if court_level and "دیوان" in court_level and not is_final:
        confidence_score -= 0.2
        
    if len(raw_text) < 150:
        confidence_score -= 0.4
        
    confidence_score = max(0.0, min(1.0, confidence_score))

    # Assemble final structure
    verdict_struct = {
        "case_meta": {
            "court_level": court_level,
            "procedure_stage": procedure_stage,
            "case_type": case_type,
            "is_final": is_final,
            "finality_basis": finality_basis,
            "branch_number": court_details["branch"],
            "city": court_details["city"],
            "province": court_details["province"],
            "decision_date": dates["decision_date"],
        },
        "parties": parties,
        "claims": claims,
        "first_instance_summary": first_instance,
        "appeal_court_reasoning": appeal_info,
        "sections": sections,  # Added Phase 3
        "legal_references": {
            "substantive_law": substantive,
            "procedural_law": procedural,
            "fiqh_principles": fiqh,
        },
        "final_decision": {
            "appeal_result": appeal_info.get("result"),
            "third_party_objection": "پذیرفته شده" if objection_accepted else "رد شده" if "وارد نیست" in text else None,
            "is_final": is_final,
        },
        "system_tags": tags,
        # Enterprise NER Subsystem entities
        "entities": entities,
        "_parsing_quality": {
            "confidence_score": confidence_score,
            "metrics": quality_metrics
        }
    }
    
    # Log structured event
    IngestionLogger.log_parsing_event(
        doc_id="text_snippet",  # We don't have doc_id here, maybe pass it or use hash?
        status="SUCCESS",
        metrics=quality_metrics,
        errors=[]
    )
    
    # Log quality report
    missing_fields = [k for k, v in quality_metrics.items() if not v]
    IngestionLogger.log_quality_report(
        doc_id="text_snippet",
        quality_score=confidence_score,
        missing_fields=missing_fields
    )
    
    return verdict_struct


def parse_verdict_file(path: str | Path) -> Dict[str, Any]:
    """
    Parse a verdict file (.txt) into structured dictionary.
    
    Args:
        path: Path to verdict text file (UTF-8 encoded)
    
    Returns:
        Dictionary with structured verdict information
    
    Raises:
        FileNotFoundError: If file doesn't exist
        UnicodeDecodeError: If file is not UTF-8
    """
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Verdict file not found: {path}")
    
    # Read file with UTF-8 encoding
    with open(path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    # Parse
    verdict_struct = parse_verdict_text(raw_text)
    
    # Add source metadata
    verdict_struct["_source"] = {
        "filename": path.name,
        "filepath": str(path.absolute()),
        "file_size_bytes": path.stat().st_size,
    }
    
    return verdict_struct


# ============================================================================
# Validation
# ============================================================================

def validate_verdict_struct(verdict_struct: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a verdict structure has required fields.
    
    Returns:
        (is_valid: bool, errors: List[str])
    """
    errors: List[Any] = []
    required_top_level = [
        "case_meta",
        "parties",
        "claims",
        "first_instance_summary",
        "appeal_court_reasoning",
        "legal_references",
        "final_decision",
        "system_tags",
    ]
    
    for field in required_top_level:
        if field not in verdict_struct:
            errors.append(f"Missing required field: {field}")
    
    # Check nested required fields
    if "case_meta" in verdict_struct:
        meta = verdict_struct["case_meta"]
        if "court_level" not in meta:
            errors.append("Missing case_meta.court_level")
    
    if "parties" in verdict_struct:
        parties = verdict_struct["parties"]
        required_party_fields = [
            "third_party_objector",
            "third_party_objector_attorney",
            "respondents",
            "respondents_attorneys",
        ]
        for field in required_party_fields:
            if field not in parties:
                errors.append(f"Missing parties.{field}")
    
    is_valid = len(errors) == 0
    return is_valid, errors


class MinimalVerdictParser:
    """Wrapper class for verdict parsing functions (Production Grade)"""
    
    def parse(self, text: str) -> Dict[str, Any]:
        """Parse verdict text and return structured data"""
        return parse_verdict_text(text)
    
    def parse_file(self, path: str) -> Dict[str, Any]:
        """Parse verdict file and return structured data"""
        return parse_verdict_file(path)
