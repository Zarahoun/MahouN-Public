"""
Delay Analysis Engine
=====================

موتور تحلیل تأخیرات پروژه
از کامپوننت‌های موجود استفاده می‌کند:
- DelayAgent برای تحلیل
- TimelineAnalyzer برای timeline
"""

from typing import Any, Dict, List, Optional
import logging

from .base_engine import BaseDomainEngine

logger = logging.getLogger(__name__)


class DelayAnalysisEngine(BaseDomainEngine):
    """
    موتور تحلیل تأخیرات پروژه
    
    این engine از کامپوننت‌های موجود استفاده می‌کند:
    - DelayAgent: برای تحلیل تأخیرات
    - TimelineAnalyzer: برای timeline
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("delay_analyzer", config)
        self.delay_agent = None
        self.timeline_analyzer = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.agents.delay_agent import DelayAgent
            from .timeline_analyzer import TimelineAnalyzer
            
            self.delay_agent = DelayAgent()
            await self.delay_agent.initialize()
            
            self.timeline_analyzer = TimelineAnalyzer()
            await self.timeline_analyzer.initialize()
            
            self._initialized = True
            self.logger.info("✅ DelayAnalysisEngine fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize DelayAnalysisEngine: {e}", exc_info=True)
            raise
    
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحلیل تأخیرات پروژه
        
        Args:
            input_data: شامل:
                - project_id: شناسه پروژه
                - baseline_schedule: برنامه پایه
                - actual_schedule: برنامه واقعی
                - query: سؤال یا موضوع
        
        Returns:
            نتیجه شامل:
                - delays: لیست تأخیرات
                - delay_analysis: تحلیل تأخیرات
                - baseline_vs_actual: مقایسه پایه و واقعی
                - critical_path: مسیر بحرانی
                - delay_windows: پنجره‌های تأخیر
                - attribution: مسئولیت‌ها
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Use DelayAgent for analysis
            delay_result = await self.delay_agent.process(input_data)
            
            if not delay_result.get("success"):
                return {
                    "success": False,
                    "error": delay_result.get("error", "Unknown error"),
                    "delays": []
                }
            
            # Get timeline for context
            timeline_result = await self.timeline_analyzer.analyze({
                "query": input_data.get("query", "timeline"),
                "documents": []
            })
            
            # Calculate delay windows
            delay_windows = self._calculate_delay_windows(
                delay_result.get("delays", []),
                delay_result.get("timeline", [])
            )
            
            # Enhanced attribution
            attribution = self._enhance_attribution(
                delay_result.get("attribution", {}),
                delay_result.get("delays", [])
            )
            
            return {
                "success": True,
                "delays": delay_result.get("delays", []),
                "delay_analysis": delay_result.get("delay_analysis", {}),
                "baseline_vs_actual": delay_result.get("delay_analysis", {}).get("baseline_vs_actual", {}),
                "critical_path": delay_result.get("critical_path", []),
                "delay_windows": delay_windows,
                "attribution": attribution,
                "timeline": timeline_result.get("timeline", []),
                "metadata": {
                    **delay_result.get("metadata", {}),
                    "delay_windows_count": len(delay_windows),
                    "has_critical_path": len(delay_result.get("critical_path", [])) > 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"Delay analysis failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "delays": []
            }
    
    def _calculate_delay_windows(self, delays: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate delay windows"""
        delay_windows: List[Any] = []
        for delay in delays:
            delay_days = delay.get("delay_days", 0)
            if delay_days > 0:
                delay_windows.append({
                    "delay_days": delay_days,
                    "description": delay.get("description", "")[:200],
                    "source": delay.get("source"),
                    "window_type": "critical" if delay_days > 30 else "normal"
                })
        
        return delay_windows
    
    def _enhance_attribution(self, attribution: Dict[str, Any], delays: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Enhance attribution with statistics"""
        enhanced: Dict[str, Any] = {}
        for party, party_delays in attribution.items():
            if party_delays:
                total_delay_days = sum(d.get("delay_days", 0) for d in party_delays)
                enhanced[party] = {
                    "delays": party_delays,
                    "total_delay_days": total_delay_days,
                    "delay_count": len(party_delays),
                    "average_delay_days": total_delay_days / len(party_delays) if party_delays else 0
                }
            else:
                enhanced[party] = {
                    "delays": [],
                    "total_delay_days": 0,
                    "delay_count": 0,
                    "average_delay_days": 0
                }
        
        return enhanced

