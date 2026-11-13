"""
Delay Agent
===========

Agent برای تحلیل تأخیرات
از کامپوننت‌های موجود استفاده می‌کند:
- HybridRAGService برای جستجو
- TimelineAgent برای timeline
- UltraReasoningService برای تحلیل
"""

from typing import Any, Dict, List, Optional
import logging

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class DelayAgent(BaseAgent):
    """
    Agent برای تحلیل تأخیرات پروژه
    
    این agent از کامپوننت‌های موجود استفاده می‌کند:
    - HybridRAGService: برای جستجو در مدارک
    - TimelineAgent: برای استخراج timeline
    - UltraReasoningService: برای تحلیل تأخیرات
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("delay_agent", config)
        self.rag_service = None
        self.timeline_agent = None
        self.reasoning_service = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies from existing components"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from .timeline_agent import TimelineAgent
            
            self.rag_service = await create_hybrid_rag_service()
            self.timeline_agent = TimelineAgent()
            await self.timeline_agent.initialize()
            
            try:
                from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
                self.reasoning_service = UltraReasoningService()
            except Exception as e:
                self.logger.warning(f"Could not initialize UltraReasoningService: {e}")
                self.reasoning_service = None
            
            self._initialized = True
            self.logger.info("✅ DelayAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize DelayAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحلیل تأخیرات
        
        Args:
            input_data: شامل:
                - project_id: شناسه پروژه
                - baseline_schedule: برنامه پایه (optional)
                - actual_schedule: برنامه واقعی (optional)
                - query: سؤال یا موضوع تحلیل
        
        Returns:
            نتیجه شامل:
                - delays: لیست تأخیرات
                - delay_analysis: تحلیل تأخیرات
                - critical_path: مسیر بحرانی
                - attribution: مسئولیت‌ها
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            project_id = input_data.get("project_id", "")
            baseline_schedule = input_data.get("baseline_schedule", {})
            actual_schedule = input_data.get("actual_schedule", {})
            query = input_data.get("query", "تحلیل تأخیرات")
            
            # Get timeline
            timeline_result = await self.timeline_agent.process({
                "query": query,
                "documents": []
            })
            
            # Search for delay-related information
            delay_queries = [
                f"{query} تأخیر",
                f"{query} مهلت",
                f"{query} زمان"
            ]
            
            all_delays: List[Any] = []
            for search_query in delay_queries:
                rag_result = await self.rag_service.retrieve(
                    query=search_query,
                    top_k=10
                )
                
                delays = self._extract_delays(rag_result.results, timeline_result.get("timeline", []))
                all_delays.extend(delays)
            
            # Analyze delays
            delay_analysis = self._analyze_delays(all_delays, baseline_schedule, actual_schedule)
            
            # Identify critical path
            critical_path = self._identify_critical_path(timeline_result.get("timeline", []))
            
            # Attribute responsibility
            attribution = self._attribute_responsibility(all_delays)
            
            return {
                "success": True,
                "delays": all_delays,
                "delay_analysis": delay_analysis,
                "critical_path": critical_path,
                "attribution": attribution,
                "timeline": timeline_result.get("timeline", []),
                "metadata": {
                    "total_delays": len(all_delays),
                    "total_delay_days": sum(d.get("delay_days", 0) for d in all_delays)
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    def _extract_delays(self, results: list, timeline: list) -> list:
        """Extract delays from results"""
        delays: List[Any] = []
        delay_keywords = ["تأخیر", "delay", "مهلت", "deadline", "زمان"]
        
        for result in results:
            content = result.content.lower()
            if any(kw in content for kw in delay_keywords):
                delays.append({
                    "description": result.content[:200],
                    "source": result.doc_id,
                    "delay_days": self._extract_delay_days(content),
                    "type": "delay"
                })
        
        return delays
    
    def _extract_delay_days(self, text: str) -> int:
        """Extract delay days from text"""
        import re
        
        patterns = [
            r'(\d+)\s*روز\s*تأخیر',
            r'تأخیر\s*(\d+)\s*روز',
            r'delay\s*of\s*(\d+)\s*days'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return 0
    
    def _analyze_delays(self, delays: list, baseline: dict, actual: dict) -> dict:
        """Analyze delays"""
        return {
            "total_delays": len(delays),
            "total_delay_days": sum(d.get("delay_days", 0) for d in delays),
            "average_delay": sum(d.get("delay_days", 0) for d in delays) / len(delays) if delays else 0,
            "baseline_vs_actual": {
                "baseline": baseline,
                "actual": actual
            }
        }
    
    def _identify_critical_path(self, timeline: list) -> list:
        """Identify critical path from timeline"""
        # Simple implementation: return events with dependencies
        critical_path: List[Any] = []
        for event in timeline:
            if event.get("description"):
                critical_path.append({
                    "event": event.get("description", "")[:100],
                    "date": event.get("date"),
                    "sequence": event.get("sequence")
                })
        
        return critical_path[:10]  # Top 10
    
    def _attribute_responsibility(self, delays: list) -> dict:
        """Attribute responsibility for delays"""
        responsibility_keywords = {
            "کارفرما": ["کارفرما", "employer", "owner"],
            "پیمانکار": ["پیمانکار", "contractor"],
            "مشاور": ["مشاور", "consultant"]
        }
        
        attribution = {key: [] for key in responsibility_keywords.keys()}
        
        for delay in delays:
            description = delay.get("description", "").lower()
            for party, keywords in responsibility_keywords.items():
                if any(kw in description for kw in keywords):
                    attribution[party].append(delay)
        
        return attribution

