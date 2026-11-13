"""
Contract Clause Reasoning Engine
================================

موتور تحلیل بندهای قرارداد و تولید پاسخ مستند
از کامپوننت‌های موجود استفاده می‌کند:
- ContractAgent برای تحلیل
- HybridRAGService برای جستجو
- UltraReasoningService برای reasoning
"""

from typing import Any, Dict, List, Optional
import logging

from .base_engine import BaseDomainEngine

logger = logging.getLogger(__name__)


class ContractClauseReasoningEngine(BaseDomainEngine):
    """
    موتور تحلیل بندهای قرارداد و تولید پاسخ مستند
    
    این engine از کامپوننت‌های موجود استفاده می‌کند:
    - ContractAgent: برای تحلیل قرارداد
    - HybridRAGService: برای جستجو در بندها
    - UltraReasoningService: برای reasoning
    - CitationEngine: برای ارجاع
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("contract_reasoning", config)
        self.contract_agent = None
        self.rag_service = None
        self.reasoning_service = None
        self.citation_engine = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.agents.contract_agent import ContractAgent
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from mahoun.rag.citation_engine import CitationEngine
            
            self.contract_agent = ContractAgent()
            await self.contract_agent.initialize()
            
            self.rag_service = await create_hybrid_rag_service()
            self.citation_engine = CitationEngine()
            
            try:
                from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
                self.reasoning_service = UltraReasoningService()
            except Exception as e:
                self.logger.warning(f"Could not initialize UltraReasoningService: {e}")
                self.reasoning_service = None
            
            self._initialized = True
            self.logger.info("✅ ContractClauseReasoningEngine fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize ContractClauseReasoningEngine: {e}", exc_info=True)
            raise
    
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحلیل بندهای قرارداد و تولید پاسخ مستند
        
        Args:
            input_data: شامل:
                - query: سؤال درباره بندها
                - clause_number: شماره بند خاص (optional)
                - contract_id: شناسه قرارداد (optional)
        
        Returns:
            نتیجه شامل:
                - answer: پاسخ به سؤال
                - clauses: بندهای مرتبط
                - reasoning: استدلال
                - citations: ارجاعات
                - obligations: تعهدات استخراج شده
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            query = input_data.get("query", "")
            clause_number = input_data.get("clause_number")
            contract_id = input_data.get("contract_id")
            
            # Build enhanced query
            enhanced_query = query
            if clause_number:
                enhanced_query = f"{query} بند {clause_number}"
            
            # Use ContractAgent for analysis
            contract_result = await self.contract_agent.process({
                "query": enhanced_query,
                "top_k": 15
            })
            
            if not contract_result.get("success"):
                return {
                    "success": False,
                    "error": contract_result.get("error", "Unknown error"),
                    "answer": ""
                }
            
            # Extract clauses from citations
            clauses = self._extract_clauses(contract_result.get("citations", []))
            
            # Extract obligations
            obligations = self._extract_obligations(
                contract_result.get("answer", ""),
                contract_result.get("citations", [])
            )
            
            # Build reasoning chain
            reasoning = self._build_reasoning_chain(
                contract_result.get("answer", ""),
                clauses,
                obligations
            )
            
            return {
                "success": True,
                "answer": contract_result.get("answer", ""),
                "clauses": clauses,
                "reasoning": reasoning,
                "citations": contract_result.get("citations", []),
                "obligations": obligations,
                "confidence": contract_result.get("confidence", 0.0),
                "verified": contract_result.get("verified", False),
                "metadata": {
                    **contract_result.get("metadata", {}),
                    "clauses_count": len(clauses),
                    "obligations_count": len(obligations)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Contract reasoning failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "answer": ""
            }
    
    def _extract_clauses(self, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract clauses from citations"""
        clauses: List[Any] = []
        for citation in citations:
            clause_num = citation.get("clause")
            if clause_num:
                clauses.append({
                    "clause_number": clause_num,
                    "doc_id": citation.get("doc_id"),
                    "citation_text": citation.get("citation_text", "")[:200]
                })
        
        return clauses
    
    def _extract_obligations(self, answer: str, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract obligations from answer and citations"""
        obligations: List[Any] = []
        obligation_keywords = ["تعهد", "وظیفه", "مسئولیت", "باید", "می‌بایست"]
        
        for keyword in obligation_keywords:
            if keyword in answer:
                # Extract sentences containing obligation
                sentences = answer.split(".")
                for sentence in sentences:
                    if keyword in sentence:
                        obligations.append({
                            "text": sentence.strip(),
                            "keyword": keyword,
                            "type": "obligation"
                        })
        
        return obligations[:10]  # Top 10
    
    def _build_reasoning_chain(self, answer: str, clauses: List[Dict[str, Any]], obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build reasoning chain"""
        return {
            "steps": [
                {
                    "step": 1,
                    "description": "شناسایی بندهای مرتبط",
                    "result": f"{len(clauses)} بند شناسایی شد"
                },
                {
                    "step": 2,
                    "description": "استخراج تعهدات",
                    "result": f"{len(obligations)} تعهد استخراج شد"
                },
                {
                    "step": 3,
                    "description": "تولید پاسخ",
                    "result": "پاسخ بر اساس بندها و تعهدات تولید شد"
                }
            ],
            "conclusion": answer[:200]
        }

