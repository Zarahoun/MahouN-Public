"""
Data Augmentation for Legal Text
================================
Advanced data augmentation pipeline with entity preservation for legal domain.

Features:
- Entity-preserving synonym replacement
- Context-aware paraphrasing
- Legal entity extraction integration
"""

import random
import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

import numpy as np

from .config import AugmentationConfig, AugmentationStrategy

logger = logging.getLogger(__name__)

# =============================================================================
# Helper Data Structures
# =============================================================================

@dataclass
class LabeledEntity:
    """Labeled entity with metadata"""
    text: str
    label: str
    start: int
    end: int
    weight: float = 1.0


# =============================================================================
# Embedded Rules (from missing weight.py)
# =============================================================================

ENTITY_RULES = [
    {"label": "ARTICLE", "pattern": r"ماده\s+[0-9۰-۹]{1,4}", "weight": 1.5},
    {"label": "NOTE", "pattern": r"تبصره\s+[0-9۰-۹]{1,2}", "weight": 1.2},
    {"label": "LAW_REF", "pattern": r"قانون\s+[^،\.\n]{5,50}", "weight": 1.8},
    {"label": "PUB_4311", "pattern": r"(?:نشریه|بخشنامه)\s*4311", "weight": 2.0},
    {"label": "GCC_ARTICLE", "pattern": r"ماده\s+\d+\s+شرایط\s+عمومی\s+پیمان", "weight": 2.0},
    {"label": "TECH_TERM", "pattern": r"(?:صورت وضعیت|ضریب تعدیل|تضامین|حسن انجام کار|پیش‌پرداخت)", "weight": 1.5},
    {"label": "COURT", "pattern": r"دادگاه\s+(?:کیفری|حقوقی|تجدیدنظر|انقلاب)[^،\.\n]*", "weight": 1.5},
    {"label": "DATE", "pattern": r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", "weight": 1.0},
    {"label": "MONEY", "pattern": r"\d+(?:[.,]\d+)*\s*(?:ریال|تومان)", "weight": 1.0},
]


# =============================================================================
# Logic Components
# =============================================================================

class LegalEntityExtractor:
    """Extract legal entities to preserve during augmentation"""
    
    def __init__(self):
        self.rules = ENTITY_RULES
    
    def extract_entities(self, text: str) -> List[LabeledEntity]:
        """Extract entities from text"""
        entities = []
        
        for rule in self.rules:
            pattern = rule["pattern"]
            label = rule["label"]
            weight = rule.get("weight", 1.0)
            
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check overlaps
                start, end = match.span()
                is_overlap = any(
                    (start < e.end and end > e.start) for e in entities
                )
                
                if not is_overlap:
                    entities.append(LabeledEntity(
                        text=match.group(0),
                        label=label,
                        start=start,
                        end=end,
                        weight=weight
                    ))
        
        return sorted(entities, key=lambda x: x.start)


class PersianLegalSynonymDict:
    """Persian synonym dictionary enhanced with legal domain terms"""
    
    def __init__(self):
        self.synonyms = {
            # Contract terms (CRITICAL for tests) - قرارداد is canonical
            "قرارداد": ["عقد", "پیمان", "موافقت‌نامه"],
            
            # Termination terms (CRITICAL for tests) - فسخ is canonical
            "فسخ": ["ابطال", "لغو", "خاتمه پیمان", "انحلال قرارداد", "برچیدن پیمان"],
            
            # Legal terms - دادگاه is canonical
            "دادگاه": ["محکمه", "دیوان", "مرجع قضایی"],
            "قاضی": ["حاکم شرع", "دادرس", "رئیس دادگاه"],
            "حکم": ["رأی", "دادنامه", "فرمان"],
            "خواهان": ["شاکی", "مدعی", "تظلم‌خواه"],
            "خوانده": ["متهم", "مشتکی‌عنه", "طرف شکایت"],
            "وکیل": ["نماینده حقوقی", "مدافع", "کارشناس حقوقی"],
            "پرونده": ["دوسیه", "سوابق", "مستندات"],
            "شهادت": ["گواهی", "استشهاد", "بیانت"],
            "جرم": ["بزه", "تخلف قانونی", "عمل مجرمانه"],
            "مجازات": ["کیفر", "عقوبت", "جریمه"],
            
            # Common verbs
            "صادر کرد": ["انشا کرد", "ابلاغ نمود", "اعلام داشت"],
            "تأیید کرد": ["ابرک نمود", "تنفیذ کرد", "صحه‌گذاری کرد"],
            "رد کرد": ["نقض نمود", "باطل اعلام کرد"],
            "اظهار داشت": ["بیان نمود", "عنوان کرد", "متذکر شد"],
            
            # Adjectives
            "قانونی": ["مشروع", "منطبق بر قانون", "حقوقی"],
            "غیرقانونی": ["نامشروع", "خلاف قانون", "غیرمجاز"],
            "قطعی": ["لازم‌الاجرا", "نهایی", "غیرقابل اعتراض"],

            # Construction / Publication 4311
            "کارفرما": ["دستگاه اجرایی", "طرف اول قرارداد", "صاحب کار"],
            "پیمانکار": ["طرف دوم قرارداد", "مجری طرح", "سازنده"],
            "مهندس مشاور": ["ناظر", "مشاور طرح", "عامل نظارت"],
            "صورت وضعیت": ["گزارش کارکرد", "صورت کارکرد", "بیلان کاری"],
            "تعدیل": ["مابه‌التفاوت نرخ", "تعدیل آحاد بها", "به‌روزرسانی قیمت"],
            "تاخیر": ["تعلل", "دیرکرد", "فوت وقت"],
            "خاتمه": ["پایان کار", "تحویل نهایی", "اتمام قرارداد"],
        }
    
    def get_synonyms(self, word: str) -> List[str]:
        return self.synonyms.get(word, [])
    
    def has_synonyms(self, word: str) -> bool:
        return word in self.synonyms


class DataAugmenter:
    """
    Main data augmentation engine.
    
    Strategies:
    1. Synonym Replacement (Entity-safe)
    2. Paraphrasing
    3. Noise Injection (Simulate OCR errors/typos)
    """
    
    def __init__(self, config: Optional[AugmentationConfig] = None):
        self.config = config or AugmentationConfig()
        self.entity_extractor = LegalEntityExtractor()
        self.synonym_dict = PersianLegalSynonymDict()
        
        logger.info(f"DataAugmenter initialized with strategies: {self.config.strategies}")

    def augment(self, text: str) -> List[str]:
        """
        Generate augmented variations of the input text.
        
        Args:
            text: Input text
            
        Returns:
            List of augmented texts
        """
        if not self.config.enabled:
            return []
            
        variations = set()
        
        # Determine how many variations to generate per strategy
        # We aim for 'augmentation_factor' total variations
        target_count = int(self.config.augmentation_factor)
        
        strategies = self.config.strategies
        if not strategies:
            return []
            
        # Try to generate enough variations
        attempts = 0
        max_attempts = target_count * 3
        
        while len(variations) < target_count and attempts < max_attempts:
            attempts += 1
            strategy = random.choice(strategies)
            
            augmented = None
            if strategy == AugmentationStrategy.SYNONYM_REPLACEMENT:
                augmented = self._augment_synonyms(text)
            elif strategy == AugmentationStrategy.PARAPHRASE:
                augmented = self._augment_paraphrase(text)
            # Add other strategies here
            
            if augmented and augmented != text:
                variations.add(augmented)
        
        return list(variations)

    def _augment_synonyms(self, text: str) -> str:
        """
        Replace words with synonyms while preserving entities.
        Optimized implementation using boolean mask.
        """
        # 1. Identify protected entities
        entities = self.entity_extractor.extract_entities(text)
        
        # Create a boolean mask for protected characters
        # This allows O(1) check for any position
        mask = [False] * len(text)
        for e in entities:
             for i in range(e.start, e.end):
                 if i < len(mask):
                     mask[i] = True
        
        # 2. Tokenize and identify candidates
        # We use a simple regex iterator to get words and their spans
        # This is faster and more accurate than split() + find()
        word_iter = re.finditer(r'\b\w+\b', text)
        
        words_info = [] # (start, end, text, is_protected)
        
        for match in word_iter:
            start, end = match.span()
            word = match.group()
            
            # Check if any char in this word is protected
            # Using any() on a slice of the mask
            is_protected = False
            # Check boundaries first for speed
            if mask[start] or mask[end-1]:
                is_protected = True
            elif any(mask[start:end]):
                is_protected = True
            
            words_info.append({
                "start": start,
                "end": end,
                "text": word,
                "protected": is_protected
            })
            
        if not words_info:
            return text
            
        # 3. Identify replaceable candidates
        candidates = []
        for i, info in enumerate(words_info):
            if not info["protected"] and self.synonym_dict.has_synonyms(info["text"]):
                candidates.append(i)
        
        if not candidates:
            return text

        # 4. Select replacements
        num_to_replace = max(1, int(len(words_info) * self.config.synonym_replacement_ratio))
        indices_to_replace = set(random.sample(
            candidates, 
            min(len(candidates), num_to_replace)
        ))
        
        # 5. Reconstruct text
        # We rebuild the string from chunks to preserve whitespace/punctuation perfectly
        result_parts = []
        last_idx = 0
        
        for i, info in enumerate(words_info):
            # Append text before this word (whitespace, punctuation)
            result_parts.append(text[last_idx:info["start"]])
            
            word = info["text"]
            if i in indices_to_replace:
                synonyms = self.synonym_dict.get_synonyms(word)
                if synonyms:
                    word = random.choice(synonyms)
            
            result_parts.append(word)
            last_idx = info["end"]
            
        # Append remaining text
        result_parts.append(text[last_idx:])
        
        return "".join(result_parts)

    def _augment_paraphrase(self, text: str) -> str:
        """Simple template-based paraphrasing"""
        # In a real system, this might call an LLM or use a seq2seq model
        # Here we use simple context-aware regex replacements
        
        patterns = [
            (r'ماده\s+(\d+)', r'ماده \1 از قانون'),
            (r'تبصره\s+(\d+)', r'تبصره \1 این ماده'),
            (r'دادگاه\s+(عمومی|کیفری)', r'شبه دادگاه \1'), # Example variation
            (r'حکم\s+به', r'صدور حکم دال بر'),
            (r'با توجه به', r'نظر به'),
            (r'در نظر گرفتن', r'لحاظ نمودن'),
            # Construction Specific
            (r'تاخیرات\s+مجاز', r'تمدید مدت پیمان'),
            (r'حوادث\s+قهری', r'شرایط فورس ماژور'),
            (r'تحویل\s+موقت', r'تحویل اولیه پروژه'),
        ]
        
        augmented = text
        # Apply 1-2 random patterns
        selected_patterns = random.sample(patterns, min(len(patterns), 2))
        
        for pat, repl in selected_patterns:
            augmented = re.sub(pat, repl, augmented)
            
        return augmented
