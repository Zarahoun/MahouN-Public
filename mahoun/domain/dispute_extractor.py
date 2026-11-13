"""
Dispute Extraction Engine
==========================

موتور استخراج اختلافات و نقض تعهدات
از کامپوننت‌های موجود استفاده می‌کند:
- DisputeAgent برای شناسایی
- HybridRAGService برای جستجو
- CitationEngine برای ارجاع
"""

from typing import Any, Dict, List, Optional
import logging

from .base_engine import BaseDomainEngine

logger = logging.getLogger(__name__)


class DisputeExtractionEngine(BaseDomainEngine):
    """
    موتور استخراج اختلافات و نقض تعهدات
    
    این engine از کامپوننت‌های موجود استفاده می‌کند:
    - DisputeAgent: برای شناسایی اختلافات
    - HybridRAGService: برای جستجو
    - CitationEngine: برای ارجاع
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("dispute_extractor", config)
        self.dispute_agent = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.agents.dispute_agent import DisputeAgent
            
            self.dispute_agent = DisputeAgent()
            await self.dispute_agent.initialize()
            
            self._initialized = True
            self.logger.info("✅ DisputeExtractionEngine fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize DisputeExtractionEngine: {e}", exc_info=True)
            raise
    
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        استخراج اختلافات و نقض تعهدات
        
        Args:
            input_data: شامل:
                - query: سؤال یا موضوع
                - documents: لیست مدارک (optional)
                - focus_areas: حوزه‌های تمرکز (optional)
        
        Returns:
            نتیجه شامل:
                - disputes: لیست اختلافات
                - violations: لیست نقض تعهدات
                - related_clauses: بندهای مرتبط
                - severity: سطح اهمیت
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Use DisputeAgent for extraction
            result = await self.dispute_agent.process(input_data)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "disputes": [],
                    "violations": []
                }
            
            # Enhance with severity analysis
            disputes = result.get("disputes", [])
            violations = result.get("violations", [])
            
            # Add severity to disputes
            for dispute in disputes:
                dispute["severity"] = self._calculate_severity(dispute)
            
            # Add severity to violations
            for violation in violations:
                violation["severity"] = self._calculate_severity(violation)
            
            # Sort by severity
            disputes.sort(key=lambda x: x.get("severity", 0), reverse=True)
            violations.sort(key=lambda x: x.get("severity", 0), reverse=True)
            
            return {
                "success": True,
                "disputes": disputes,
                "violations": violations,
                "related_clauses": result.get("related_clauses", []),
                "citations": result.get("citations", []),
                "metadata": {
                    **result.get("metadata", {}),
                    "high_severity_disputes": len([d for d in disputes if d.get("severity", 0) > 0.7]),
                    "high_severity_violations": len([v for v in violations if v.get("severity", 0) > 0.7])
                }
            }
            
        except Exception as e:
            self.logger.error(f"Dispute extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "disputes": [],
                "violations": []
            }
    
    def _calculate_severity(self, item: Dict[str, Any]) -> float:
        """Calculate severity score for dispute/violation"""
        severity_keywords = {
            "critical": ["بحرانی", "فوری", "مهم", "critical", "urgent"],
            "high": ["زیاد", "مهم", "high", "significant"],
            "medium": ["متوسط", "medium", "moderate"],
            "low": ["کم", "low", "minor"]
        }
        
        description = item.get("description", "").lower()
        score = item.get("score", 0.5)
        
        # Adjust based on keywords
        if any(kw in description for kw in severity_keywords["critical"]):
            return min(1.0, score + 0.3)
        elif any(kw in description for kw in severity_keywords["high"]):
            return min(1.0, score + 0.2)
        elif any(kw in description for kw in severity_keywords["medium"]):
            return score
        elif any(kw in description for kw in severity_keywords["low"]):
            return max(0.0, score - 0.2)
        
        return score

