"""
Legal Named Entity Recognition (NER) Engine
============================================
Enterprise-grade entity extraction for Persian legal texts.

This module provides a fully offline, rule-based NER engine designed for 
high-precision extraction of legal entities from Iranian judicial documents.

Entity Types Supported:
- Persons (خانم/آقای + name patterns)
- Organizations (شرکت، مؤسسه، بانک, etc.)
- Courts (دادگاه، شعبه، دیوان, etc.)
- Laws/Articles (ماده X قانون Y)
- Topics (legal issue categories)

Design Principles:
- Offline-first: Zero external network calls
- Deterministic: Same input → same output
- Configurable: Patterns can be extended
- Performance: < 30ms per chunk on average hardware
- Governed: Under MAHOUN governance kernel oversight

Usage:
    from mahoun.pipelines.ingestion.legal_ner import extract_entities, LegalNEREngine
    
    # Quick extraction
    entities = extract_entities("متن حقوقی فارسی")
    
    # Advanced usage with engine
    engine = LegalNEREngine()
    entities = engine.extract(text)

Output Contract:
    {
        "persons": [...],
        "organizations": [...],
        "courts": [...],
        "laws": [...],
        "topics": [...]
    }
"""

import re
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from .persian_normalizer import PersianLegalNormalizer

# Governance imports
try:
    from mahoun.core.governance.governance_context import GovernanceContext
    from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
    GOVERNANCE_AVAILABLE = True
except ImportError:
    GOVERNANCE_AVAILABLE = False
    GovernanceContext = None
    IngestionExecutionGate = None

logger = logging.getLogger(__name__)


def _trimmed_match_span(match: re.Match[str]) -> tuple[str, int, int]:
    raw_text = match.group(0)
    text = raw_text.strip()
    start = match.start() + len(raw_text) - len(raw_text.lstrip())
    return text, start, start + len(text)


# ============================================================================
# Entity Data Classes
# ============================================================================

@dataclass
class Entity:
    """Base entity class with common attributes"""
    text: str
    entity_type: str
    start: int = 0
    end: int = 0
    confidence: float = 1.0
    normalized: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PersonEntity(Entity):
    """Person entity with additional attributes"""
    title: Optional[str] = None  # خانم/آقای
    name: Optional[str] = None
    father_name: Optional[str] = None
    role: Optional[str] = None  # e.g., خواهان، خوانده، وکیل


@dataclass
class OrganizationEntity(Entity):
    """Organization entity"""
    org_type: Optional[str] = None  # شرکت، بانک، مؤسسه
    registration_id: Optional[str] = None


@dataclass
class CourtEntity(Entity):
    """Court entity with hierarchy info"""
    level: Optional[str] = None  # بدوی، تجدیدنظر، دیوان عالی
    branch: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None


@dataclass
class LawArticleEntity(Entity):
    """Law/Article reference entity"""
    article_number: Optional[str] = None
    law_name: Optional[str] = None
    clause: Optional[str] = None


@dataclass
class TopicEntity(Entity):
    """Legal topic/category entity"""
    category: Optional[str] = None
    parent_topic: Optional[str] = None


# ============================================================================
# Pattern Configuration
# ============================================================================

class NERPatternConfig:
    """
    Configurable NER patterns for Persian legal text.
    
    This class centralizes all regex patterns used for entity extraction,
    making them easily auditable and extendable by governance teams.
    """
    
    # ========================================================================
    # Person Patterns
    # ========================================================================
    
    # Main person pattern: (خانم|آقای) NAME فرزند FATHER
    PERSON_PATTERN = re.compile(
        r'(خانم|آقای|آقا)\s+([^،\.\n\r\t]+?)(?:\s*،?\s*)فرزند\s+([^،\.\n\r\t]+?)(?:\s|،|\.|\n|$)',
        re.UNICODE
    )
    
    # Person with national ID: ... کد ملی NUMBER
    PERSON_WITH_ID = re.compile(
        r'(خانم|آقای|آقا)\s+([^،\.\n]+?)\s+(?:با\s+)?کد\s+ملی\s+(\d+)',
        re.UNICODE
    )
    
    # Attorney pattern: با وکالت ...
    ATTORNEY_PATTERN = re.compile(
        r'با\s+وکالت\s+(خانم|آقای|آقا)\s+([^،\.\n]+?)(?:\s|،|\.|\n|$)',
        re.UNICODE
    )
    
    # ========================================================================
    # Organization Patterns
    # ========================================================================
    
    # Company patterns
    COMPANY_PATTERNS = [
        re.compile(
            r'شرکت\s+([^،\.\n]{3,50}?)'
            r'(?:\s+به\s+شماره\s+ثبت\s+(\d+))?'
            r'(?=[،\.\n]|$|\s+و\s+سازمان\b)',
            re.UNICODE,
        ),
        re.compile(r'مؤسسه\s+([^،\.\n]{3,50})', re.UNICODE),
        re.compile(
            r'سازمان\s+([^،\.\n]{3,50}?)'
            r'(?=[،\.\n]|$|\s+و\s+سازمان\b)',
            re.UNICODE,
        ),
    ]
    
    # Bank patterns
    BANK_PATTERN = re.compile(
        r'بانک\s+([^،\.\n]{2,60})',
        re.UNICODE
    )
    
    # Government org patterns
    GOV_ORG_PATTERNS = [
        re.compile(r'(وزارت\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(سازمان\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(اداره\s+(?:کل\s+)?[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(شهرداری\s+[^،\.\n]{3,30})', re.UNICODE),
    ]
    
    # Oil & Gas Industry patterns (برای دعاوی نفتی و گازی)
    OIL_GAS_PATTERNS = [
        re.compile(r'(شرکت\s+نفتی\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(شرکت\s+گازی\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(شرکت\s+پتروشیمی\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(شرکت\s+ملی\s+صنایع\s+نفت)', re.UNICODE),
        re.compile(r'(شرکت\s+ملی\s+گاز\s+ایران)', re.UNICODE),
        re.compile(r'(شرکت\s+نفت\s+و\s+گاز\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(پالایشگاه\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(نفت\s+و\s+گاز\s+[^،\.\n]{3,40})', re.UNICODE),
        re.compile(r'(صنایع\s+نفتی\s+[^،\.\n]{3,40})', re.UNICODE),
    ]
    
    # ========================================================================
    # Court Patterns
    # ========================================================================

    COURT_STOP = (
        r"(?=\s+(?:مورد\s+رسیدگی|رسیدگی|رأی|رای|حکم|دادخواست|ابلاغ)\b"
        r"|[،؛.\n]|$)"
    )
    
    # Main court patterns
    COURT_PATTERNS = [
        # شعبه X دادگاه Y شهرستان/شهر Z
        re.compile(
            r'شعبه\s+(\d+)\s+(دادگاه\s+[^،\.\n]+?)(?:\s+(?:شهرستان|شهر|استان)\s+([^،\.\n]+))?',
            re.UNICODE
        ),
        # دادگاه Y استان Z شعبه X
        re.compile(
            r'(دادگاه\s+[^،\.\n]+?)\s+(?:استان\s+([^،\.\n]+?))\s+شعبه\s+(\d+)',
            re.UNICODE
        ),
        # Simple court level patterns
        re.compile(
            r'(دادگاه\s+تجدیدنظر\s+استان\s+[^،؛.\n]+?)' + COURT_STOP,
            re.UNICODE
        ),
        re.compile(
            r'(دادگاه\s+عمومی\s+(?:حقوقی|جزایی|کیفری)\s+[^،؛.\n]+?)' + COURT_STOP,
            re.UNICODE
        ),
        re.compile(
            r'(دادگاه\s+کیفری\s+(?:یک|دو)\s+[^،؛.\n]+?)' + COURT_STOP,
            re.UNICODE
        ),
        re.compile(
            r'(دادگاه\s+انقلاب\s+[^،؛.\n]+?)' + COURT_STOP,
            re.UNICODE
        ),
        re.compile(r'(دیوان\s+عالی\s+کشور)', re.UNICODE),
        re.compile(r'(دیوان\s+عدالت\s+اداری)', re.UNICODE),
    ]
    
    # ========================================================================
    # Law/Article Patterns
    # ========================================================================
    
    # ماده NUMBER قانون LAW_NAME (PRECISION FIX: More restrictive pattern)
    LAW_ARTICLE_PATTERN = re.compile(
        r'ماده\s*\(?\s*(\d+)\s*\)?\s+(?:'
        r'(این قانون|قانون مذکور|قانون فوق)(?=\s|[:：،.\n]|$)'
        r'|قانون\s+([^،\.\n\r\t]{3,160}?)'
        r'(?=\s+(?:مصوب|سال|باشد|است|به|مکلف(?:ند)?|مشمول|شامل|حسب|مطابق|'
        r'ماده|تبصره)\b|\s+و\s+(?:ماده|اصلاح|نیروهای\s+مسلح)\b'
        r'|\s+و\s+در\s+چهارچوب\b'
        r'|\s+از\s+موانع\s+تعرفه\b|\s*[-:：،.\n]|$))',
        re.UNICODE
    )
    
    # Multiple articles: مواد X و Y و Z قانون ...
    MULTIPLE_ARTICLES_PATTERN = re.compile(
        r'مواد\s+([\d\s،وی]+)\s+قانون\s+([^،\.\n]{5,60})',
        re.UNICODE
    )
    
    # Bylaw pattern: آیین‌نامه ...
    BYLAW_PATTERN = re.compile(
        r'آیین[‌\s]?نامه\s+([^،\.\n]{5,60})',
        re.UNICODE
    )

    # ============================================================================
    # Legal Advisory Opinions Patterns (نظریات مشورتی)
    # ============================================================================

    # Legal advisory opinion number: نظریه شماره X/Y/Z
    OPINION_NUMBER_PATTERN = re.compile(
        r'نظریه\s+شماره\s+(\d+(?:/\d+)+)',
        re.UNICODE
    )

    # Case number: شماره پرونده X-Y/Z
    CASE_NUMBER_PATTERN = re.compile(
        r'شماره\s+پرونده\s+([\d-]+(?:[کجح]|\d)?)',
        re.UNICODE
    )

    # Court ruling number: رای وحدت رویه شماره X
    RULING_NUMBER_PATTERN = re.compile(
        r'(?:رای|قرار)\s+(?:وحدت\s+رویە|عدالت\s+اداری|دیوان\s+عالی\s+کشور)\s+شماره\s+(\d+)',
        re.UNICODE
    )

    # Legal concepts (مفاهیم حقوقی تخصصی)
    LEGAL_CONCEPT_PATTERNS = [
        re.compile(r'\b(?:ارتشاء|اختلاس|کلاهبرداری|جرایم\s+سازمان‌یافته)\b', re.UNICODE),
        re.compile(r'\b(?:مسئولیت\s+تضامنی|مرور\s+زمان|دیه)\b', re.UNICODE),
        re.compile(r'\b(?:خیار\s+شرط|بازداشت\s+موقت|قرار\s+تأمین)\b', re.UNICODE),
        re.compile(r'\b(?:کیفرخواست|جلب\s+دادرسی|منع\s+تعقیب)\b', re.UNICODE),
        re.compile(r'\b(?:موقوفی\s+تعقیب|ماده\s+\d+(?:\s+تبصره\s+\d+)?)\b', re.UNICODE),
    ]

    # Comprehensive law references (ارجاعات جامع قانونی)
    LAW_REFERENCE_PATTERNS = [
        # قانون مجازات اسلامی
        re.compile(r'(قانون\s+مجازات\s+اسلامی(?:\s*\(\s*اصلاحی\s+\d{4}\))?)', re.UNICODE),
        # قانون آیین دادرسی کیفری
        re.compile(r'(قانون\s+آیین\s+دادرسی\s+کیفری(?:\s*\(\s*اصلاحی\s+\d{4}\))?)', re.UNICODE),
        # قانون بودجه سال X
        re.compile(r'(قانون\s+بودجه\s+سال\s+\d{2,4}\s+کل\s+کشور)', re.UNICODE),
        # قانون احترام به آزادی‌های مشروع
        re.compile(r'(قانون\s+احترام\s+به\s+آزادی‌های\s+مشروع\s+و\s+حفظ\s+حقوق\s+شهروندی)', re.UNICODE),
        # سایر قوانین با ساختار استاندارد
        re.compile(r'قانون\s+([^،\.\n\r]{5,60}?)(?:\s+ماده\s+\d+|\s*$|\s+و\s+)', re.UNICODE),
        # آیین‌نامه‌های خاص
        re.compile(r'آیین\s*نامه\s+([^،\.\n\r]{5,60}?)(?:\s*$|\s+ماده\s+)', re.UNICODE),
        # بخشنامه‌ها
        re.compile(r'بخشنامه\s+([^،\.\n\r]{5,60}?)(?:\s*$|\s+ماده\s+)', re.UNICODE),
    ]
    
    # ========================================================================
    # Topic/Category Patterns - COMPREHENSIVE LEGAL TAXONOMY
    # ========================================================================
    
    # Legal topic keywords and categories - 25+ categories, 300+ keywords
    TOPIC_KEYWORDS = {
        # =====================================================================
        # حقوق مدنی - Civil Law
        # =====================================================================
        
        # Property/Real Estate - دعاوی ملکی
        'ملکی': [
            'خلع ید', 'تخلیه', 'تصرف عدوانی', 'الزام به تنظیم سند', 'ابطال سند',
            'افراز', 'تفکیک', 'فروش مال مشاع', 'مزاحمت', 'ممانعت از حق',
            'اثبات مالکیت', 'ابطال معامله', 'استرداد ملک', 'تحویل مبیع',
            'الزام به فک رهن', 'ابطال سند رهنی', 'تنفیذ معامله',
            'اعلام بطلان معامله', 'تأیید فسخ', 'اعلام فسخ',
        ],
        
        # Contracts - عقود و قراردادها
        'عقود': [
            # عقود معین
            'بیع', 'اجاره', 'صلح', 'هبه', 'وکالت', 'ودیعه', 'عاریه',
            'قرض', 'مضاربه', 'مزارعه', 'مساقات', 'جعاله', 'شرکت',
            'رهن', 'ضمان', 'حواله', 'کفالت',
            # مفاهیم قراردادی
            'ایجاب', 'قبول', 'عقد لازم', 'عقد جایز', 'عقد معلق', 'عقد منجز',
            'شرط ضمن عقد', 'شرط فعل', 'شرط نتیجه', 'شرط صفت',
            'خیار شرط', 'خیار مجلس', 'خیار حیوان', 'خیار رؤیت',
            'خیار غبن', 'خیار عیب', 'خیار تدلیس', 'خیار تبعض صفقه',
            'خیار تأخیر ثمن', 'خیار تخلف شرط', 'خیار تخلف وصف',
        ],
        
        # Contract Defects - عیوب اراده
        'عیوب_اراده': [
            'اشتباه', 'اکراه', 'تدلیس', 'غبن', 'غبن فاحش', 'غبن افحش',
            'عدم اهلیت', 'جنون', 'سفه', 'صغر', 'حجر',
            'معامله فضولی', 'معامله صوری', 'معامله به قصد فرار از دین',
        ],
        
        # Obligations - تعهدات
        'تعهدات': [
            'الزام به انجام تعهد', 'عدم انجام تعهد', 'تأخیر در انجام تعهد',
            'خسارت عدم انجام تعهد', 'خسارت تأخیر', 'وجه التزام',
            'تهاتر', 'ابراء', 'اقاله', 'تبدیل تعهد', 'انتقال دین', 'انتقال طلب',
        ],
        
        # Civil Liability - مسئولیت مدنی
        'مسئولیت_مدنی': [
            'اتلاف', 'تسبیب', 'غصب', 'استیفاء', 'ضمان قهری',
            'مسئولیت ناشی از فعل غیر', 'مسئولیت کارفرما', 'مسئولیت متصدی حمل',
            'خسارت مادی', 'خسارت معنوی', 'خسارت عدم النفع',
            'جبران خسارت', 'اعاده وضع به حال سابق',
        ],
        
        # =====================================================================
        # حقوق خانواده - Family Law
        # =====================================================================
        'خانواده': [
            # ازدواج
            'نکاح', 'عقد نکاح', 'نکاح دائم', 'نکاح موقت', 'متعه',
            'مهریه', 'مهرالمسمی', 'مهرالمثل', 'مهرالمتعه',
            'نفقه', 'نفقه زوجه', 'نفقه اقارب', 'تمکین', 'نشوز',
            # طلاق
            'طلاق', 'طلاق رجعی', 'طلاق بائن', 'طلاق خلع', 'طلاق مبارات',
            'طلاق توافقی', 'عسر و حرج', 'عدم پرداخت نفقه',
            # فرزندان
            'حضانت', 'ملاقات فرزند', 'ولایت', 'قیمومت', 'نسب', 'اثبات نسب',
            'نفی ولد', 'فرزندخواندگی', 'سرپرستی',
            # سایر
            'اجرت المثل ایام زوجیت', 'جهیزیه', 'استرداد جهیزیه',
        ],
        
        # =====================================================================
        # ارث و وصیت - Inheritance
        # =====================================================================
        'ارث': [
            'انحصار وراثت', 'گواهی حصر وراثت', 'تقسیم ترکه', 'ترکه',
            'سهم الارث', 'فرض', 'قرابت', 'ارث بری', 'محرومیت از ارث',
            'حاجب', 'محجوب', 'عول', 'تعصیب',
            # طبقات ارث
            'طبقه اول ارث', 'طبقه دوم ارث', 'طبقه سوم ارث',
            # وصیت
            'وصیت', 'وصیت‌نامه', 'وصیت تملیکی', 'وصیت عهدی',
            'موصی', 'موصی له', 'موصی به', 'وصی', 'ثلث ترکه',
        ],
        
        # =====================================================================
        # حقوق تجارت - Commercial Law
        # =====================================================================
        'تجاری': [
            # اسناد تجاری
            'چک', 'سفته', 'برات', 'ظهرنویسی', 'ضمانت', 'واخواست',
            'چک بلامحل', 'چک برگشتی', 'صدور چک بلامحل',
            # شرکت‌ها
            'شرکت سهامی', 'شرکت با مسئولیت محدود', 'شرکت تضامنی',
            'انحلال شرکت', 'تصفیه شرکت', 'ورشکستگی', 'اعلام ورشکستگی',
            'مدیر تصفیه', 'هیأت مدیره', 'مجمع عمومی',
            # تجار
            'تاجر', 'دفاتر تجاری', 'اعمال تجاری',
        ],
        
        # =====================================================================
        # حقوق کیفری - Criminal Law
        # =====================================================================
        'کیفری': [
            # جرائم علیه اموال
            'سرقت', 'سرقت تعزیری', 'سرقت حدی', 'کلاهبرداری', 'خیانت در امانت',
            'تحصیل مال نامشروع', 'پولشویی', 'اختلاس', 'ارتشاء', 'رشوه',
            # جرائم علیه اشخاص
            'قتل', 'قتل عمد', 'قتل شبه عمد', 'قتل خطای محض',
            'ضرب و جرح', 'ایراد ضرب عمدی', 'ایراد جرح',
            # جرائم علیه امنیت
            'جعل', 'استفاده از سند مجعول', 'جعل امضا',
            'توهین', 'افترا', 'نشر اکاذیب', 'تهدید',
            # سایر جرائم
            'ترک انفاق', 'رابطه نامشروع', 'تصرف عدوانی کیفری',
        ],
        
        # Punishments - مجازات‌ها
        'مجازات': [
            'حد', 'قصاص', 'دیه', 'تعزیر', 'مجازات بازدارنده',
            'حبس', 'جزای نقدی', 'شلاق', 'محرومیت از حقوق اجتماعی',
            'تعلیق مجازات', 'تخفیف مجازات', 'تبدیل مجازات',
            'آزادی مشروط', 'عفو',
        ],
        
        # Diyat - دیات
        'دیات': [
            'دیه', 'دیه کامل', 'دیه نفس', 'ارش', 'حکومت',
            'دیه اعضا', 'دیه منافع', 'دیه جراحات',
            'عاقله', 'بیت المال',
        ],
        
        # =====================================================================
        # حقوق کار - Labor Law
        # =====================================================================
        'کار': [
            'قرارداد کار', 'رابطه کارگری', 'کارگر', 'کارفرما',
            'اخراج', 'اخراج غیرقانونی', 'بازگشت به کار', 'ترک کار',
            'مزد', 'حقوق', 'حق سنوات', 'سنوات خدمت', 'پاداش',
            'اضافه کاری', 'نوبت کاری', 'مرخصی', 'مرخصی استحقاقی',
            'بیمه', 'بیمه بیکاری', 'تأمین اجتماعی', 'بازنشستگی',
            'حادثه ناشی از کار', 'بیماری شغلی',
            'هیأت تشخیص', 'هیأت حل اختلاف کار',
        ],
        
        # =====================================================================
        # حقوق اداری - Administrative Law
        # =====================================================================
        'اداری': [
            'دیوان عدالت اداری', 'شکایت از دولت', 'ابطال مصوبه',
            'تصمیم اداری', 'اقدام اداری', 'ترک فعل',
            'استخدام', 'انفصال از خدمت', 'بازخرید', 'اخراج از خدمت',
            'مالیات', 'مالیات بر درآمد', 'مالیات بر ارزش افزوده',
            'عوارض', 'جریمه مالیاتی',
            'شهرداری', 'کمیسیون ماده ۱۰۰', 'تخلفات ساختمانی',
        ],
        
        # =====================================================================
        # آیین دادرسی - Procedural Law
        # =====================================================================
        'آیین_دادرسی_مدنی': [
            'دادخواست', 'خواهان', 'خوانده', 'خواسته', 'بهای خواسته',
            'ابلاغ', 'ابلاغ واقعی', 'ابلاغ قانونی', 'اخطاریه',
            'جلسه دادرسی', 'ختم دادرسی', 'ختم مذاکرات',
            'قرار', 'قرار رد دعوا', 'قرار عدم استماع', 'قرار سقوط دعوا',
            'قرار ابطال دادخواست', 'قرار رد دادخواست',
            'قرار تأمین خواسته', 'قرار دستور موقت',
            'حکم', 'حکم قطعی', 'حکم غیابی', 'حکم حضوری',
            'واخواهی', 'تجدیدنظرخواهی', 'فرجام‌خواهی', 'اعاده دادرسی',
            'اعتراض ثالث', 'اعتراض ثالث اصلی', 'اعتراض ثالث طاری',
        ],
        
        'آیین_دادرسی_کیفری': [
            'شکایت', 'شاکی', 'متهم', 'مشتکی عنه',
            'کیفرخواست', 'قرار مجرمیت', 'قرار منع تعقیب', 'قرار موقوفی تعقیب',
            'بازداشت موقت', 'قرار کفالت', 'قرار وثیقه', 'قرار التزام',
            'دادسرا', 'دادستان', 'بازپرس', 'دادیار',
            'تحقیقات مقدماتی', 'صدور کیفرخواست',
        ],
        
        # =====================================================================
        # اجرای احکام - Execution
        # =====================================================================
        'اجرا': [
            'اجرای احکام', 'اجرای احکام مدنی', 'اجرای احکام کیفری',
            'اجراییه', 'صدور اجراییه', 'عملیات اجرایی',
            'توقیف', 'توقیف اموال', 'توقیف حساب', 'رفع توقیف',
            'مزایده', 'فروش اموال', 'تحویل مال',
            'ممنوع الخروج', 'جلب', 'حبس محکوم علیه',
            'اعتراض به عملیات اجرایی', 'شکایت از اجرا',
        ],
        
        # =====================================================================
        # اصول و قواعد فقهی - Fiqh Principles
        # =====================================================================
        'فقهی': [
            # اصول عملیه
            'اصل برائت', 'اصل احتیاط', 'اصل تخییر', 'اصل استصحاب',
            # قواعد فقهی
            'قاعده لاضرر', 'لاضرر و لاضرار', 'قاعده ید', 'قاعده تسلیط',
            'قاعده اتلاف', 'قاعده تسبیب', 'قاعده غرور', 'قاعده احسان',
            'قاعده اقدام', 'قاعده ضمان', 'قاعده حیازت',
            'اصاله الصحه', 'اصل صحت', 'اصاله اللزوم', 'اصل لزوم',
            'قاعده الزام', 'قاعده درء', 'قاعده فراش',
            # مفاهیم فقهی
            'حلال', 'حرام', 'مکروه', 'مستحب', 'مباح',
            'واجب', 'واجب عینی', 'واجب کفایی',
        ],
        
        # =====================================================================
        # مقامات قضایی - Judicial Authorities
        # =====================================================================
        'مقامات_قضایی': [
            'قاضی', 'رئیس دادگاه', 'مستشار', 'دادرس',
            'دادستان', 'معاون دادستان', 'بازپرس', 'دادیار',
            'رئیس شعبه', 'عضو ممیز',
        ],
        
        # =====================================================================
        # انواع دادگاه‌ها - Court Types
        # =====================================================================
        'دادگاه': [
            'دادگاه بدوی', 'دادگاه نخستین', 'دادگاه عمومی',
            'دادگاه حقوقی', 'دادگاه کیفری', 'دادگاه کیفری یک', 'دادگاه کیفری دو',
            'دادگاه تجدیدنظر', 'دادگاه تجدیدنظر استان',
            'دیوان عالی کشور', 'شعبه دیوان',
            'دادگاه انقلاب', 'دادگاه ویژه روحانیت',
            'دادگاه خانواده', 'دادگاه اطفال',
        ],
        
        # =====================================================================
        # نتایج رسیدگی - Case Outcomes
        # =====================================================================
        'نتایج': [
            'محکومیت', 'برائت', 'رد دعوا', 'پذیرش دعوا',
            'تأیید رأی', 'نقض رأی', 'اصلاح رأی',
            'صدور حکم', 'صدور قرار', 'ختم رسیدگی',
            'مختومه شدن پرونده', 'ارجاع به شعبه هم‌عرض',
        ],
        
        # =====================================================================
        # ثبت و اسناد - Registration
        # =====================================================================
        'ثبت': [
            'سند رسمی', 'سند عادی', 'سند مالکیت',
            'ثبت ملک', 'ثبت سند', 'دفتر اسناد رسمی',
            'سردفتر', 'دفتریار', 'تنظیم سند',
            'اسناد لازم الاجرا', 'اجرای ثبت', 'اداره ثبت',
        ],
        
        # =====================================================================
        # مالی و بانکی - Financial
        # =====================================================================
        'مالی': [
            'مطالبه وجه', 'مطالبه خسارت', 'استرداد وجه',
            'خسارت تأخیر تأدیه', 'بهره', 'ربا',
            'وام', 'تسهیلات', 'ضمانت‌نامه بانکی',
            'اعتبار اسنادی', 'حساب جاری', 'حساب سپرده',
        ],
        
        # =====================================================================
        # بیمه - Insurance
        # =====================================================================
        'بیمه': [
            'بیمه‌نامه', 'حق بیمه', 'خسارت بیمه‌ای',
            'بیمه عمر', 'بیمه حوادث', 'بیمه مسئولیت',
            'بیمه شخص ثالث', 'بیمه بدنه', 'بیمه آتش‌سوزی',
            'بیمه‌گر', 'بیمه‌گذار', 'ذینفع بیمه',
        ],
        
        # =====================================================================
        # مالکیت فکری - Intellectual Property
        # =====================================================================
        'مالکیت_فکری': [
            'حق اختراع', 'اختراع', 'ثبت اختراع',
            'علامت تجاری', 'برند', 'نام تجاری',
            'حق تألیف', 'کپی‌رایت', 'حقوق مؤلف',
            'طرح صنعتی', 'نمونه اشیاء',
        ],
    }


# ============================================================================
# Legal NER Engine
# ============================================================================

class LegalNEREngine:
    """
    Enterprise-grade NER engine for Persian legal text.
    
    Features:
    - Rule-based extraction (deterministic)
    - Configurable patterns
    - Deduplication and normalization
    - Performance optimized (< 30ms per chunk)
    
    Usage:
        engine = LegalNEREngine()
        entities = engine.extract(text)
    """
    
    def __init__(
        self,
        enable_deduplication: bool = True,
        enable_normalization: bool = True,
        confidence_threshold: float = 0.5,
        enable_governance: bool = True
    ):
        """
        Initialize NER Engine.
        
        Args:
            enable_deduplication: Remove duplicate entities
            enable_normalization: Normalize entity text
            confidence_threshold: Minimum confidence score
            enable_governance: Enable governance tracking (if available)
        """
        self.patterns = NERPatternConfig()
        self.enable_deduplication = enable_deduplication
        self.enable_normalization = enable_normalization
        self.confidence_threshold = confidence_threshold
        self.enable_governance = enable_governance and GOVERNANCE_AVAILABLE
        
        # Governance context
        self.governance_context = None
        if self.enable_governance and GovernanceContext:
            try:
                self.governance_context = GovernanceContext.get_active()
            except Exception:
                self.governance_context = None
        
        # Statistics
        self.stats = {
            "texts_processed": 0,
            "entities_extracted": 0,
            "avg_processing_time_ms": 0.0
        }
        
        logger.info(
            f"LegalNEREngine initialized "
            f"(governance={'enabled' if self.enable_governance else 'disabled'})"
        )
    
    def extract(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract all entity types from text.
        
        Args:
            text: Persian legal text
        
        Returns:
            Dictionary with entity lists:
            {
                "persons": [...],
                "organizations": [...],
                "courts": [...],
                "laws": [...],
                "topics": [...]
            }
        """
        import time
        start_time = time.time()
        
        # Governance: Log extraction start
        if self.governance_context:
            try:
                self.governance_context.log_operation(
                    operation="ner_extract_start",
                    details={"text_length": len(text)}
                )
            except Exception:
                pass
        
        if not text or not text.strip():
            return self._empty_result()
        
        # Normalize text for consistent extraction
        if self.enable_normalization:
            normalized_text = PersianLegalNormalizer.normalize_legal_text(text)
        else:
            normalized_text = text
        
        # Extract each entity type
        persons = self._extract_persons(normalized_text)
        organizations = self._extract_organizations(normalized_text)
        courts = self._extract_courts(normalized_text)
        laws = self._extract_laws(normalized_text)
        topics = self._extract_topics(normalized_text)
        legal_concepts = self._extract_legal_concepts(normalized_text)

        # Sanitize entity text to remove dangerous patterns
        persons = self._sanitize_entities(persons)
        organizations = self._sanitize_entities(organizations)
        courts = self._sanitize_entities(courts)
        laws = self._sanitize_entities(laws)
        topics = self._sanitize_entities(topics)
        legal_concepts = self._sanitize_entities(legal_concepts)

        # Build result
        result = {
            "persons": persons,
            "organizations": organizations,
            "courts": courts,
            "laws": laws,
            "topics": topics,
            "legal_concepts": legal_concepts
        }
        
        # Apply deduplication
        if self.enable_deduplication:
            result = self._deduplicate(result)
        
        # Update statistics
        processing_time_ms = (time.time() - start_time) * 1000
        self._update_stats(result, processing_time_ms)
        
        # Governance: Log extraction complete
        if self.governance_context:
            try:
                self.governance_context.log_operation(
                    operation="ner_extract_complete",
                    details={
                        "processing_time_ms": processing_time_ms,
                        "entity_counts": {
                            "persons": len(result["persons"]),
                            "organizations": len(result["organizations"]),
                            "courts": len(result["courts"]),
                            "laws": len(result["laws"]),
                            "topics": len(result["topics"]),
                            "legal_concepts": len(result["legal_concepts"])
                        }
                    }
                )
            except Exception:
                pass
        
        logger.debug(
            f"NER_PIPELINE: Extracted entities - "
            f"persons={len(result['persons'])}, "
            f"organizations={len(result['organizations'])}, "
            f"courts={len(result['courts'])}, "
            f"laws={len(result['laws'])}, "
            f"topics={len(result['topics'])} "
            f"({processing_time_ms:.1f}ms)"
        )
        
        return result
    
    def _extract_persons(self, text: str) -> List[Dict[str, Any]]:
        """Extract person entities"""
        persons: List[Any] = []
        seen_names: Set[str] = set()
        
        # Main person pattern
        for match in self.patterns.PERSON_PATTERN.finditer(text):
            title, name, father_name = match.groups()
            name = name.strip()
            entity_text, start, end = _trimmed_match_span(match)
            
            # Skip if already seen (by normalized name)
            norm_name = self._normalize_name(name)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            persons.append({
                "text": entity_text,
                "entity_type": "PERSON",
                "title": title.strip(),
                "name": name,
                "father_name": father_name.strip() if father_name else None,
                "normalized_name": norm_name,
                "start": start,
                "end": end,
                "confidence": 0.9
            })
        
        # Person with national ID
        for match in self.patterns.PERSON_WITH_ID.finditer(text):
            title, name, national_id = match.groups()
            name = name.strip()
            entity_text, start, end = _trimmed_match_span(match)
            
            norm_name = self._normalize_name(name)
            if norm_name in seen_names:
                # Update existing with national_id
                for p in persons:
                    if p.get("normalized_name") == norm_name:
                        p["national_id"] = national_id
                        p["confidence"] = min(1.0, p["confidence"] + 0.1)
                continue
            seen_names.add(norm_name)
            
            persons.append({
                "text": entity_text,
                "entity_type": "PERSON",
                "title": title.strip(),
                "name": name,
                "national_id": national_id,
                "normalized_name": norm_name,
                "start": start,
                "end": end,
                "confidence": 0.95
            })
        
        # Attorneys
        for match in self.patterns.ATTORNEY_PATTERN.finditer(text):
            title, name = match.groups()
            name = name.strip()
            entity_text, start, end = _trimmed_match_span(match)
            
            norm_name = self._normalize_name(name)
            if norm_name in seen_names:
                # Update role if already exists
                for p in persons:
                    if p.get("normalized_name") == norm_name:
                        p["role"] = "وکیل"
                continue
            seen_names.add(norm_name)
            
            persons.append({
                "text": entity_text,
                "entity_type": "PERSON",
                "title": title.strip(),
                "name": name,
                "role": "وکیل",
                "normalized_name": norm_name,
                "start": start,
                "end": end,
                "confidence": 0.85
            })
        
        return persons
    
    @staticmethod
    def _is_valid_org_name(name: Optional[str], org_type: str = "", full_text: str = "") -> bool:
        """
        Hardened validator to filter out false-positive organization names.
        Rejects:
        - Predicative verbs / verbal endings: 'خواهد بود', 'می‌باشد', 'است', 'گردد', 'یافته', 'ارتکاب یابد'
        - Ambiguous non-organization nouns: 'اطلاعاتی', 'خون', 'سلول', 'بذر' (e.g. بانک اطلاعاتی)
        - Adjectival 'سازمان‌یافته' or 'سازمان یافته'
        - Role designations: 'محال‌علیه', 'عامل'
        """
        if not name:
            return False

        cleaned = name.strip()
        if len(cleaned) < 2:
            return False
        if re.fullmatch(
            r"(?:سهامی\s+خاص|سهامی\s+عام|با\s+مسئولیت\s+محدود|"
            r"مسئولیت\s+محدود|تضامنی|مختلط\s+غیرسهامی|مختلط\s+سهامی|تعاونی)",
            cleaned,
        ):
            return False

        invalid_verbs = [
            "خواهد بود", "می‌باشد", "میباشد", "است", "گردد", "می‌شود",
            "میشود", "شد", "یافت", "یافته", "ارتکاب یابد", "عمل می‌نماید",
            "می‌نماید", "تضمین می‌شود", "تضمین میگردد"
        ]
        for v in invalid_verbs:
            if v in cleaned:
                return False

        invalid_collocations = [
            "اطلاعاتی", "خون", "بذر", "سلول",
            "یافته", "یافتگی",
            "محال‌علیه", "محال علیه",
        ]
        for inv in invalid_collocations:
            if inv in cleaned:
                return False

        if cleaned.endswith(" و") or cleaned.endswith(" به") or cleaned.endswith(" در"):
            return False

        return True

    def _extract_organizations(self, text: str) -> List[Dict[str, Any]]:
        """Extract organization entities"""
        organizations: List[Any] = []
        seen_names: Set[str] = set()
        
        # Companies
        for pattern in self.patterns.COMPANY_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                name = self._clean_org_name(groups[0]) if groups else None
                entity_text, start, end = _trimmed_match_span(match)
                
                if not name:
                    continue
                
                registration_id = groups[1] if len(groups) > 1 else None
                
                # Determine org type from pattern
                org_type = "شرکت"
                if 'مؤسسه' in match.group(0):
                    org_type = "مؤسسه"
                elif 'سازمان' in match.group(0):
                    org_type = "سازمان"
                
                if not self._is_valid_org_name(name, org_type, match.group(0)):
                    continue

                norm_name = self._normalize_org_name(name)
                if norm_name in seen_names:
                    continue
                seen_names.add(norm_name)
                
                organizations.append({
                    "text": entity_text,
                    "entity_type": "ORGANIZATION",
                    "name": name,
                    "org_type": org_type,
                    "registration_id": registration_id,
                    "normalized_name": norm_name,
                    "start": start,
                    "end": end,
                    "confidence": 0.85
                })
        
        # Banks
        for match in self.patterns.BANK_PATTERN.finditer(text):
            name = self._clean_org_name(match.group(1))
            entity_text, start, end = _trimmed_match_span(match)
            if not name:
                continue
            
            if not self._is_valid_org_name(name, "بانک", match.group(0)):
                continue

            norm_name = self._normalize_org_name(name)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            organizations.append({
                "text": entity_text,
                "entity_type": "ORGANIZATION",
                "name": name,
                "org_type": "بانک",
                "normalized_name": norm_name,
                "start": start,
                "end": end,
                "confidence": 0.9
            })
        
        # Government organizations
        for pattern in self.patterns.GOV_ORG_PATTERNS:
            for match in pattern.finditer(text):
                entity_text, start, end = _trimmed_match_span(match)
                raw_name = (
                    match.group(1) if match.groups() else match.group(0)
                )
                name = self._clean_org_name(raw_name)
                if not name:
                    continue
                
                if not self._is_valid_org_name(name, "دولتی", match.group(0)):
                    continue

                norm_name = self._normalize_org_name(name)
                if norm_name in seen_names:
                    continue
                seen_names.add(norm_name)
                
                organizations.append({
                    "text": entity_text,
                    "entity_type": "ORGANIZATION",
                    "name": name,
                    "org_type": "دولتی",
                    "normalized_name": norm_name,
                    "start": start,
                    "end": end,
                    "confidence": 0.85
                })

        # Oil & Gas Industry organizations (برای دعاوی نفتی و گازی)
        for pattern in self.patterns.OIL_GAS_PATTERNS:
            for match in pattern.finditer(text):
                entity_text, start, end = _trimmed_match_span(match)
                raw_name = (
                    match.group(1) if match.groups() else match.group(0)
                )
                name = self._clean_org_name(raw_name)
                if not name:
                    continue

                if not self._is_valid_org_name(name, "نفت_گاز_پتروشیمی", match.group(0)):
                    continue

                norm_name = self._normalize_org_name(name)
                if norm_name in seen_names:
                    continue
                seen_names.add(norm_name)

                organizations.append({
                    "text": entity_text,
                    "entity_type": "ORGANIZATION",
                    "name": name,
                    "org_type": "نفت_گاز_پتروشیمی",
                    "normalized_name": norm_name,
                    "start": start,
                    "end": end,
                    "confidence": 0.95  # Higher confidence for industry-specific
                })
        
        return organizations

    @staticmethod
    def _clean_org_name(name: Optional[str]) -> Optional[str]:
        if not name:
            return None

        cleaned = name.strip()
        prose_boundary = re.search(
            r"\s+(?:اعم\s+از\s+اینکه|حداقل|حداکثر|کمتر\s+از|بیشتر\s+از|"
            r"در\s+مناقصه|در\s+اجرای|به\s+میزان|به\s+منظور|مکلف(?:ند)?|"
            r"مشمول|اعلام|تهیه|انجام|باشد|است|در|برای|به|که|موظف|"
            r"و\s+(?:وزارت(?:خانه)?|سازمان|اتاق(?:های)?|بانک|رعایت))\b"
            r"|\s+\d+\s*[-–—]",
            cleaned,
        )
        if prose_boundary:
            cleaned = cleaned[: prose_boundary.start()].rstrip()

        if re.match(r"^(?:متشکل|های|در|برای|به|از|و|شامل|حسب)\b", cleaned):
            return None
        if re.match(r"^سازمان\s+های\b", cleaned):
            return None
        if cleaned in {
            "ایرانی",
            "خارجی",
            "خصوصی",
            "تعاونی",
            "دولتی",
            "عمومی",
            "وابسته",
            "تابعه",
        }:
            return None
        return cleaned or None
    
    def _extract_courts(self, text: str) -> List[Dict[str, Any]]:
        """Extract court entities"""
        courts: List[Any] = []
        seen_courts: Set[str] = set()
        
        for pattern in self.patterns.COURT_PATTERNS:
            for match in pattern.finditer(text):
                full_text, start, end = _trimmed_match_span(match)
                
                # Parse court details based on pattern groups
                groups = match.groups()
                
                court_info = {
                    "text": full_text,
                    "entity_type": "COURT",
                    "start": start,
                    "end": end,
                    "confidence": 0.9
                }
                
                # Try to extract level, branch, location
                if len(groups) >= 2:
                    # Check if first group is branch number
                    if groups[0] and groups[0].isdigit():
                        court_info["branch"] = groups[0]
                        court_info["level"] = groups[1].strip() if len(groups) > 1 and groups[1] else None
                        court_info["city"] = groups[2].strip() if len(groups) > 2 and groups[2] else None
                    else:
                        court_info["level"] = groups[0].strip() if groups[0] else full_text
                        court_info["province"] = groups[1].strip() if len(groups) > 1 and groups[1] else None
                        court_info["branch"] = groups[2] if len(groups) > 2 and groups[2] else None
                else:
                    court_info["level"] = full_text
                
                # Normalize for deduplication
                norm_court = self._normalize_court(court_info)
                if norm_court in seen_courts:
                    continue
                seen_courts.add(norm_court)
                
                court_info["normalized_name"] = norm_court
                courts.append(court_info)
        
        return courts
    
    def _extract_laws(self, text: str) -> List[Dict[str, Any]]:
        """Extract law/article entities"""
        laws: List[Any] = []
        seen_refs: Set[str] = set()
        
        # Single article references
        for match in self.patterns.LAW_ARTICLE_PATTERN.finditer(text):
            article_num = match.group(1)
            law_name = match.group(3).strip() if match.group(3) else match.group(2)
            if law_name:
                law_name = re.sub(r"\s+(?:و|یا)$", "", law_name).strip()
            
            # Skip if law name is empty or too short
            if not law_name or len(law_name) < 3:
                continue
            
            ref_key = f"ماده {article_num} {law_name}"
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            
            laws.append({
                "text": match.group(0).strip(),
                "entity_type": "LAW_ARTICLE",
                "article_number": article_num,
                "law_name": law_name,
                "normalized_ref": ref_key,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.85
            })
        
        # Multiple article references
        for match in self.patterns.MULTIPLE_ARTICLES_PATTERN.finditer(text):
            articles_str = match.group(1)
            law_name = match.group(2).strip()
            
            # Parse article numbers
            article_nums = re.findall(r'\d+', articles_str)
            
            for article_num in article_nums:
                ref_key = f"ماده {article_num} {law_name}"
                if ref_key in seen_refs:
                    continue
                seen_refs.add(ref_key)
                
                laws.append({
                    "text": f"ماده {article_num} قانون {law_name}",
                    "entity_type": "LAW_ARTICLE",
                    "article_number": article_num,
                    "law_name": law_name,
                    "normalized_ref": ref_key,
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.8
                })
        
        # Bylaws
        for match in self.patterns.BYLAW_PATTERN.finditer(text):
            bylaw_name = match.group(1).strip()
            
            ref_key = f"آیین‌نامه {bylaw_name}"
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            
            laws.append({
                "text": match.group(0).strip(),
                "entity_type": "BYLAW",
                "law_name": bylaw_name,
                "normalized_ref": ref_key,
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.8
            })
        
        return laws
    
    def _extract_topics(self, text: str) -> List[Dict[str, Any]]:
        """Extract legal topics/categories"""
        topics: List[Any] = []
        found_topics: Set[str] = set()
        
        for category, keywords in self.patterns.TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if keyword in found_topics:
                        continue
                    found_topics.add(keyword)
                    
                    topics.append({
                        "text": keyword,
                        "entity_type": "TOPIC",
                        "topic": keyword,
                        "category": category,
                        "confidence": 0.8
                    })
        
        return topics

    def _extract_legal_concepts(self, text: str) -> List[Dict[str, Any]]:
        """Extract legal concepts and references from advisory opinions"""
        concepts: List[Any] = []
        seen_concepts: Set[str] = set()

        # Legal concept patterns
        for pattern in self.patterns.LEGAL_CONCEPT_PATTERNS:
            for match in pattern.finditer(text):
                concept_text, start, end = _trimmed_match_span(match)
                if concept_text in seen_concepts:
                    continue
                seen_concepts.add(concept_text)

                concepts.append({
                    "text": concept_text,
                    "entity_type": "LEGAL_CONCEPT",
                    "concept": concept_text,
                    "start": start,
                    "end": end,
                    "confidence": 0.85
                })

        # Law reference patterns (ارجاعات قانونی گسترده)
        for pattern in self.patterns.LAW_REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                law_ref = match.group(1).strip()
                if len(law_ref) < 4 or law_ref in seen_concepts:
                    continue
                seen_concepts.add(law_ref)

                concepts.append({
                    "text": match.group(0).strip(),
                    "entity_type": "LAW_REFERENCE",
                    "law_name": law_ref,
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.8
                })

        return concepts

    # ========================================================================
    # Normalization Helpers
    # ========================================================================
    
    def _normalize_name(self, name: str) -> str:
        """Normalize person name for deduplication"""
        if not name:
            return ""
        # Remove extra whitespace and normalize Persian chars
        name = PersianLegalNormalizer.normalize_legal_text(name)
        # Remove common prefixes/suffixes
        name = re.sub(r'^(خانم|آقای|آقا)\s+', '', name)
        return name.strip().lower()
    
    def _normalize_org_name(self, name: str) -> str:
        """Normalize organization name for deduplication"""
        if not name:
            return ""
        name = PersianLegalNormalizer.normalize_legal_text(name)
        # Remove org type prefixes for normalization
        name = re.sub(r'^(شرکت|مؤسسه|سازمان|بانک|اداره)\s+', '', name)
        return name.strip().lower()
    
    def _normalize_court(self, court_info: Dict[str, Any]) -> str:
        """Normalize court info for deduplication"""
        parts: List[Any] = []
        if court_info.get("level"):
            parts.append(court_info["level"])
        if court_info.get("branch"):
            parts.append(f"شعبه {court_info['branch']}")
        if court_info.get("city"):
            parts.append(court_info["city"])
        return " ".join(parts).lower()
    
    def _sanitize_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sanitize entity text to remove dangerous patterns.
        
        Removes:
        - HTML tags (<script>, etc.)
        - Shell commands (rm -rf, etc.)
        - SQL injection patterns
        - JavaScript code patterns
        
        Args:
            entities: List of entity dictionaries
        
        Returns:
            Sanitized entity list
        """
        dangerous_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'<.*?>',  # Any HTML tag
            r'rm\s+-rf',  # Shell commands
            r'\$\(.+?\)',  # Shell command substitution
            r';\s*DROP\s+TABLE',  # SQL injection
            r'OR\s+1=1',  # SQL injection
            r'alert\s*\(',  # JavaScript alert
            r'eval\s*\(',  # JavaScript eval
        ]
        
        sanitized = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            
            # Sanitize text field
            if "text" in entity:
                original_text = entity["text"]
                for pattern in dangerous_patterns:
                    original_text = re.sub(pattern, '', original_text, flags=re.IGNORECASE | re.DOTALL)
                entity["text"] = original_text.strip()
            
            # Sanitize name field if exists
            if "name" in entity:
                original_name = entity["name"]
                for pattern in dangerous_patterns:
                    original_name = re.sub(pattern, '', original_name, flags=re.IGNORECASE | re.DOTALL)
                entity["name"] = original_name.strip()
            
            sanitized.append(entity)
        
        return sanitized
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def _empty_result(self) -> Dict[str, List]:
        """Return empty result structure"""
        return {
            "persons": [],
            "organizations": [],
            "courts": [],
            "laws": [],
            "topics": [],
            "legal_concepts": []
        }
    
    def _deduplicate(self, result: Dict[str, List]) -> Dict[str, List]:
        """Remove duplicate entities within each category"""
        for entity_type, entities in result.items():
            seen = set()
            deduped: List[Any] = []
            for entity in entities:
                key = entity.get("normalized_name") or entity.get("normalized_ref") or entity.get("text", "")
                if key and key.lower() not in seen:
                    seen.add(key.lower())
                    deduped.append(entity)
            result[entity_type] = deduped
        return result
    
    def _update_stats(self, result: Dict[str, List], processing_time_ms: float):
        """Update processing statistics"""
        total_entities = sum(len(entities) for entities in result.values())
        
        self.stats["texts_processed"] += 1
        self.stats["entities_extracted"] += total_entities
        
        n = self.stats["texts_processed"]
        self.stats["avg_processing_time_ms"] = (
            (self.stats["avg_processing_time_ms"] * (n - 1) + processing_time_ms) / n
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        return self.stats.copy()


# ============================================================================
# Convenience Functions (API Contract)
# ============================================================================

# Global engine instance (lazy initialization)
# Thread-safe singleton for NER engine
from mahoun.core.singleton import ThreadSafeSingleton

_ner_singleton = ThreadSafeSingleton["LegalNEREngine"]("LegalNEREngine")


def _get_engine() -> LegalNEREngine:
    """
    Get or create global engine instance (thread-safe).
    
    Returns:
        LegalNEREngine instance
    """
    return _ner_singleton.get_instance(factory=lambda: LegalNEREngine())


def extract_entities(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract all entity types from Persian legal text.
    
    This is the main API function for NER extraction.
    
    Args:
        text: Persian legal text (raw or normalized)
    
    Returns:
        Dictionary containing extracted entities:
        {
            "persons": [
                {"text": "...", "name": "...", "title": "...", ...},
                ...
            ],
            "organizations": [
                {"text": "...", "name": "...", "org_type": "...", ...},
                ...
            ],
            "courts": [
                {"text": "...", "level": "...", "branch": "...", ...},
                ...
            ],
            "laws": [
                {"text": "...", "article_number": "...", "law_name": "...", ...},
                ...
            ],
            "topics": [
                {"text": "...", "topic": "...", "category": "...", ...},
                ...
            ]
        }
    
    Example:
        >>> from mahoun.pipelines.ingestion.legal_ner import extract_entities
        >>> text = "آقای احمد احمدی فرزند محمد به شعبه ۱۰ دادگاه عمومی حقوقی تهران مراجعه کرد."
        >>> entities = extract_entities(text)
        >>> print(entities["persons"][0]["name"])
        "احمد احمدی"
    """
    return _get_engine().extract(text)


def extract_entities_for_chunk(chunk_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract entities from a single chunk of text.
    
    Alias for extract_entities() for pipeline integration clarity.
    
    Args:
        chunk_text: Text chunk from verdict/document
    
    Returns:
        Entity dictionary (same as extract_entities)
    """
    return extract_entities(chunk_text)


# ============================================================================
# Batch Processing
# ============================================================================

def extract_entities_batch(
    texts: List[str],
    consolidate: bool = False
) -> List[Dict[str, List[Dict[str, Any]]]]:
    """
    Extract entities from multiple texts.
    
    Args:
        texts: List of text chunks
        consolidate: If True, merge all entities into single result
    
    Returns:
        List of entity dictionaries (one per text) or single consolidated dict
    """
    engine = _get_engine()
    results = [engine.extract(text) for text in texts]
    
    if consolidate:
        consolidated: Dict[str, List[Dict[str, Any]]] = {
            "persons": [],
            "organizations": [],
            "courts": [],
            "laws": [],
            "topics": []
        }
        
        for result in results:
            for entity_type, entities in result.items():
                consolidated[entity_type].extend(entities)
        
        # Deduplicate consolidated result
        return [engine._deduplicate(consolidated)]
    
    return results


# ============================================================================
# Module Test
# ============================================================================

if __name__ == "__main__":
    # Test the NER engine
    test_text = """
    آقای احمد احمدی فرزند محمد با وکالت خانم زهرا محمدی فرزند علی
    به شعبه ۱۰ دادگاه عمومی حقوقی تهران مراجعه و دادخواست خود را
    بر اساس ماده ۱۰ قانون مدنی و مواد ۳۴۸ و ۳۵۸ قانون آیین دادرسی مدنی
    تقدیم نمود. خوانده دعوی شرکت سهامی خاص توسعه فناوری به شماره ثبت ۱۲۳۴۵
    و بانک ملی ایران می‌باشند. موضوع دعوی مطالبه وجه و الزام به تنظیم سند بود.
    دادگاه تجدیدنظر استان تهران رأی بدوی را تأیید نمود.
    """
    
    print("🔍 Testing Legal NER Engine")
    print("=" * 60)
    
    entities = extract_entities(test_text)
    
    for entity_type, items in entities.items():
        print(f"\n📌 {entity_type.upper()} ({len(items)} found):")
        for item in items:
            print(f"   • {item.get('name') or item.get('text')}")
    
    print("\n" + "=" * 60)
    print("✅ NER Test Complete")
 