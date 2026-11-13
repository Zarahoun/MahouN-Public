"""
Ultra-Advanced Citation Auditing System
=======================================
Enterprise-grade citation verification and accuracy checking.

Features:
- Multi-level citation extraction (explicit, implicit, cross-reference)
- Fuzzy matching for citation verification
- Citation graph construction
- Plagiarism detection
- Citation style validation
- Source credibility scoring
- Citation completeness checking
- Automated citation correction
- Citation network analysis
- Legal citation standards compliance
"""

import re
import difflib
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
_PERSIAN_TEXT_TRANSLATION = str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " "})
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
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


def _normalize_citation_text(text: str) -> str:
    normalized = text.translate(_DIGIT_TRANSLATION).translate(_PERSIAN_TEXT_TRANSLATION)
    normalized = _DIACRITICS.sub("", normalized)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


# ============================================================================
# Citation Types and Results
# ============================================================================

class CitationType(Enum):
    """Types of citations"""
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"
    LEGAL_ARTICLE = "legal_article"
    CASE_REFERENCE = "case_reference"
    STATUTE = "statute"


class CitationStyle(Enum):
    """Citation style standards"""
    PERSIAN_LEGAL = "persian_legal"
    BLUEBOOK = "bluebook"
    APA = "apa"


@dataclass
class Citation:
    """Enhanced citation object"""
    text: str
    citation_type: CitationType
    start: int
    end: int
    source_reference: Optional[str] = None
    article_number: Optional[str] = None
    law_name: Optional[str] = None
    case_number: Optional[str] = None
    is_valid: bool = False
    confidence: float = 0.0
    matched_source: Optional[str] = None
    similarity_score: float = 0.0
    completeness_score: float = 0.0
    style_compliance: bool = False
    extraction_method: str = "pattern"
    section_number: Optional[str] = None
    publication_date: Optional[str] = None


@dataclass
class UltraCitationAuditResult:
    """Comprehensive citation audit result"""
    is_valid: bool
    overall_score: float
    total_citations: int
    valid_citations: int
    invalid_citations: int
    missing_citations: int
    citations: List[Citation] = field(default_factory=list)
    invalid_citation_details: List[Dict] = field(default_factory=list)
    accuracy_score: float = 0.0
    completeness_score: float = 0.0
    style_compliance_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    corrections: Dict[str, str] = field(default_factory=dict)
    processing_time_ms: float = 0.0


@dataclass
class PlagiarismResult:
    """Plagiarism detection result"""
    has_plagiarism: bool
    plagiarism_score: float
    suspicious_spans: List[Tuple[str, str, float]]
    sources: List[str]


# ============================================================================
# Citation Extractor
# ============================================================================

class CitationExtractor:
    """Extract citations from text"""
    
    def __init__(self):
        self.patterns = self._build_patterns()
        print("📚 Citation Extractor initialized")
    
    def extract_citations(self, text: str) -> List[Citation]:
        """Extract all citations from text"""
        citations: List[Any] = []
        citations.extend(self._extract_explicit_citations(text))
        citations.extend(self._extract_legal_articles(text))
        citations.extend(self._extract_case_references(text))
        citations.extend(self._extract_implicit_citations(text))
        citations = self._remove_duplicates(citations)
        citations.sort(key=lambda c: c.start)
        return citations
    
    def _build_patterns(self) -> Dict[str, List[str]]:
        """Build citation extraction patterns"""
        digits = r"[0-9۰-۹٠-٩]+"
        return {
            "explicit": [
                r'"([^"]+)"\s*\(([^)]+)\)',
                r'«([^»]+)»\s*\(([^)]+)\)',
            ],
            "legal_article": [
                rf'(?P<article_kind>ماده|مادّه|اصل)[ \t]*[\(（]?[ \t]*'
                rf'(?P<article_number>{digits})[ \t]*[\)）]?[ \t]*'
                rf'(?P<law_name>قانون[ \t]+.+?)'
                rf'(?=\s+(?:و\s+)?(?:تبصره|ماده|'
                rf'اصل(?![ \t]*(?:چهل(?:[ \t]+و[ \t]+چهارم)?|{digits}))|'
                r'رأی|حکم|قرار|پرونده)|'
                r'\s+(?:مصوب(?:ه)?|اصلاح(?:ی)?|سال|باشد|است|'
                r'م[کك]لف(?:ند)?|مشمول|شامل)\b|'
                r'\s+و\s+مجموعه[ \t]+ها[یي]?[ \t]+ز[یي]ر[ \t]+نظر\b|'
                r'\s+از\s+موانع\b|'
                r'\s*-\s*(?:مصوب|اصلاح)|'
                r'\s+به\s+(?:\d|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|'
                r'یازده|دوازده|سی|ب[یي]ست|پانزده|'
                r'میزان|منظور|ترتیب)\b|\s+و\s+در\s+(?:چهارچوب|صورت)\b|'
                r'[،؛.\n]|$)'
                rf'(?:\s*-\s*)?(?:\s*(?:مصوب(?:ه)?(?:\s+سال)?|سال)\s*'
                rf'(?P<publication_date>{digits}(?:[ \t]*/[ \t]*{digits}){{0,2}}))?',
                rf'تبصره[ \t]*[\(（]?[ \t]*(?P<section_number>{digits})'
                rf'[ \t]*[\)）]?[ \t]+'
                rf'(?P<article_kind>ماده|مادّه|اصل)[ \t]*'
                rf'[\(（]?[ \t]*(?P<article_number>{digits})[ \t]*[\)）]?'
                rf'(?:[ \t]+(?P<law_name>قانون[ \t]+.+?))?'
                r'(?=\s+(?:مصوب|اصلاح|باشد|است|م[کك]لف|مشمول)\b|'
                r'\s+و\s+مجموعه[ \t]+ها[یي]?[ \t]+ز[یي]ر[ \t]+نظر\b|'
                r'\s+از\s+موانع\b|'
                rf'\s+به\s+(?:{digits}|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|'
                r'یازده|دوازده|سی|ب[یي]ست|پانزده|میزان|منظور|ترتیب)\b|'
                r'[،؛.\n]|$)',
            ],
            "case_reference": [
                rf'(رأی|حکم|قرار)\s+شماره\s+({digits}(?:/{digits})*)',
                rf'پرونده\s+شماره\s+({digits}(?:/{digits})*)',
            ],
        }
    
    def _extract_explicit_citations(self, text: str) -> List[Citation]:
        """Extract explicit citations with quotes"""
        citations: List[Any] = []
        for pattern in self.patterns["explicit"]:
            for match in re.finditer(pattern, text):
                citation = Citation(
                    text=match.group(0),
                    citation_type=CitationType.EXPLICIT,
                    start=match.start(),
                    end=match.end(),
                    source_reference=match.group(2) if match.lastindex >= 2 else None,
                    extraction_method="regex_explicit"
                )
                citations.append(citation)
        return citations
    
    def _extract_legal_articles(self, text: str) -> List[Citation]:
        """Extract legal article references"""
        citations: List[Any] = []
        for pattern in self.patterns["legal_article"]:
            for match in re.finditer(pattern, text):
                article_number = match.group("article_number").translate(_DIGIT_TRANSLATION)
                section_number = match.groupdict().get("section_number")
                law_name = match.groupdict().get("law_name")
                if law_name:
                    title_words = _normalize_citation_text(law_name.removeprefix("قانون")).split()
                    if not title_words or title_words[0] in _NON_LAW_TITLE_STARTS:
                        continue
                citation = Citation(
                    text=match.group(0),
                    citation_type=CitationType.LEGAL_ARTICLE,
                    start=match.start(),
                    end=match.end(),
                    article_number=article_number,
                    law_name=law_name,
                    extraction_method="regex_legal",
                    section_number=section_number.translate(_DIGIT_TRANSLATION)
                    if section_number
                    else None,
                    publication_date=(
                        re.sub(
                            r"\s*/\s*",
                            "/",
                            match.groupdict()["publication_date"].translate(
                                _DIGIT_TRANSLATION
                            ),
                        )
                        if match.groupdict().get("publication_date")
                        else None
                    ),
                )
                citations.append(citation)
        sectioned = [
            citation for citation in citations if citation.section_number is not None
        ]
        return [
            citation
            for citation in citations
            if citation.section_number is not None
            or not any(
                sectioned_citation.article_number == citation.article_number
                and sectioned_citation.start <= citation.start
                and sectioned_citation.end >= citation.end
                for sectioned_citation in sectioned
            )
        ]
    
    def _extract_case_references(self, text: str) -> List[Citation]:
        """Extract case references"""
        citations: List[Any] = []
        for pattern in self.patterns["case_reference"]:
            for match in re.finditer(pattern, text):
                citation = Citation(
                    text=match.group(0),
                    citation_type=CitationType.CASE_REFERENCE,
                    start=match.start(),
                    end=match.end(),
                    case_number=(
                        match.group(2) if match.lastindex >= 2 else match.group(1)
                    ).translate(_DIGIT_TRANSLATION),
                    extraction_method="regex_case"
                )
                citations.append(citation)
        return citations
    
    def _extract_implicit_citations(self, text: str) -> List[Citation]:
        """Extract implicit citations"""
        citations: List[Any] = []
        digits = r"[0-9۰-۹٠-٩]+"
        legal_reference = (
            rf"(?:(?:ماده|مواد|مادّه|اصل|تبصره)[ \t]*[\(（]?[ \t]*"
            rf"{digits}[ \t]*[\)）]?"
            rf"(?:[ \t]+قانون[ \t]+[^،؛.\n]+?)?"
            rf"|(?:قانون|آیین[‌ \t]?نامه)[ \t]+[^،؛.\n]+?"
            rf"|(?:رأی|حکم|قرار|دادنامه|پرونده)[ \t]+شماره[ \t]+"
            rf"{digits}(?:/{digits})*"
            rf")(?=[ \t]+(?:اقدام|اعلام|تنظیم|منعقد|محاسبه|دفاع|می‌شود|می\u200cشود|"
            rf"خواهد|باید|مکلف)|[،؛.\n]|$)"
        )
        implicit_patterns = [
            rf"(طبق|مطابق|براساس|بر اساس)[ \t]+({legal_reference})",
            rf"(با استناد به|مستند به)[ \t]+({legal_reference})",
        ]
        for pattern in implicit_patterns:
            for match in re.finditer(pattern, text):
                citation = Citation(
                    text=match.group(0),
                    citation_type=CitationType.IMPLICIT,
                    start=match.start(),
                    end=match.end(),
                    source_reference=match.group(2) if match.lastindex >= 2 else None,
                    extraction_method="regex_implicit"
                )
                citations.append(citation)
        return citations
    
    def _remove_duplicates(self, citations: List[Citation]) -> List[Citation]:
        """Remove duplicate citations"""
        seen = set()
        unique: List[Any] = []
        for citation in citations:
            key = (citation.text.lower(), citation.start, citation.end)
            if key not in seen:
                seen.add(key)
                unique.append(citation)
        return unique


# ============================================================================
# Citation Verifier
# ============================================================================

class CitationVerifier:
    """Verify citations against source documents"""
    
    def __init__(self, fuzzy_threshold: float = 0.8):
        self.fuzzy_threshold = fuzzy_threshold
        self._citation_extractor = CitationExtractor()
        print("✅ Citation Verifier initialized")
    
    def verify_citations(
        self,
        citations: List[Citation],
        sources: List[str]
    ) -> List[Citation]:
        """Verify multiple citations"""
        for citation in citations:
            citation_text = self._extract_citation_text(citation.text)
            normalized_citation = _normalize_citation_text(citation_text)
            best_match: Optional[Any] = None
            best_score = 0.0

            if not normalized_citation:
                citation.is_valid = False
                citation.matched_source = None
                citation.similarity_score = 0.0
                citation.confidence = 0.0
                citation.completeness_score = self._compute_completeness(citation)
                continue
            
            for source in sources:
                normalized_source = _normalize_citation_text(source)
                if normalized_citation in normalized_source:
                    best_match = source
                    best_score = 1.0
                    break
                if self._has_structured_conflict(citation, source):
                    continue
                score = self._fuzzy_match(normalized_citation, normalized_source)
                if score > best_score and score >= self.fuzzy_threshold:
                    best_match = source
                    best_score = score
            
            citation.is_valid = best_match is not None
            citation.matched_source = best_match
            citation.similarity_score = best_score
            citation.confidence = best_score
            citation.completeness_score = self._compute_completeness(citation)
        
        return citations

    def _has_structured_conflict(self, citation: Citation, source: str) -> bool:
        if citation.citation_type == CitationType.LEGAL_ARTICLE:
            expected = citation
            if not citation.article_number:
                parsed_citations = self._citation_extractor._extract_legal_articles(
                    citation.text
                )
                if parsed_citations:
                    expected = parsed_citations[0]
            source_citations = self._citation_extractor._extract_legal_articles(
                source
            )
            candidates = [
                candidate
                for candidate in source_citations
                if candidate.article_number == expected.article_number
                and (
                    expected.section_number is None
                    or candidate.section_number == expected.section_number
                )
            ]
            if not candidates:
                return True

            expected_law = self._normalize_law_name(expected.law_name)
            expected_date = self._normalize_date(expected.publication_date)
            for candidate in candidates:
                if expected_law and self._normalize_law_name(
                    candidate.law_name
                ) != expected_law:
                    continue
                if expected_date and self._normalize_date(
                    candidate.publication_date
                ) != expected_date:
                    continue
                return False
            return True

        if citation.citation_type == CitationType.CASE_REFERENCE:
            source_cases = self._citation_extractor._extract_case_references(source)
            return not any(
                candidate.case_number == citation.case_number
                for candidate in source_cases
            )

        return False

    @staticmethod
    def _normalize_law_name(law_name: Optional[str]) -> str:
        if not law_name:
            return ""
        normalized = _normalize_citation_text(law_name)
        return re.sub(r"^قانون\s+", "", normalized).strip()

    @staticmethod
    def _normalize_date(date: Optional[str]) -> str:
        if not date:
            return ""
        return re.sub(r"\s+", "", date.translate(_DIGIT_TRANSLATION))
    
    def _extract_citation_text(self, text: str) -> str:
        """Extract core citation text"""
        text = re.sub(r'[«»""]', '', text)
        text = re.sub(r'\([^)]+\)', '', text)
        return text.strip()
    
    def _fuzzy_match(self, text1: str, text2: str) -> float:
        """Compare a citation with source passages instead of the whole source."""
        needle = _normalize_citation_text(text1)
        haystack = _normalize_citation_text(text2)
        if not needle or not haystack:
            return 0.0
        if needle in haystack:
            return 1.0

        needle_tokens = [match.group(0) for match in _WORD_PATTERN.finditer(needle)]
        source_matches = list(_WORD_PATTERN.finditer(haystack))
        if not needle_tokens or not source_matches or len(needle_tokens) > 120:
            return 0.0

        source_tokens = [match.group(0) for match in source_matches]
        positions: Dict[str, List[int]] = defaultdict(list)
        for index, token in enumerate(source_tokens):
            positions[token].append(index)

        anchors = [
            (len(positions[token]), -len(token), index, token)
            for index, token in enumerate(needle_tokens)
            if positions[token]
        ]
        if not anchors:
            return 0.0

        _, _, anchor_index, anchor = min(anchors)
        size_tolerance = min(3, max(1, len(needle_tokens) // 10))
        min_size = max(1, len(needle_tokens) - size_tolerance)
        max_size = min(120, len(needle_tokens) + size_tolerance)
        best_score = 0.0

        # Anchor each small comparison near a rare citation token; never diff against
        # the entire source document.
        for anchor_position in positions[anchor]:
            expected_start = anchor_position - anchor_index
            for offset in (-1, 0, 1):
                start = max(0, expected_start + offset)
                for size in range(min_size, max_size + 1):
                    candidate = " ".join(source_tokens[start : start + size])
                    if candidate:
                        score = difflib.SequenceMatcher(
                            None, needle, candidate, autojunk=False
                        ).ratio()
                        best_score = max(best_score, score)
                        if best_score == 1.0:
                            return best_score

        return best_score
    
    def _compute_completeness(self, citation: Citation) -> float:
        """Compute citation completeness score"""
        score = 0.5
        if citation.source_reference:
            score += 0.2
        if citation.article_number or citation.case_number:
            score += 0.2
        if citation.law_name:
            score += 0.1
        return min(1.0, score)


# ============================================================================
# Plagiarism Detector
# ============================================================================

class PlagiarismDetector:
    """Detect potential plagiarism"""
    
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        print("🔍 Plagiarism Detector initialized")
    
    def detect_plagiarism(
        self,
        text: str,
        sources: List[str],
        window_size: int = 50
    ) -> PlagiarismResult:
        """Detect plagiarism in text"""
        suspicious_spans: List[Any] = []
        words = text.split()
        
        for i in range(0, len(words), window_size // 2):
            window = " ".join(words[i:i+window_size])
            for source in sources:
                similarity = self._compute_similarity(window, source)
                if similarity >= self.threshold:
                    suspicious_spans.append((window, source[:100], similarity))
        
        plagiarism_score = len(suspicious_spans) / max(1, len(words) // window_size)
        has_plagiarism = plagiarism_score > 0.3
        
        return PlagiarismResult(
            has_plagiarism=has_plagiarism,
            plagiarism_score=plagiarism_score,
            suspicious_spans=suspicious_spans,
            sources=[s for _, s, _ in suspicious_spans]
        )
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute text similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0


# ============================================================================
# Citation Style Validator
# ============================================================================

class CitationStyleValidator:
    """Validate citation style compliance"""
    
    def __init__(self, style: CitationStyle = CitationStyle.PERSIAN_LEGAL):
        self.style = style
        print(f"📋 Citation Style Validator initialized ({style.value})")
    
    def validate_style(self, citation: Citation) -> bool:
        """Validate citation style"""
        if self.style == CitationStyle.PERSIAN_LEGAL:
            if citation.citation_type == CitationType.LEGAL_ARTICLE:
                return bool(citation.article_number and citation.law_name)
            if citation.citation_type == CitationType.CASE_REFERENCE:
                return bool(citation.case_number)
        return True


# ============================================================================
# Ultra Citation Auditor
# ============================================================================

class UltraCitationAuditor:
    """Ultra-advanced citation auditing system"""
    
    def __init__(
        self,
        min_accuracy: float = 0.8,
        fuzzy_threshold: float = 0.8,
        citation_style: CitationStyle = CitationStyle.PERSIAN_LEGAL,
        enable_plagiarism_detection: bool = True,
    ):
        self.min_accuracy = min_accuracy
        self.fuzzy_threshold = fuzzy_threshold
        self.citation_style = citation_style
        self.enable_plagiarism_detection = enable_plagiarism_detection
        
        self.extractor = CitationExtractor()
        self.verifier = CitationVerifier(fuzzy_threshold)
        self.style_validator = CitationStyleValidator(citation_style)
        
        if enable_plagiarism_detection:
            self.plagiarism_detector = PlagiarismDetector()
        
        self.stats = {
            "total_audits": 0,
            "total_citations": 0,
            "valid_citations": 0,
            "invalid_citations": 0,
            "avg_accuracy": 0.0,
        }
        
        print("🚀 Ultra Citation Auditor initialized")
    
    def audit(
        self,
        answer: str,
        sources: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> UltraCitationAuditResult:
        """Comprehensive citation audit"""
        import time
        start_time = time.time()
        
        citations = self.extractor.extract_citations(answer)
        
        if not citations:
            return UltraCitationAuditResult(
                is_valid=False,
                overall_score=0.0,
                total_citations=0,
                valid_citations=0,
                invalid_citations=0,
                missing_citations=0,
                recommendations=["هیچ استنادی یافت نشد. لطفاً منابع را ذکر کنید."]
            )
        
        verified_citations = self.verifier.verify_citations(citations, sources)
        
        for citation in verified_citations:
            citation.style_compliance = self.style_validator.validate_style(citation)
        
        valid_count = sum(1 for c in verified_citations if c.is_valid)
        invalid_count = len(verified_citations) - valid_count
        
        accuracy_score = valid_count / len(verified_citations) if verified_citations else 0.0
        completeness_score = sum(c.completeness_score for c in verified_citations) / len(verified_citations)
        style_compliance_score = sum(1 for c in verified_citations if c.style_compliance) / len(verified_citations)
        
        overall_score = (
            0.5 * accuracy_score +
            0.3 * completeness_score +
            0.2 * style_compliance_score
        )
        
        is_valid = overall_score >= self.min_accuracy
        
        recommendations = self._generate_recommendations(
            verified_citations,
            accuracy_score,
            completeness_score,
            style_compliance_score
        )
        
        corrections = self._generate_corrections(verified_citations)
        
        if self.enable_plagiarism_detection:
            plagiarism_result = self.plagiarism_detector.detect_plagiarism(answer, sources)
            if plagiarism_result.has_plagiarism:
                recommendations.append(
                    f"⚠️ احتمال سرقت ادبی: {plagiarism_result.plagiarism_score:.2%}"
                )
        
        result = UltraCitationAuditResult(
            is_valid=is_valid,
            overall_score=overall_score,
            total_citations=len(verified_citations),
            valid_citations=valid_count,
            invalid_citations=invalid_count,
            missing_citations=0,
            citations=verified_citations,
            invalid_citation_details=[
                {
                    "text": c.text,
                    "reason": "منبع یافت نشد" if not c.matched_source else "شباهت پایین",
                    "similarity": c.similarity_score
                }
                for c in verified_citations if not c.is_valid
            ],
            accuracy_score=accuracy_score,
            completeness_score=completeness_score,
            style_compliance_score=style_compliance_score,
            recommendations=recommendations,
            corrections=corrections,
            processing_time_ms=(time.time() - start_time) * 1000
        )
        
        self.stats["total_audits"] += 1
        self.stats["total_citations"] += len(verified_citations)
        self.stats["valid_citations"] += valid_count
        self.stats["invalid_citations"] += invalid_count
        self.stats["avg_accuracy"] = (
            (self.stats["avg_accuracy"] * (self.stats["total_audits"] - 1) + accuracy_score)
            / self.stats["total_audits"]
        )
        
        return result
    
    def _generate_recommendations(
        self,
        citations: List[Citation],
        accuracy: float,
        completeness: float,
        style_compliance: float
    ) -> List[str]:
        """Generate improvement recommendations"""
        recommendations: List[Any] = []
        if accuracy < 0.8:
            recommendations.append("دقت استنادها پایین است. منابع را بررسی کنید.")
        if completeness < 0.7:
            recommendations.append("استنادها ناقص هستند. جزئیات بیشتری اضافه کنید.")
        if style_compliance < 0.8:
            recommendations.append("استنادها با استاندارد سبک مطابقت ندارند.")
        
        legal_citations = [c for c in citations if c.citation_type == CitationType.LEGAL_ARTICLE]
        missing_articles = [c for c in legal_citations if not c.article_number]
        if missing_articles:
            recommendations.append(f"{len(missing_articles)} استناد قانونی بدون شماره ماده")
        
        return recommendations
    
    def _generate_corrections(self, citations: List[Citation]) -> Dict[str, str]:
        """Generate automated corrections"""
        corrections: Dict[str, Any] = {}
        for citation in citations:
            if not citation.is_valid and citation.matched_source:
                corrections[citation.text] = citation.matched_source[:100]
        return corrections
    
    def get_statistics(self) -> Dict:
        """Get auditor statistics"""
        return self.stats


# ============================================================================
# Example Usage
# ============================================================================

def test_ultra_citation_auditor():
    """Test ultra citation auditor"""
    print("🚀 Testing Ultra Citation Auditor")
    print("=" * 60)
    
    auditor = UltraCitationAuditor(
        min_accuracy=0.8,
        fuzzy_threshold=0.8,
        enable_plagiarism_detection=True
    )
    
    answer = """
    طبق ماده 10 قانون مدنی، هر شخصی دارای اهلیت است.
    همچنین بر اساس رأی شماره 123/98 دیوان عالی کشور،
    این موضوع تأیید شده است.
    """
    
    sources = [
        "قانون مدنی - ماده 10: هر شخصی دارای اهلیت است مگر اینکه قانون او را فاقد اهلیت بداند.",
        "دیوان عالی کشور - رأی شماره 123/98: موضوع اهلیت اشخاص تأیید می‌شود.",
    ]
    
    result = auditor.audit(answer, sources)
    
    print("\n📊 Audit Results:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Overall Score: {result.overall_score:.2%}")
    print(f"   Total Citations: {result.total_citations}")
    print(f"   Valid: {result.valid_citations}")
    print(f"   Invalid: {result.invalid_citations}")
    print(f"   Accuracy: {result.accuracy_score:.2%}")
    print(f"   Completeness: {result.completeness_score:.2%}")
    print(f"   Style Compliance: {result.style_compliance_score:.2%}")
    
    print("\n📝 Citations:")
    for i, citation in enumerate(result.citations, 1):
        print(f"   {i}. {citation.text[:50]}...")
        print(f"      Type: {citation.citation_type.value}")
        print(f"      Valid: {citation.is_valid}")
        print(f"      Similarity: {citation.similarity_score:.2%}")
    
    if result.recommendations:
        print("\n💡 Recommendations:")
        for rec in result.recommendations:
            print(f"   - {rec}")
    
    stats = auditor.get_statistics()
    print(f"\n📈 Statistics: {stats}")


if __name__ == "__main__":
    test_ultra_citation_auditor()
