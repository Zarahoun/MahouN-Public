"""
Ultra Legal Precedent Agent - Enterprise-Grade Precedent Search
================================================================
Agent پیشرفته برای یافتن آراء و احکام مشابه

Features:
- Semantic Similarity Search
- Legal Principle Extraction
- Case Comparison Analysis
- Precedent Ranking
- Recommendation Generation
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_agent import UltraBaseAgent, AgentConfig

logger = logging.getLogger(__name__)


class PrecedentType(str, Enum):
    """Types of legal precedents"""
    SUPREME_COURT = "supreme_court"      # دیوان عالی کشور
    APPEAL_COURT = "appeal_court"        # تجدیدنظر
    GENERAL_COURT = "general_court"      # عمومی
    ADMINISTRATIVE = "administrative"    # دیوان عدالت اداری
    UNKNOWN = "unknown"


class RelevanceLevel(str, Enum):
    """Relevance levels for precedents"""
    HIGHLY_RELEVANT = "highly_relevant"  # بسیار مرتبط
    RELEVANT = "relevant"                # مرتبط
    SOMEWHAT_RELEVANT = "somewhat"       # تا حدی مرتبط
    LOW_RELEVANCE = "low"               # کم ارتباط


@dataclass
class PrecedentAgentConfig(AgentConfig):
    """Configuration for precedent agent"""
    top_k: int = 20
    min_similarity: float = 0.4
    extract_principles: bool = True
    generate_comparison: bool = True
    max_precedents: int = 10


@dataclass
class LegalPrecedent:
    """A legal precedent/verdict"""
    doc_id: str
    content: str
    similarity: float
    precedent_type: PrecedentType
    relevance: RelevanceLevel
    court_name: Optional[str] = None
    case_number: Optional[str] = None
    date: Optional[str] = None
    legal_principles: List[str] = field(default_factory=list)


@dataclass
class LegalPrinciple:
    """An extracted legal principle"""
    text: str
    source_doc: str
    confidence: float
    category: Optional[str] = None


class UltraPrecedentAgent(UltraBaseAgent):
    """
    Enterprise-grade legal precedent search agent.
    
    این agent آراء و احکام مشابه را جستجو می‌کند:
    1. جستجوی معنایی در پایگاه آراء
    2. استخراج اصول حقوقی
    3. مقایسه با پرونده فعلی
    4. رتبه‌بندی و توصیه
    """
    
    # Keywords for precedent detection
    PRECEDENT_KEYWORDS = ["رأی", "حکم", "دادنامه", "دادگاه", "شعبه"]
    
    # Court type detection
    COURT_PATTERNS = {
        PrecedentType.SUPREME_COURT: ["دیوان عالی", "دیوان عالی کشور"],
        PrecedentType.APPEAL_COURT: ["تجدیدنظر", "دادگاه تجدیدنظر"],
        PrecedentType.ADMINISTRATIVE: ["دیوان عدالت", "عدالت اداری"],
        PrecedentType.GENERAL_COURT: ["دادگاه عمومی", "دادگاه حقوقی", "دادگاه کیفری"]
    }
    
    def __init__(self, config: Optional[PrecedentAgentConfig] = None):
        super().__init__(
            name="ultra_precedent",
            config=config or PrecedentAgentConfig()
        )
        self._rag_service = None
        
        self._precedent_metrics = {
            "searches_performed": 0,
            "precedents_found": 0,
            "principles_extracted": 0,
            "avg_similarity": 0.0,
        }
    
    async def _initialize_impl(self):
        """Initialize components"""
        self.logger.info("Initializing UltraPrecedentAgent...")
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            self._rag_service = await create_hybrid_rag_service()
            self.logger.info("✅ RAG Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ RAG Service not available: {e}")
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Search for legal precedents.
        
        Args:
            input_data: {
                "case_description": str,  # Description of current case
                "case_type": str,         # Type of case
                "legal_issues": list,     # Legal issues involved
                "court_preference": str   # Preferred court type
            }
        """
        case_description = input_data.get("case_description", "")
        case_type = input_data.get("case_type", "")
        legal_issues = input_data.get("legal_issues", [])
        court_preference = input_data.get("court_preference")
        
        if not case_description:
            raise ValueError("Case description is required")
        
        # Build search query
        query = self._build_search_query(case_description, case_type, legal_issues)
        
        # Search for precedents
        search_results = await self._search_precedents(query, correlation_id)
        
        # Filter and rank precedents
        precedents = self._process_results(search_results, court_preference)
        
        # Extract legal principles
        principles: List[Any] = []
        if self.config.extract_principles:
            principles = self._extract_principles(precedents)
        
        # Generate comparison analysis
        comparison: Optional[Any] = None
        if self.config.generate_comparison and precedents:
            comparison = self._generate_comparison(case_description, precedents)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(precedents, principles)
        
        # Update metrics
        self._precedent_metrics["searches_performed"] += 1
        self._precedent_metrics["precedents_found"] += len(precedents)
        self._precedent_metrics["principles_extracted"] += len(principles)
        if precedents:
            avg_sim = sum(p.similarity for p in precedents) / len(precedents)
            n = self._precedent_metrics["searches_performed"]
            self._precedent_metrics["avg_similarity"] = (
                (self._precedent_metrics["avg_similarity"] * (n-1) + avg_sim) / n
            )
        
        return {
            "precedents": [self._precedent_to_dict(p) for p in precedents],
            "legal_principles": [self._principle_to_dict(p) for p in principles],
            "comparison": comparison,
            "recommendations": recommendations,
            "metadata": {
                "total_precedents": len(precedents),
                "total_principles": len(principles),
                "avg_similarity": round(sum(p.similarity for p in precedents) / len(precedents), 3) if precedents else 0,
                "court_types": list(set(p.precedent_type.value for p in precedents))
            }
        }
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Fallback: return empty results with message"""
        self.logger.warning(f"[{correlation_id}] Using FALLBACK mode")
        
        return {
            "precedents": [],
            "legal_principles": [],
            "comparison": None,
            "recommendations": ["سرویس جستجوی آراء در دسترس نیست. لطفاً بعداً تلاش کنید."],
            "metadata": {"fallback_used": True}
        }
    
    def _build_search_query(
        self,
        case_description: str,
        case_type: str,
        legal_issues: List[str]
    ) -> str:
        """Build optimized search query"""
        parts = [case_description[:300]]
        
        if case_type:
            parts.append(case_type)
        
        if legal_issues:
            parts.extend(legal_issues[:3])
        
        # Add precedent keywords
        parts.append("رأی دادگاه")
        
        return " ".join(parts)
    
    async def _search_precedents(
        self,
        query: str,
        correlation_id: Optional[str]
    ) -> List[Dict]:
        """Search for precedents using RAG"""
        if not self._rag_service:
            return []
        
        try:
            from mahoun.rag.hybrid_rag_service import RAGMode
            
            result = await self._rag_service.retrieve(
                query=query,
                mode=RAGMode.AUTO,
                top_k=self.config.top_k
            )
            
            return [
                {
                    "content": r.content,
                    "doc_id": r.doc_id,
                    "score": r.score,
                    "metadata": getattr(r, 'metadata', {})
                }
                for r in result.results
                if r.score >= self.config.min_similarity
            ]
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] Search failed: {e}")
            return []
    
    def _process_results(
        self,
        results: List[Dict],
        court_preference: Optional[str]
    ) -> List[LegalPrecedent]:
        """Process and filter search results"""
        precedents: List[Any] = []
        for result in results:
            content = result["content"]
            
            # Check if it's a precedent
            if not any(kw in content for kw in self.PRECEDENT_KEYWORDS):
                continue
            
            # Detect court type
            court_type = self._detect_court_type(content)
            
            # Filter by preference
            if court_preference:
                try:
                    pref_type = PrecedentType(court_preference)
                    if court_type != pref_type and court_type != PrecedentType.UNKNOWN:
                        continue
                except ValueError:
                    pass
            
            # Determine relevance
            relevance = self._assess_relevance(result["score"])
            
            # Extract court name
            court_name = self._extract_court_name(content)
            
            precedents.append(LegalPrecedent(
                doc_id=result["doc_id"],
                content=content[:500],
                similarity=result["score"],
                precedent_type=court_type,
                relevance=relevance,
                court_name=court_name
            ))
        
        # Sort by similarity
        precedents.sort(key=lambda x: x.similarity, reverse=True)
        
        return precedents[:self.config.max_precedents]
    
    def _detect_court_type(self, content: str) -> PrecedentType:
        """Detect court type from content"""
        content_lower = content.lower()
        
        for court_type, patterns in self.COURT_PATTERNS.items():
            if any(p in content_lower for p in patterns):
                return court_type
        
        return PrecedentType.UNKNOWN
    
    def _assess_relevance(self, score: float) -> RelevanceLevel:
        """Assess relevance level based on score"""
        if score >= 0.8:
            return RelevanceLevel.HIGHLY_RELEVANT
        elif score >= 0.6:
            return RelevanceLevel.RELEVANT
        elif score >= 0.4:
            return RelevanceLevel.SOMEWHAT_RELEVANT
        return RelevanceLevel.LOW_RELEVANCE
    
    def _extract_court_name(self, content: str) -> Optional[str]:
        """Extract court name from content"""
        for patterns in self.COURT_PATTERNS.values():
            for pattern in patterns:
                if pattern in content:
                    # Find surrounding context
                    idx = content.find(pattern)
                    start = max(0, idx - 20)
                    end = min(len(content), idx + len(pattern) + 30)
                    return content[start:end].strip()
        return None
    
    def _extract_principles(self, precedents: List[LegalPrecedent]) -> List[LegalPrinciple]:
        """Extract legal principles from precedents"""
        principles: List[Any] = []
        principle_keywords = ["اصل", "قاعده", "ماده", "مقرر است", "حکم قانون"]
        
        for precedent in precedents[:5]:
            content = precedent.content
            
            for keyword in principle_keywords:
                if keyword in content:
                    # Extract sentence containing keyword
                    sentences = content.split(".")
                    for sent in sentences:
                        if keyword in sent and len(sent) > 20:
                            principles.append(LegalPrinciple(
                                text=sent.strip()[:200],
                                source_doc=precedent.doc_id,
                                confidence=precedent.similarity * 0.9
                            ))
                            break
        
        return principles[:10]
    
    def _generate_comparison(
        self,
        case_description: str,
        precedents: List[LegalPrecedent]
    ) -> Dict[str, Any]:
        """Generate comparison analysis"""
        if not precedents:
            return None
        
        top_precedent = precedents[0]
        
        return {
            "most_similar": {
                "doc_id": top_precedent.doc_id,
                "similarity": round(top_precedent.similarity, 3),
                "court": top_precedent.court_name
            },
            "similarity_distribution": {
                "high": sum(1 for p in precedents if p.relevance == RelevanceLevel.HIGHLY_RELEVANT),
                "medium": sum(1 for p in precedents if p.relevance == RelevanceLevel.RELEVANT),
                "low": sum(1 for p in precedents if p.relevance in [RelevanceLevel.SOMEWHAT_RELEVANT, RelevanceLevel.LOW_RELEVANCE])
            },
            "court_distribution": {
                court_type.value: sum(1 for p in precedents if p.precedent_type == court_type)
                for court_type in PrecedentType
                if sum(1 for p in precedents if p.precedent_type == court_type) > 0
            }
        }
    
    def _generate_recommendations(
        self,
        precedents: List[LegalPrecedent],
        principles: List[LegalPrinciple]
    ) -> List[str]:
        """Generate recommendations based on findings"""
        recommendations: List[Any] = []
        if not precedents:
            recommendations.append("آرای مشابه یافت نشد. توصیه می‌شود با کلیدواژه‌های متفاوت جستجو شود.")
            return recommendations
        
        # High similarity precedents
        high_sim = [p for p in precedents if p.relevance == RelevanceLevel.HIGHLY_RELEVANT]
        if high_sim:
            recommendations.append(
                f"یافت {len(high_sim)} رأی با شباهت بالا - می‌تواند به عنوان سابقه قضایی استفاده شود."
            )
        
        # Supreme court precedents
        supreme = [p for p in precedents if p.precedent_type == PrecedentType.SUPREME_COURT]
        if supreme:
            recommendations.append(
                f"یافت {len(supreme)} رأی از دیوان عالی کشور - دارای اعتبار بالا برای استناد."
            )
        
        # Legal principles
        if principles:
            recommendations.append(
                f"استخراج {len(principles)} اصل حقوقی - برای تقویت استدلال استفاده شود."
            )
        
        return recommendations
    
    def _precedent_to_dict(self, p: LegalPrecedent) -> Dict:
        return {
            "doc_id": p.doc_id,
            "content": p.content[:300],
            "similarity": round(p.similarity, 3),
            "court_type": p.precedent_type.value,
            "relevance": p.relevance.value,
            "court_name": p.court_name
        }
    
    def _principle_to_dict(self, p: LegalPrinciple) -> Dict:
        return {
            "text": p.text,
            "source": p.source_doc,
            "confidence": round(p.confidence, 3)
        }
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        return {
            "components": {"rag_service": self._rag_service is not None},
            "metrics": self._precedent_metrics.copy()
        }
