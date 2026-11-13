"""
Dispute Agent
=============

Advanced agent for detecting and analyzing disputes, contract violations, and risks.
Merges functionality from previous DisputeAgent (MVP) and EnhancedDisputeAgent.
"""

from typing import Any, Dict, List, Optional
import logging
from enum import Enum

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class DisputeType(str, Enum):
    """Types of disputes"""
    FINANCIAL = "financial"
    TEMPORAL = "temporal"
    QUALITY = "quality"
    CONTRACTUAL = "contractual"
    PROCEDURAL = "procedural"
    OTHER = "other"


class DisputeSeverity(str, Enum):
    """Severity level of the dispute"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DisputeAgent(BaseAgent):
    """
    Advanced Agent for Dispute Analysis and Risk Assessment.
    
    Capabilities:
    - Deep analysis using Hybrid RAG and Reasoning
    - Classification of dispute types
    - Severity scoring and prioritization
    - Risk assessment
    - Legal citation extraction (backward compatible)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # Use "dispute_agent" as type to match factory registry
        super().__init__("dispute_agent", config)
        self.rag_service = None
        self.reasoning_service = None
        self.citation_engine = None
        self.query_router = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from mahoun.rag.query_router import QueryRouter
            from mahoun.rag.citation_engine import CitationEngine
            
            self.rag_service = await create_hybrid_rag_service()
            self.query_router = QueryRouter(rag_service=self.rag_service)
            self.citation_engine = CitationEngine()
            
            try:
                from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
                self.reasoning_service = UltraReasoningService()
            except Exception as e:
                self.logger.warning(f"Could not initialize UltraReasoningService: {e}")
                self.reasoning_service = None
            
            self._initialized = True
            self.logger.info("✅ DisputeAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize DisputeAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive dispute analysis.
        
        Args:
            input_data:
                - query: question or text to analyze
                - documents: list of documents (optional)
                - focus_areas: areas to focus on (optional)
        
        Returns:
            Dict containing disputes, violations, risk assessment, references, etc.
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            query = input_data.get("query", "")
            documents = input_data.get("documents", [])
            
            # Step 1: Deep analysis (Extracts disputes, violations, and citations)
            disputes, violations, all_citations = await self._deep_analysis(query, documents)
            
            # Step 2: Classification
            classified_disputes = await self._classify_disputes(disputes)
            
            # Step 3: Severity scoring
            scored_disputes = await self._calculate_severity(classified_disputes)
            
            # Step 4: Legal references (similar to citations but focused on laws)
            legal_refs = await self._find_legal_references(scored_disputes)
            
            # Step 5: Risk assessment
            risk_assessment = await self._assess_risk(scored_disputes, violations)
            
            # Step 6: Recommendations
            recommendations = await self._generate_recommendations(
                scored_disputes,
                risk_assessment
            )
            
            # Extract related clauses (Backward compatibility)
            related_clauses = self._extract_related_clauses(all_citations)
            
            # Transform citations to dict for output (Backward compatibility)
            citations_output = [
                {
                    "doc_id": c.doc_id,
                    "clause": c.clause_number,
                    "citation_text": c.citation_text
                }
                for c in all_citations
            ]
            
            return {
                "success": True,
                # MVP fields
                "disputes": scored_disputes,
                "violations": violations,
                "related_clauses": related_clauses,
                "citations": citations_output,
                
                # Enhanced fields
                "dispute_types": self._summarize_types(scored_disputes),
                "risk_assessment": risk_assessment,
                "legal_references": legal_refs,
                "recommendations": recommendations,
                
                "metadata": {
                    "total_disputes": len(scored_disputes),
                    "total_violations": len(violations),
                    "total_citations": len(all_citations),
                    "critical_count": len([d for d in scored_disputes if d.get("severity") == DisputeSeverity.CRITICAL]),
                    "high_risk": risk_assessment.get("overall_risk") == "high"
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    async def _deep_analysis(
        self,
        query: str,
        documents: List[str]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Any]]:
        """Deep analysis returning disputes, violations, and citations"""
        disputes: List[Any] = []
        violations: List[Any] = []
        all_citations: List[Any] = []
        # Build comprehensive queries
        queries = [
            query,
            f"{query} اختلاف",
            f"{query} نقض تعهد",
            f"{query} مسئولیت",
            f"{query} خسارت"
        ]
        
        # Use top 3 queries for broader context
        for search_query in queries[:3]:
            # Route and Retrieve
            routed = await self.query_router.route(query=search_query, top_k=10)
            
            # 1. Extract Citations (Legacy capability integration)
            if self.citation_engine:
                citation_result = await self.citation_engine.extract_citations(
                    rag_result=routed.rag_result,
                    query=search_query
                )
                all_citations.extend(citation_result.citations)
            
            # 2. Reasoning Analysis
            if self.reasoning_service:
                for result in routed.rag_result.results[:5]:
                    reasoning = await self.reasoning_service.reason(
                        query=f"تحلیل این متن برای شناسایی اختلاف: {result.content[:200]}",
                        context=[result.content]
                    )
                    
                    # Extract disputes from reasoning
                    r_text = str(reasoning).lower()
                    if "dispute" in r_text or "اختلاف" in r_text:
                        disputes.append({
                            "description": result.content[:300],
                            "source": result.doc_id,
                            "score": result.score,
                            "reasoning": str(reasoning)[:200]
                        })
            
            # 3. Violation Detection (Heuristic)
            for result in routed.rag_result.results:
                content_lower = result.content.lower()
                violation_keywords = ["نقض", "تخلف", "عدم رعایت", "مخالفت", "تخطی"]
                if any(kw in content_lower for kw in violation_keywords):
                    violations.append({
                        "description": result.content[:300],
                        "source": result.doc_id,
                        "score": result.score,
                        "type": "violation"
                    })
        
        return disputes, violations, all_citations
    
    async def _classify_disputes(
        self,
        disputes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Classify dispute types"""
        classified: List[Any] = []
        for dispute in disputes:
            description = dispute.get("description", "").lower()
            
            # Financial keywords
            financial_keywords = ["پول", "پرداخت", "خسارت", "مالی", "هزینه", "قیمت"]
            if any(kw in description for kw in financial_keywords):
                dispute["type"] = DisputeType.FINANCIAL
                dispute["type_confidence"] = 0.8
            
            # Temporal keywords
            elif any(kw in description for kw in ["تأخیر", "مهلت", "زمان", "deadline"]):
                dispute["type"] = DisputeType.TEMPORAL
                dispute["type_confidence"] = 0.8
            
            # Quality keywords
            elif any(kw in description for kw in ["کیفیت", "عیب", "نقص", "مشکل فنی"]):
                dispute["type"] = DisputeType.QUALITY
                dispute["type_confidence"] = 0.8
            
            # Contractual keywords
            elif any(kw in description for kw in ["قرارداد", "بند", "شرط", "تعهد"]):
                dispute["type"] = DisputeType.CONTRACTUAL
                dispute["type_confidence"] = 0.7
            
            else:
                dispute["type"] = DisputeType.OTHER
                dispute["type_confidence"] = 0.5
            
            classified.append(dispute)
        
        return classified
    
    async def _calculate_severity(
        self,
        disputes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Calculate severity score"""
        scored: List[Any] = []
        for dispute in disputes:
            base_score = dispute.get("score", 0.5)
            type_weight = {
                DisputeType.FINANCIAL: 1.2,
                DisputeType.TEMPORAL: 1.1,
                DisputeType.QUALITY: 1.0,
                DisputeType.CONTRACTUAL: 1.1,
                DisputeType.PROCEDURAL: 1.0,
                DisputeType.OTHER: 0.9
            }.get(dispute.get("type"), 1.0)
            
            # Check for critical keywords
            description = dispute.get("description", "").lower()
            critical_keywords = ["بحرانی", "فوری", "مهم", "جدی", "خطر"]
            if any(kw in description for kw in critical_keywords):
                severity = DisputeSeverity.CRITICAL
                severity_score = min(1.0, base_score * type_weight * 1.3)
            elif base_score * type_weight > 0.7:
                severity = DisputeSeverity.HIGH
                severity_score = base_score * type_weight
            elif base_score * type_weight > 0.5:
                severity = DisputeSeverity.MEDIUM
                severity_score = base_score * type_weight
            else:
                severity = DisputeSeverity.LOW
                severity_score = base_score * type_weight
            
            dispute["severity"] = severity
            dispute["severity_score"] = severity_score
            scored.append(dispute)
        
        # Sort by severity
        scored.sort(key=lambda x: {
            DisputeSeverity.CRITICAL: 4,
            DisputeSeverity.HIGH: 3,
            DisputeSeverity.MEDIUM: 2,
            DisputeSeverity.LOW: 1
        }.get(x.get("severity"), 0), reverse=True)
        
        return scored
    
    async def _find_legal_references(
        self,
        disputes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find related legal references"""
        legal_refs: List[Any] = []
        for dispute in disputes[:5]:  # Top 5
            query = f"{dispute.get('type')} {dispute.get('description', '')[:100]}"
            
            if self.rag_service:
                result = await self.rag_service.retrieve(
                    query=query,
                    top_k=3
                )
                
                for res in result.results:
                    if any(kw in res.content for kw in ["قانون", "ماده", "بند", "آیین‌نامه"]):
                        legal_refs.append({
                            "dispute_id": dispute.get("source"),
                            "legal_reference": res.content[:200],
                            "source": res.doc_id,
                            "relevance": res.score
                        })
        
        return legal_refs
    
    async def _assess_risk(
        self,
        disputes: List[Dict[str, Any]],
        violations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Assess overall risk"""
        critical_count = len([d for d in disputes if d.get("severity") == DisputeSeverity.CRITICAL])
        high_count = len([d for d in disputes if d.get("severity") == DisputeSeverity.HIGH])
        violation_count = len(violations)
        
        # Calculate overall risk
        risk_score = (
            critical_count * 3 +
            high_count * 2 +
            violation_count * 1.5
        ) / max(1, len(disputes))
        
        if risk_score > 2.5:
            overall_risk = "critical"
        elif risk_score > 1.5:
            overall_risk = "high"
        elif risk_score > 0.8:
            overall_risk = "medium"
        else:
            overall_risk = "low"
        
        return {
            "overall_risk": overall_risk,
            "risk_score": risk_score,
            "critical_disputes": critical_count,
            "high_disputes": high_count,
            "violations": violation_count,
            "recommendation": self._get_risk_recommendation(overall_risk)
        }
    
    def _get_risk_recommendation(self, risk_level: str) -> str:
        """Get recommendation based on risk"""
        recommendations = {
            "critical": "نیاز به اقدام فوری و مشورت با وکیل",
            "high": "نیاز به بررسی دقیق و مستندسازی",
            "medium": "نیاز به نظارت و پیگیری",
            "low": "نیاز به بررسی دوره‌ای"
        }
        return recommendations.get(risk_level, "نیاز به بررسی")
    
    async def _generate_recommendations(
        self,
        disputes: List[Dict[str, Any]],
        risk_assessment: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations: List[Any] = []
        # Based on risk level
        if risk_assessment.get("overall_risk") in ["critical", "high"]:
            recommendations.append("جمع‌آوری و مستندسازی کامل مدارک")
            recommendations.append("مشورت با وکیل متخصص")
        
        # Based on dispute types
        types = [d.get("type") for d in disputes]
        if DisputeType.FINANCIAL in types:
            recommendations.append("بررسی دقیق محاسبات مالی")
        if DisputeType.TEMPORAL in types:
            recommendations.append("بررسی timeline و مهلت‌ها")
        
        # Based on violations
        if risk_assessment.get("violations", 0) > 0:
            recommendations.append("بررسی تعهدات و نقض‌های احتمالی")
        
        return list(set(recommendations))  # Remove duplicates
    
    def _summarize_types(self, disputes: List[Dict[str, Any]]) -> Dict[str, int]:
        """Summarize dispute types count"""
        type_counts: Dict[str, Any] = {}
        for dispute in disputes:
            dispute_type = dispute.get("type", DisputeType.OTHER)
            type_counts[dispute_type.value] = type_counts.get(dispute_type.value, 0) + 1
        return type_counts
        
    def _extract_related_clauses(self, citations: List[Any]) -> List[Dict[str, Any]]:
        """Extract related clauses for backward compatibility"""
        clauses: List[Any] = []
        for citation in citations:
            if citation.clause_number:
                clauses.append({
                    "clause_number": citation.clause_number,
                    "doc_id": citation.doc_id,
                    "doc_title": citation.doc_title,
                    "content": citation.content[:200]
                })
        return clauses
