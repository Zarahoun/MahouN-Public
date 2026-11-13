"""
Advanced Query Enhancement for Persian Legal RAG
================================================

Features:
- Intent classification (definition, procedure, case law, etc.)
- Entity extraction and normalization
- Legal term expansion with synonyms
- Query complexity analysis
- Multi-turn context handling
- Persian NLP integration
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
try:
    from mahoun.pipelines.persian_legal_nlp import normalize, tokenize, extract_legal_terms
    HAS_PERSIAN_NLP = True
except ImportError:
    HAS_PERSIAN_NLP = False

from mahoun.pipelines._logging import setup_logger

log = setup_logger("query_enhancement")


class QueryIntent(str, Enum):
    """Query intent types"""
    DEFINITION = "definition"           # "قانون مدنی چیست"
    PROCEDURE = "procedure"             # "نحوه ثبت شرکت"
    CASE_LAW = "case_law"              # "رأی دادگاه در مورد..."
    ARTICLE_LOOKUP = "article_lookup"   # "ماده 10 قانون مدنی"
    COMPARISON = "comparison"           # "تفاوت بین ... و ..."
    REQUIREMENT = "requirement"         # "شرایط لازم برای..."
    CONSEQUENCE = "consequence"         # "عواقب حقوقی..."
    GENERAL = "general"                 # سوال عمومی


class QueryComplexity(str, Enum):
    """Query complexity levels"""
    SIMPLE = "simple"           # یک مفهوم ساده
    MODERATE = "moderate"       # چند مفهوم مرتبط
    COMPLEX = "complex"         # چند مفهوم با روابط پیچیده
    MULTI_HOP = "multi_hop"     # نیاز به استدلال چند مرحله‌ای


@dataclass
class EnhancedQuery:
    """Enhanced query with metadata"""
    original: str
    normalized: str
    intent: QueryIntent
    complexity: QueryComplexity
    entities: List[Dict[str, str]]
    legal_terms: List[str]
    keywords: List[str]
    expansions: List[str]
    reformulations: List[str]
    confidence: float
    metadata: Dict = field(default_factory=dict)
    
    def get_all_variants(self) -> List[str]:
        """Get all query variants"""
        variants = [self.normalized]
        variants.extend(self.expansions)
        variants.extend(self.reformulations)
        return list(set(variants))


class LegalTermExpander:
    """
    Expand legal terms with synonyms and related concepts
    
    Specialized for Persian legal domain
    """
    
    # Legal term synonyms and expansions
    LEGAL_SYNONYMS = {
        # قوانین و مقررات
        "قانون": ["ماده", "تبصره", "مقررات", "آیین‌نامه"],
        "ماده": ["بند", "تبصره", "قانون"],
        "مقررات": ["قانون", "آیین‌نامه", "دستورالعمل"],
        
        # دادگاه و قضا
        "دادگاه": ["محکمه", "مرجع قضایی", "شعبه"],
        "قاضی": ["دادرس", "مرجع رسیدگی"],
        "رأی": ["حکم", "قرار", "تصمیم"],
        "حکم": ["رأی", "قرار قضایی"],
        
        # قراردادها
        "قرارداد": ["عقد", "توافق", "معامله", "پیمان"],
        "عقد": ["قرارداد", "توافق"],
        "طرفین": ["اصحاب دعوا", "متعاقدین"],
        
        # اشخاص حقوقی
        "شخص": ["فرد", "کس"],
        "شرکت": ["موسسه", "سازمان"],
        
        # اموال
        "ملک": ["مال", "دارایی", "عین"],
        "مال": ["ملک", "دارایی"],
        
        # جرایم
        "جرم": ["بزه", "معصیت"],
        "مجازات": ["کیفر", "تعزیر"],
        
        # حقوق مدنی
        "ضرر": ["خسارت", "زیان"],
        "تعهد": ["التزام", "مسئولیت"],
        "حق": ["اختیار", "صلاحیت"],
    }
    
    # Legal concepts and their related terms
    LEGAL_CONCEPTS = {
        "ازدواج": ["نکاح", "عقد نکاح", "ازدواج دائم", "ازدواج موقت", "صیغه"],
        "طلاق": ["فسخ نکاح", "جدایی", "انحلال نکاح"],
        "ارث": ["میراث", "ترکه", "وراث", "سهم الارث"],
        "وصیت": ["وصیت‌نامه", "موصی", "موصی‌له"],
        "وکالت": ["وکیل", "موکل", "وکالت‌نامه"],
        "رهن": ["گرو", "مرهون", "راهن", "مرتهن"],
        "اجاره": ["کرایه", "موجر", "مستأجر", "اجاره‌نامه"],
        "بیع": ["خرید و فروش", "معامله", "بایع", "مشتری"],
    }
    
    @classmethod
    def expand(cls, term: str) -> List[str]:
        """Expand a legal term with synonyms"""
        expansions = [term]
        
        # Direct synonyms
        if term in cls.LEGAL_SYNONYMS:
            expansions.extend(cls.LEGAL_SYNONYMS[term])
        
        # Concept-based expansion
        if term in cls.LEGAL_CONCEPTS:
            expansions.extend(cls.LEGAL_CONCEPTS[term])
        
        # Check if term is in any synonym list
        for key, synonyms in cls.LEGAL_SYNONYMS.items():
            if term in synonyms and key not in expansions:
                expansions.append(key)
        
        return list(set(expansions))
    
    @classmethod
    def expand_query(cls, query: str) -> List[str]:
        """Expand entire query with legal terms"""
        expansions = [query]
        
        # Tokenize
        tokens = query.split()
        
        # Find legal terms and expand
        for i, token in enumerate(tokens):
            term_expansions = cls.expand(token)
            if len(term_expansions) > 1:
                # Create new queries with each expansion
                for expansion in term_expansions[1:]:  # Skip original
                    new_tokens = tokens.copy()
                    new_tokens[i] = expansion
                    expansions.append(" ".join(new_tokens))
        
        return list(set(expansions))[:10]  # Limit to 10


class IntentClassifier:
    """
    Classify query intent for better retrieval strategy
    """
    
    # Intent patterns
    INTENT_PATTERNS = {
        QueryIntent.DEFINITION: [
            r"چیست",
            r"چه است",
            r"تعریف",
            r"مفهوم",
            r"معنی",
            r"منظور از",
        ],
        QueryIntent.PROCEDURE: [
            r"نحوه",
            r"چگونه",
            r"روش",
            r"مراحل",
            r"طریقه",
            r"چطور",
        ],
        QueryIntent.CASE_LAW: [
            r"رأی",
            r"حکم",
            r"قرار",
            r"رویه قضایی",
            r"نظر دادگاه",
        ],
        QueryIntent.ARTICLE_LOOKUP: [
            r"ماده\s+\d+",
            r"بند\s+\d+",
            r"تبصره\s+\d+",
        ],
        QueryIntent.COMPARISON: [
            r"تفاوت",
            r"مقایسه",
            r"فرق",
            r"در مقابل",
        ],
        QueryIntent.REQUIREMENT: [
            r"شرایط",
            r"الزامات",
            r"ضوابط",
            r"لازم",
        ],
        QueryIntent.CONSEQUENCE: [
            r"عواقب",
            r"پیامد",
            r"نتیجه",
            r"اثر",
        ],
    }
    
    @classmethod
    def classify(cls, query: str) -> Tuple[QueryIntent, float]:
        """
        Classify query intent
        
        Returns:
            Tuple of (intent, confidence)
        """
        query_lower = query.lower()
        
        # Check each intent pattern
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent, 0.9
        
        # Default to general
        return QueryIntent.GENERAL, 0.5


class ComplexityAnalyzer:
    """
    Analyze query complexity
    """
    
    @staticmethod
    def analyze(query: str, entities: List[Dict], legal_terms: List[str]) -> QueryComplexity:
        """
        Analyze query complexity
        
        Factors:
        - Number of entities
        - Number of legal terms
        - Query length
        - Presence of logical operators
        """
        # Count factors
        num_entities = len(entities)
        num_legal_terms = len(legal_terms)
        num_words = len(query.split())
        
        # Check for logical operators
        has_and = any(word in query for word in ["و", "and", "همچنین"])
        has_or = any(word in query for word in ["یا", "or", "و یا"])
        has_not = any(word in query for word in ["نه", "not", "بدون"])
        has_condition = any(word in query for word in ["اگر", "if", "در صورت"])
        
        # Complexity score
        score = 0
        score += num_entities * 2
        score += num_legal_terms * 1.5
        score += num_words * 0.5
        score += 5 if has_and else 0
        score += 5 if has_or else 0
        score += 5 if has_not else 0
        score += 10 if has_condition else 0
        
        # Classify
        if score < 10:
            return QueryComplexity.SIMPLE
        elif score < 20:
            return QueryComplexity.MODERATE
        elif score < 35:
            return QueryComplexity.COMPLEX
        else:
            return QueryComplexity.MULTI_HOP


class EntityExtractor:
    """
    Extract entities from query
    """
    
    # Entity patterns
    ENTITY_PATTERNS = {
        "article": r"ماده\s+(\d+)",
        "law": r"قانون\s+([\w\s]+)",
        "date": r"(\d{4})/(\d{1,2})/(\d{1,2})",
        "number": r"\d+",
    }
    
    @classmethod
    def extract(cls, query: str) -> List[Dict[str, str]]:
        """Extract entities from query"""
        entities = []
        
        for entity_type, pattern in cls.ENTITY_PATTERNS.items():
            matches = re.finditer(pattern, query)
            for match in matches:
                entities.append({
                    "type": entity_type,
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                })
        
        return entities


class QueryReformulator:
    """
    Reformulate queries for better matching
    """
    
    # Reformulation rules
    REFORMULATION_RULES = [
        # Question to statement
        (r"(.+)\s+چیست\??", r"\1"),
        (r"چگونه\s+(.+)\??", r"نحوه \1"),
        (r"چرا\s+(.+)\??", r"دلیل \1"),
        (r"چه زمانی\s+(.+)\??", r"زمان \1"),
        
        # Add legal context
        (r"^([^قانون]+)$", r"\1 قانون"),
        
        # Normalize punctuation
        (r"؟", r""),
        (r"\?", r""),
    ]
    
    @classmethod
    def reformulate(cls, query: str) -> List[str]:
        """Generate reformulations"""
        reformulations = [query]
        
        for pattern, replacement in cls.REFORMULATION_RULES:
            try:
                reformed = re.sub(pattern, replacement, query)
                if reformed != query and reformed not in reformulations:
                    reformulations.append(reformed.strip())
            except:
                continue
        
        return reformulations[:5]


class AdvancedQueryEnhancer:
    """
    Main query enhancement system
    
    Combines all enhancement techniques
    """
    
    def __init__(self):
        self.term_expander = LegalTermExpander()
        self.intent_classifier = IntentClassifier()
        self.complexity_analyzer = ComplexityAnalyzer()
        self.entity_extractor = EntityExtractor()
        self.reformulator = QueryReformulator()
        
        log.info("Advanced Query Enhancer initialized")
    
    def enhance(self, query: str, context: Optional[List[str]] = None) -> EnhancedQuery:
        """
        Enhance query with all techniques
        
        Args:
            query: Original query
            context: Previous queries for multi-turn context
            
        Returns:
            EnhancedQuery with all enhancements
        """
        # Normalize query
        if HAS_PERSIAN_NLP:
            normalized = normalize(query)
        else:
            normalized = query.strip()
        
        # Extract entities
        entities = self.entity_extractor.extract(normalized)
        
        # Extract legal terms
        if HAS_PERSIAN_NLP:
            legal_terms = extract_legal_terms(normalized)
        else:
            legal_terms = []
        
        # Classify intent
        intent, intent_confidence = self.intent_classifier.classify(normalized)
        
        # Analyze complexity
        complexity = self.complexity_analyzer.analyze(normalized, entities, legal_terms)
        
        # Generate expansions
        expansions = self.term_expander.expand_query(normalized)
        
        # Generate reformulations
        reformulations = self.reformulator.reformulate(normalized)
        
        # Extract keywords (simple tokenization)
        keywords = [w for w in normalized.split() if len(w) > 2]
        
        # Handle multi-turn context
        if context:
            # Add context to metadata
            metadata = {"context": context}
            # Could enhance query with context here
        else:
            metadata = {}
        
        # Create enhanced query
        enhanced = EnhancedQuery(
            original=query,
            normalized=normalized,
            intent=intent,
            complexity=complexity,
            entities=entities,
            legal_terms=legal_terms,
            keywords=keywords,
            expansions=expansions,
            reformulations=reformulations,
            confidence=intent_confidence,
            metadata=metadata,
        )
        
        log.debug(
            f"Enhanced query: intent={intent.value}, "
            f"complexity={complexity.value}, "
            f"variants={len(enhanced.get_all_variants())}"
        )
        
        return enhanced
    
    def enhance_batch(self, queries: List[str]) -> List[EnhancedQuery]:
        """Enhance multiple queries"""
        return [self.enhance(q) for q in queries]


# Global enhancer instance
_global_enhancer: Optional[AdvancedQueryEnhancer] = None


def get_global_enhancer() -> AdvancedQueryEnhancer:
    """Get or create global enhancer"""
    global _global_enhancer
    if _global_enhancer is None:
        _global_enhancer = AdvancedQueryEnhancer()
    return _global_enhancer


def main():
    """Test query enhancement"""
    print("=" * 70)
    print("Testing Advanced Query Enhancement")
    print("=" * 70)
    
    enhancer = AdvancedQueryEnhancer()
    
    # Test queries
    test_queries = [
        "قانون مدنی چیست",
        "نحوه ثبت شرکت",
        "ماده 10 قانون مدنی",
        "تفاوت بین قرارداد و عقد",
        "شرایط لازم برای طلاق",
        "عواقب حقوقی نقض قرارداد",
    ]
    
    for query in test_queries:
        print(f"\n{'='*70}")
        print(f"📝 Original: {query}")
        print(f"{'='*70}")
        
        enhanced = enhancer.enhance(query)
        
        print(f"🎯 Intent: {enhanced.intent.value} (confidence: {enhanced.confidence:.2f})")
        print(f"📊 Complexity: {enhanced.complexity.value}")
        print(f"🏷️  Entities: {len(enhanced.entities)}")
        for entity in enhanced.entities:
            print(f"   - {entity['type']}: {entity['value']}")
        print(f"⚖️  Legal Terms: {enhanced.legal_terms}")
        print(f"🔑 Keywords: {enhanced.keywords[:5]}")
        print(f"\n🔄 Expansions ({len(enhanced.expansions)}):")
        for exp in enhanced.expansions[:3]:
            print(f"   - {exp}")
        print(f"\n📝 Reformulations ({len(enhanced.reformulations)}):")
        for ref in enhanced.reformulations[:3]:
            print(f"   - {ref}")
        print(f"\n✨ Total Variants: {len(enhanced.get_all_variants())}")


if __name__ == "__main__":
    main()
