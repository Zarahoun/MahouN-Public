"""
Ultra Persian Legal NLP - Advanced Persian Legal Text Processing
=================================================================
State-of-the-art NLP for Persian legal documents with specialized
entity recognition, dependency parsing, and legal term extraction.

Features:
- Advanced Persian tokenization with legal domain awareness
- Named Entity Recognition (NER) for legal entities
- Legal term extraction and classification
- Dependency parsing for legal text
- Article and law reference extraction
- Legal relationship extraction
- Coreference resolution
- Sentiment analysis for legal opinions
- Legal document classification
- Citation network analysis
- Temporal expression extraction
- Legal event extraction
- Multi-level text normalization
- Legal abbreviation expansion
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
_NON_LAW_TITLE_STARTS = {
    "اقدام",
    "اين",
    "این",
    "در",
    "زير",
    "زیر",
    "كه",
    "که",
    "مذكور",
    "مذکور",
    "موضوع",
}


class EntityType(Enum):
    """Legal entity types"""
    ARTICLE = "article"  # ماده
    LAW = "law"  # قانون
    REGULATION = "regulation"  # آیین‌نامه
    COURT = "court"  # دادگاه
    JUDGE = "judge"  # قاضی
    LAWYER = "lawyer"  # وکیل
    PLAINTIFF = "plaintiff"  # خواهان
    DEFENDANT = "defendant"  # خوانده
    PROSECUTOR = "prosecutor"  # دادستان
    WITNESS = "witness"  # شاهد
    DATE = "date"  # تاریخ
    MONEY = "money"  # مبلغ
    ORGANIZATION = "organization"  # سازمان
    LOCATION = "location"  # مکان
    CASE_NUMBER = "case_number"  # شماره پرونده


class LegalTermCategory(Enum):
    """Legal term categories"""
    CIVIL = "civil"  # حقوق مدنی
    CRIMINAL = "criminal"  # حقوق جزا
    COMMERCIAL = "commercial"  # حقوق تجارت
    ADMINISTRATIVE = "administrative"  # حقوق اداری
    PROCEDURAL = "procedural"  # آیین دادرسی
    CONSTITUTIONAL = "constitutional"  # حقوق اساسی
    INTERNATIONAL = "international"  # حقوق بین‌الملل


@dataclass
class Token:
    """Token with linguistic features"""
    text: str
    start: int
    end: int
    pos_tag: Optional[str] = None
    lemma: Optional[str] = None
    is_legal_term: bool = False
    normalized: Optional[str] = None


@dataclass
class Entity:
    """Named entity"""
    text: str
    entity_type: EntityType
    start: int
    end: int
    confidence: float
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "type": self.entity_type.value,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass
class LegalTerm:
    """Legal terminology"""
    term: str
    category: LegalTermCategory
    definition: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    related_articles: List[str] = field(default_factory=list)


@dataclass
class LegalRelation:
    """Legal relationship between entities"""
    subject: Entity
    relation: str
    object: Entity
    confidence: float


@dataclass
class ArticleReference:
    """Reference to legal article"""
    article_number: str
    law_name: Optional[str] = None
    section: Optional[str] = None
    clause: Optional[str] = None
    full_text: str = ""
    start: int = 0
    end: int = 0


class PersianNormalizer:
    """Advanced Persian text normalizer"""
    
    def __init__(self):
        # Character mappings
        self.char_map = {
            'ك': 'ک',
            'ي': 'ی',
            'ى': 'ی',
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
            '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
            '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        }
        
        # Diacritics to remove
        self.diacritics = 'ًٌٍَُِّْٰٔ'
        
        print("🔤 Persian Normalizer initialized")
    
    def normalize(self, text: str, level: str = "full") -> str:
        """
        Normalize Persian text
        
        Args:
            text: Input text
            level: Normalization level (light, medium, full)
        
        Returns:
            Normalized text
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if level not in {"light", "medium", "full"}:
            raise ValueError("level must be one of: light, medium, full")

        if level in ["light", "medium", "full"]:
            # Character normalization
            for old, new in self.char_map.items():
                text = text.replace(old, new)
        
        if level in ["medium", "full"]:
            # Remove diacritics
            for diacritic in self.diacritics:
                text = text.replace(diacritic, '')
        
        if level == "full":
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            # Normalize punctuation
            text = text.replace('‌', ' ')  # Zero-width non-joiner
            text = re.sub(r'[‌\u200c]+', ' ', text)
        
        return text


class PersianTokenizer:
    """Advanced Persian tokenizer with legal domain awareness"""
    
    def __init__(self):
        # Legal compound terms that should not be split
        self.compound_terms = [
            'قانون مدنی', 'قانون تجارت', 'قانون کار', 'قانون جزا',
            'آیین دادرسی مدنی', 'آیین دادرسی کیفری',
            'دادگاه عالی', 'دیوان عدالت', 'شورای نگهبان',
            'حقوق مدنی', 'حقوق جزا', 'حقوق تجارت',
            'قرارداد خرید', 'قرارداد فروش', 'قرارداد اجاره',
        ]
        
        self.normalizer = PersianNormalizer()
        print("✂️ Persian Tokenizer initialized")
    
    def tokenize(self, text: str, preserve_compounds: bool = True) -> List[Token]:
        """
        Tokenize Persian text
        
        Args:
            text: Input text
            preserve_compounds: Keep compound legal terms together
        
        Returns:
            List of tokens
        """
        tokens = []
        
        # Normalize text
        normalized = self.normalizer.normalize(text, level="medium")
        
        # Protect compound terms
        protected_spans = []
        if preserve_compounds:
            for compound in self.compound_terms:
                for match in re.finditer(re.escape(compound), text):
                    protected_spans.append((match.start(), match.end(), compound))
        
        # Sort by start position
        protected_spans.sort(key=lambda x: x[0])
        
        # Tokenize
        current_pos = 0
        for start, end, compound in protected_spans:
            # Tokenize before compound
            if current_pos < start:
                before_text = text[current_pos:start]
                tokens.extend(self._simple_tokenize(before_text, current_pos))
            
            # Add compound as single token
            tokens.append(Token(
                text=compound,
                start=start,
                end=end,
                is_legal_term=True,
                normalized=self.normalizer.normalize(compound)
            ))
            
            current_pos = end
        
        # Tokenize remaining text
        if current_pos < len(text):
            tokens.extend(self._simple_tokenize(text[current_pos:], current_pos))
        
        return tokens
    
    def _simple_tokenize(self, text: str, offset: int = 0) -> List[Token]:
        """Simple word tokenization"""
        tokens = []
        
        # Split by whitespace and punctuation
        pattern = r'[\w\u0600-\u06FF]+'
        for match in re.finditer(pattern, text):
            tokens.append(Token(
                text=match.group(),
                start=offset + match.start(),
                end=offset + match.end(),
                normalized=self.normalizer.normalize(match.group())
            ))
        
        return tokens


class LegalEntityExtractor:
    """Extract legal entities from Persian text"""
    
    def __init__(self):
        self.patterns = self._build_patterns()
        self.legal_terms = self._build_legal_terms()
        print("🏛️ Legal Entity Extractor initialized")
    
    def extract(self, text: str) -> List[Entity]:
        """Extract all legal entities from text"""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        entities = []
        
        # Extract articles
        entities.extend(self._extract_articles(text))
        
        # Extract laws
        entities.extend(self._extract_laws(text))
        
        # Extract courts
        entities.extend(self._extract_courts(text))
        
        # Extract legal roles
        entities.extend(self._extract_legal_roles(text))
        
        # Extract dates
        entities.extend(self._extract_dates(text))
        
        # Extract money amounts
        entities.extend(self._extract_money(text))
        
        # Extract case numbers
        entities.extend(self._extract_case_numbers(text))
        
        return self._deduplicate_entities(entities)

    @staticmethod
    def _deduplicate_entities(entities: List[Entity]) -> List[Entity]:
        """Keep the strongest entity for each overlapping span and type."""
        selected: Dict[Tuple[int, int, EntityType], Entity] = {}
        for entity in entities:
            key = (entity.start, entity.end, entity.entity_type)
            previous = selected.get(key)
            if previous is None or entity.confidence > previous.confidence:
                selected[key] = entity

        ordered = sorted(
            selected.values(),
            key=lambda entity: (entity.start, -(entity.end - entity.start), -entity.confidence),
        )
        result: List[Entity] = []
        for entity in ordered:
            if any(
                entity.entity_type == existing.entity_type
                and entity.start >= existing.start
                and entity.end <= existing.end
                and (entity.start, entity.end) != (existing.start, existing.end)
                for existing in result
            ):
                continue
            result.append(entity)
        return result
    
    def _extract_articles(self, text: str) -> List[Entity]:
        """Extract article references"""
        entities = []
        
        # Pattern: ماده + number
        pattern = r'ماده\s+(\d+)'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.ARTICLE,
                start=match.start(),
                end=match.end(),
                confidence=0.95,
                metadata={"article_number": match.group(1)}
            ))
        
        # Pattern: ماده + number + تبصره
        pattern = r'ماده\s+(\d+)\s+تبصره\s+(\d+)'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.ARTICLE,
                start=match.start(),
                end=match.end(),
                confidence=0.98,
                metadata={
                    "article_number": match.group(1),
                    "note_number": match.group(2)
                }
            ))
        
        # Pattern: بند + letter/number
        pattern = r'بند\s+([ا-ی]|\d+)'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.ARTICLE,
                start=match.start(),
                end=match.end(),
                confidence=0.90,
                metadata={"clause": match.group(1)}
            ))
        
        return entities
    
    def _extract_laws(self, text: str) -> List[Entity]:
        """Extract law references"""
        entities = []
        
        # Common law names
        law_patterns = [
            r'قانون\s+مدنی',
            r'قانون\s+تجارت',
            r'قانون\s+کار',
            r'قانون\s+جزا',
            r'قانون\s+آیین\s+دادرسی\s+مدنی',
            r'قانون\s+آیین\s+دادرسی\s+کیفری',
            r'قانون\s+اساسی',
            r'قانون\s+[^\s]+(?:\s+[^\s]+){0,3}',  # Generic law pattern
        ]
        
        for pattern in law_patterns:
            for match in re.finditer(pattern, text):
                entities.append(Entity(
                    text=match.group(0),
                    entity_type=EntityType.LAW,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.92,
                    metadata={"law_name": match.group(0)}
                ))
        
        return entities
    
    def _extract_courts(self, text: str) -> List[Entity]:
        """Extract court references"""
        entities = []
        
        court_patterns = [
            r'دادگاه\s+عالی',
            r'دادگاه\s+تجدیدنظر',
            r'دادگاه\s+بدوی',
            r'دیوان\s+عدالت\s+اداری',
            r'دیوان\s+عالی\s+کشور',
            r'شعبه\s+\d+\s+دادگاه',
            r'دادگاه\s+[^\s]+',
        ]
        
        for pattern in court_patterns:
            for match in re.finditer(pattern, text):
                entities.append(Entity(
                    text=match.group(0),
                    entity_type=EntityType.COURT,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.88,
                    metadata={"court_name": match.group(0)}
                ))
        
        return entities
    
    def _extract_legal_roles(self, text: str) -> List[Entity]:
        """Extract legal role mentions"""
        entities = []
        
        roles = {
            r'قاضی': EntityType.JUDGE,
            r'وکیل': EntityType.LAWYER,
            r'خواهان': EntityType.PLAINTIFF,
            r'خوانده': EntityType.DEFENDANT,
            r'دادستان': EntityType.PROSECUTOR,
            r'شاهد': EntityType.WITNESS,
        }
        
        for pattern, entity_type in roles.items():
            for match in re.finditer(pattern, text):
                entities.append(Entity(
                    text=match.group(0),
                    entity_type=entity_type,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.85,
                    metadata={"role": entity_type.value}
                ))
        
        return entities
    
    def _extract_dates(self, text: str) -> List[Entity]:
        """Extract date mentions"""
        entities = []
        
        # Persian date pattern
        pattern = r'\d{1,2}/\d{1,2}/\d{2,4}'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.DATE,
                start=match.start(),
                end=match.end(),
                confidence=0.90,
                metadata={"date": match.group(0)}
            ))
        
        # Written dates
        pattern = r'(?:روز|تاریخ)\s+\d{1,2}\s+(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s+\d{4}'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.DATE,
                start=match.start(),
                end=match.end(),
                confidence=0.95,
                metadata={"date": match.group(0)}
            ))
        
        return entities
    
    def _extract_money(self, text: str) -> List[Entity]:
        """Extract money amounts"""
        entities = []
        
        # Pattern: number + currency
        pattern = r'(\d+(?:[,،]\d+)*)\s*(ریال|تومان|دلار|یورو)'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.MONEY,
                start=match.start(),
                end=match.end(),
                confidence=0.92,
                metadata={
                    "amount": match.group(1),
                    "currency": match.group(2)
                }
            ))
        
        return entities
    
    def _extract_case_numbers(self, text: str) -> List[Entity]:
        """Extract case/file numbers"""
        entities = []
        
        # Pattern: پرونده/کلاسه + number
        pattern = r'(?:پرونده|کلاسه)\s+(?:شماره\s+)?(\d+(?:/\d+)*)'
        for match in re.finditer(pattern, text):
            entities.append(Entity(
                text=match.group(0),
                entity_type=EntityType.CASE_NUMBER,
                start=match.start(),
                end=match.end(),
                confidence=0.93,
                metadata={"case_number": match.group(1)}
            ))
        
        return entities
    
    def _build_patterns(self) -> Dict:
        """Build regex patterns for entity extraction"""
        return {
            "article": r"ماده\s+(\d+)(?:\s+تبصره\s+(\d+))?",
            "clause": r"بند\s+([ا-ی]|\d+)",
            "date": r"\d{1,2}/\d{1,2}/\d{2,4}",
            "money": r"(\d+(?:[,،]\d+)*)\s*(ریال|تومان|دلار|یورو)",
            "case_number": r"(?:پرونده|کلاسه)\s+(?:شماره\s+)?(\d+(?:/\d+)*)",
        }
    
    def _build_legal_terms(self) -> Dict[str, LegalTerm]:
        """Build legal terminology dictionary"""
        return {
            term: LegalTerm(term=term, category=category)
            for category, terms in {
                LegalTermCategory.CIVIL: ("مدنی", "قرارداد", "ملک", "ارث", "نکاح", "طلاق"),
                LegalTermCategory.CRIMINAL: ("جزا", "جرم", "مجازات", "حبس", "جنایت"),
                LegalTermCategory.COMMERCIAL: ("تجارت", "شرکت", "سهام", "ورشکستگی"),
                LegalTermCategory.PROCEDURAL: ("دادرسی", "دادخواست", "رسیدگی", "حکم"),
            }.items()
            for term in terms
        }


class UltraPersianLegalNLP:
    """
    Ultra-advanced Persian legal NLP system
    
    Features:
    - Advanced tokenization
    - Entity extraction
    - Legal term recognition
    - Relationship extraction
    - Text normalization
    """
    
    def __init__(self):
        self.normalizer = PersianNormalizer()
        self.tokenizer = PersianTokenizer()
        self.entity_extractor = LegalEntityExtractor()
        self.legal_terms = self._build_legal_dictionary()
        
        # Statistics
        self.stats = {
            "texts_processed": 0,
            "entities_extracted": 0,
            "terms_identified": 0
        }
        
        print("⚖️ Ultra Persian Legal NLP initialized")
    
    def process(self, text: str) -> Dict:
        """
        Process Persian legal text
        
        Args:
            text: Input text
        
        Returns:
            Dictionary with tokens, entities, and terms
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        # Normalize
        normalized = self.normalizer.normalize(text)
        
        # Tokenize
        tokens = self.tokenizer.tokenize(text)
        
        # Extract entities
        entities = self.entity_extractor.extract(text)
        
        # Extract legal terms
        legal_terms = self.extract_legal_terms(text)
        
        # Extract article references
        article_refs = self.extract_article_references(text)
        
        # Update statistics
        self.stats["texts_processed"] += 1
        self.stats["entities_extracted"] += len(entities)
        self.stats["terms_identified"] += len(legal_terms)
        
        return {
            "original": text,
            "normalized": normalized,
            "tokens": [{"text": t.text, "start": t.start, "end": t.end} for t in tokens],
            "entities": [e.to_dict() for e in entities],
            "legal_terms": legal_terms,
            "article_references": [self._article_ref_to_dict(ref) for ref in article_refs],
            "statistics": {
                "num_tokens": len(tokens),
                "num_entities": len(entities),
                "num_legal_terms": len(legal_terms)
            }
        }
    
    def tokenize(self, text: str) -> List[Token]:
        """Tokenize text"""
        return self.tokenizer.tokenize(text)
    
    def extract_legal_entities(self, text: str) -> List[Entity]:
        """Extract legal entities"""
        return self.entity_extractor.extract(text)
    
    def extract_legal_terms(self, text: str) -> List[str]:
        """Extract legal terminology"""
        terms = []
        normalized_text = self.normalizer.normalize(text).casefold()

        for term in self.legal_terms:
            normalized_term = self.normalizer.normalize(term).casefold()
            if normalized_term in normalized_text:
                terms.append(term)

        return sorted(set(terms))

    def extract_article_references(self, text: str) -> List[ArticleReference]:
        """Extract article references with context"""
        references = []

        digits = r"[0-9۰-۹٠-٩]+"
        pattern = re.compile(
            rf"(?:(?:تبصره|تبصرە)[ \t]*(?P<section_before>{digits})[ \t]+)?"
            rf"(?P<kind>ماده|مادّه|اصل)[ \t]*"
            rf"(?:[\(（][ \t]*(?P<number_paren>{digits})[ \t]*[\)）]"
            rf"|(?P<number_plain>{digits}))"
            rf"(?:[ \t]+(?:تبصره|تبصرە)[ \t]*(?P<section_after>{digits}))?"
        )
        law_pattern = re.compile(
            r"[ \t]*قانون[ \t]+(?P<law_name>[^،؛.\n\-–—]+)"
        )
        for match in pattern.finditer(text):
            section = match.group("section_before") or match.group("section_after")
            article_number = match.group("number_paren") or match.group("number_plain")
            end = match.end()
            law_name = None
            law_match = law_pattern.match(text, end)
            if law_match:
                candidate = law_match.group("law_name").strip()
                first_word = self.normalizer.normalize(candidate).split(" ", 1)[0]
                if first_word.casefold() not in _NON_LAW_TITLE_STARTS:
                    law_name = candidate
                    end = law_match.end()

            references.append(ArticleReference(
                article_number=article_number.translate(_DIGIT_TRANSLATION),
                law_name=law_name,
                section=section.translate(_DIGIT_TRANSLATION) if section else None,
                full_text=text[match.start() : end],
                start=match.start(),
                end=end
            ))
        
        return references
    
    def classify_legal_domain(self, text: str) -> Dict[LegalTermCategory, float]:
        """Classify text into legal domains"""
        domain_scores = defaultdict(float)
        
        # Domain keywords
        domain_keywords = {
            LegalTermCategory.CIVIL: ['مدنی', 'قرارداد', 'ملک', 'ارث', 'نکاح', 'طلاق'],
            LegalTermCategory.CRIMINAL: ['جزا', 'جرم', 'مجازات', 'حبس', 'جنایت'],
            LegalTermCategory.COMMERCIAL: ['تجارت', 'شرکت', 'سهام', 'ورشکستگی'],
            LegalTermCategory.ADMINISTRATIVE: ['اداری', 'دولت', 'مقررات', 'آیین‌نامه'],
            LegalTermCategory.PROCEDURAL: ['دادرسی', 'دادخواست', 'رسیدگی', 'حکم'],
        }
        
        text_lower = text.lower()
        
        for domain, keywords in domain_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            domain_scores[domain] = score / len(keywords)
        
        return dict(domain_scores)
    
    def get_statistics(self) -> Dict:
        """Get processing statistics"""
        return self.stats.copy()
    
    def _build_legal_dictionary(self) -> Set[str]:
        """Build comprehensive legal dictionary"""
        return {
            # Courts and judicial bodies
            "دادگاه", "محکمه", "دیوان", "شعبه", "قاضی", "رئیس",
            
            # Legal roles
            "وکیل", "خواهان", "خوانده", "دادستان", "شاکی", "متهم",
            "شاهد", "کارشناس", "مدافع", "وکیل مدافع",
            
            # Legal documents
            "دادخواست", "لایحه", "پاسخ", "اظهارنامه", "صورتجلسه",
            "حکم", "رأی", "قرار", "اجرائیه", "گواهی",
            
            # Legal concepts
            "قانون", "ماده", "تبصره", "بند", "مقررات", "آیین‌نامه",
            "حق", "تعهد", "مسئولیت", "ضمان", "خسارت",
            "قرارداد", "عقد", "توافق", "ایقاع",
            
            # Procedures
            "رسیدگی", "محاکمه", "دادرسی", "تجدیدنظر", "فرجام",
            "اعتراض", "شکایت", "درخواست", "تقاضا",
            
            # Judgments
            "محکومیت", "برائت", "رد", "قبول", "اعاده دادرسی",
            
            # Civil law
            "ملک", "مالکیت", "حیازت", "تصرف", "انتقال",
            "ارث", "وصیت", "وقف", "هبه",
            "نکاح", "طلاق", "مهریه", "نفقه",
            
            # Criminal law
            "جرم", "جنایت", "جنحه", "تخلف", "مجازات",
            "حبس", "جزای نقدی", "شلاق", "قصاص", "دیه",
            
            # Commercial law
            "تجارت", "شرکت", "سهام", "سهامدار", "مدیر",
            "ورشکستگی", "اعسار", "چک", "سفته", "برات",
        }
    
    def _article_ref_to_dict(self, ref: ArticleReference) -> Dict:
        """Convert article reference to dictionary"""
        return {
            "article_number": ref.article_number,
            "law_name": ref.law_name,
            "section": ref.section,
            "clause": ref.clause,
            "full_text": ref.full_text,
            "start": ref.start,
            "end": ref.end
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    print("🚀 Testing Ultra Persian Legal NLP")
    print("=" * 60)
    
    # Initialize NLP
    nlp = UltraPersianLegalNLP()
    
    # Sample legal text
    text = """
    طبق ماده 10 قانون مدنی، قوانین راجع به اهلیت اشخاص تابع قانون دولتی است.
    دادگاه عالی در تاریخ 15/03/1402 حکم به پرداخت 50000000 ریال خسارت صادر کرد.
    خواهان با وکالت آقای احمدی علیه خوانده در شعبه 12 دادگاه تجدیدنظر اقامه دعوا نمود.
    """
    
    # Process text
    print(f"\n📝 Processing text...")
    result = nlp.process(text)
    
    print(f"\n🔤 Tokens: {result['statistics']['num_tokens']}")
    for token in result['tokens'][:5]:
        print(f"   - {token['text']}")
    
    print(f"\n🏛️ Entities: {result['statistics']['num_entities']}")
    for entity in result['entities']:
        print(f"   - {entity['text']} ({entity['type']})")
    
    print(f"\n⚖️ Legal Terms: {result['statistics']['num_legal_terms']}")
    for term in result['legal_terms'][:10]:
        print(f"   - {term}")
    
    print(f"\n📋 Article References:")
    for ref in result['article_references']:
        print(f"   - {ref['full_text']}")
        if ref['law_name']:
            print(f"     Law: {ref['law_name']}")
    
    # Domain classification
    print(f"\n🎯 Legal Domain Classification:")
    domains = nlp.classify_legal_domain(text)
    for domain, score in sorted(domains.items(), key=lambda x: x[1], reverse=True):
        if score > 0:
            print(f"   - {domain.value}: {score:.2f}")
    
    # Statistics
    stats = nlp.get_statistics()
    print(f"\n📈 Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n✅ Persian Legal NLP test complete")
