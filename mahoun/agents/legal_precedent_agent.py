"""
Legal Precedent Agent
=====================

Agent برای یافتن آراء و احکام مشابه
"""

from typing import Any, Dict, List, Optional
import logging

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class LegalPrecedentAgent(BaseAgent):
    """
    Agent برای یافتن آراء و احکام مشابه
    
    ویژگی‌ها:
    - جستجو در database آراء
    - تحلیل similarity
    - استخراج اصول حقوقی
    - مقایسه با پرونده فعلی
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("legal_precedent_agent", config)
        self.rag_service = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            
            self.rag_service = await create_hybrid_rag_service()
            
            self._initialized = True
            self.logger.info("✅ LegalPrecedentAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize LegalPrecedentAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        یافتن آراء مشابه
        
        Args:
            input_data: شامل:
                - case_description: شرح پرونده
                - case_type: نوع پرونده (optional)
                - legal_issues: مسائل حقوقی (optional)
        
        Returns:
            نتیجه شامل:
                - precedents: آراء مشابه
                - similarity_scores: نمرات similarity
                - legal_principles: اصول حقوقی استخراج شده
                - recommendations: توصیه‌ها
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            case_description = input_data.get("case_description", "")
            case_type = input_data.get("case_type", "")
            legal_issues = input_data.get("legal_issues", [])
            
            # Build search query
            query = self._build_precedent_query(case_description, case_type, legal_issues)
            
            # Search for precedents
            result = await self.rag_service.retrieve(
                query=query,
                top_k=15
            )
            
            # Filter for verdicts/precedents
            precedents = self._filter_precedents(result.results)
            
            # Extract legal principles
            legal_principles = self._extract_legal_principles(precedents)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(precedents, legal_principles)
            
            return {
                "success": True,
                "precedents": precedents,
                "legal_principles": legal_principles,
                "recommendations": recommendations,
                "metadata": {
                    "total_precedents": len(precedents),
                    "avg_similarity": sum(p.get("similarity", 0) for p in precedents) / len(precedents) if precedents else 0
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    def _build_precedent_query(
        self,
        case_description: str,
        case_type: str,
        legal_issues: List[str]
    ) -> str:
        """Build query for precedent search"""
        query_parts = [case_description]
        
        if case_type:
            query_parts.append(f"نوع: {case_type}")
        
        if legal_issues:
            query_parts.extend(legal_issues)
        
        # Add precedent keywords
        query_parts.append("رأی دادگاه")
        query_parts.append("حکم")
        
        return " ".join(query_parts)
    
    def _filter_precedents(self, results: List[Any]) -> List[Dict[str, Any]]:
        """Filter and format precedents with legal-aware ranking"""
        precedents: List[Any] = []
        for result in results:
            content = result.content.lower()
            
            # Check if it's a verdict/precedent
            verdict_keywords = ["رأی", "حکم", "دادگاه", "دادگاه تجدیدنظر", "دیوان عالی"]
            if any(kw in content for kw in verdict_keywords):
                # Extract legal metadata if available
                legal_metadata = result.metadata.get("legal_metadata", {})
                court_rank = legal_metadata.get("court_rank", 6)  # Default to lowest rank
                authority_score = legal_metadata.get("authority_score", 0.0)
                statute_status = legal_metadata.get("statute_status", "active")
                
                # Skip repealed or superseded precedents
                if statute_status in ["repealed", "superseded"]:
                    continue
                
                # Calculate enhanced score based on court hierarchy and authority
                enhanced_score = result.score
                
                # Court hierarchy boost (lower rank number = higher authority)
                if court_rank == 1:  # Supreme Court
                    enhanced_score += 0.3
                elif court_rank == 2:  # Appeals Court
                    enhanced_score += 0.2
                elif court_rank == 3:  # First Instance
                    enhanced_score += 0.1
                
                # Authority score boost
                enhanced_score += authority_score * 0.2
                
                # Cap at 1.0
                enhanced_score = min(1.0, enhanced_score)
                
                precedents.append({
                    "content": result.content[:500],
                    "source": result.doc_id,
                    "similarity": result.score,
                    "enhanced_score": enhanced_score,
                    "court_rank": court_rank,
                    "authority_score": authority_score,
                    "statute_status": statute_status,
                    "metadata": result.metadata or {}
                })
        
        # Sort by enhanced score (court hierarchy + authority + similarity)
        precedents.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
        
        return precedents[:10]  # Top 10
    
    def _extract_legal_principles(
        self,
        precedents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """استخراج اصول حقوقی از آراء"""
        principles: List[Any] = []
        legal_keywords = ["اصل", "قاعده", "ماده", "بند", "مقررات"]
        
        for precedent in precedents[:5]:
            content = precedent.get("content", "")
            
            # Extract legal references
            for keyword in legal_keywords:
                if keyword in content:
                    # Simple extraction (can be improved)
                    principles.append({
                        "principle": content[:200],
                        "source": precedent.get("source"),
                        "relevance": precedent.get("similarity", 0)
                    })
                    break
        
        return principles[:5]
    
    def _generate_recommendations(
        self,
        precedents: List[Dict[str, Any]],
        principles: List[Dict[str, Any]]
    ) -> List[str]:
        """تولید توصیه‌ها بر اساس آراء"""
        recommendations: List[Any] = []
        if precedents:
            high_similarity = [p for p in precedents if p.get("similarity", 0) > 0.8]
            if high_similarity:
                recommendations.append(f"یافت {len(high_similarity)} رأی با similarity بالا - می‌تواند مفید باشد")
        
        if principles:
            recommendations.append("اصول حقوقی مرتبط استخراج شد - برای استدلال استفاده کنید")
        
        if not precedents:
            recommendations.append("آرای مشابه یافت نشد - نیاز به تحلیل بیشتر")
        
        return recommendations

