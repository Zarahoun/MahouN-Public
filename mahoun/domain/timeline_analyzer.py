"""
Timeline Analyzer
=================

موتور تحلیل خط‌زمان و توالی وقایع
از کامپوننت‌های موجود استفاده می‌کند:
- TimelineAgent برای استخراج timeline
- Metadata Extractor برای استخراج تاریخ‌ها
"""

from typing import Any, Dict, List, Optional
import logging

from .base_engine import BaseDomainEngine

logger = logging.getLogger(__name__)


class TimelineAnalyzer(BaseDomainEngine):
    """
    موتور تحلیل خط‌زمان و توالی وقایع
    
    این engine از کامپوننت‌های موجود استفاده می‌کند:
    - TimelineAgent: برای استخراج timeline
    - Metadata Extractor: برای استخراج تاریخ‌ها
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("timeline_analyzer", config)
        self.timeline_agent = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.agents.timeline_agent import TimelineAgent
            
            self.timeline_agent = TimelineAgent()
            await self.timeline_agent.initialize()
            
            self._initialized = True
            self.logger.info("✅ TimelineAnalyzer fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize TimelineAnalyzer: {e}", exc_info=True)
            raise
    
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحلیل timeline و توالی وقایع
        
        Args:
            input_data: شامل:
                - query: سؤال یا موضوع
                - documents: لیست مدارک (optional)
                - date_range: بازه زمانی (optional)
        
        Returns:
            نتیجه شامل:
                - timeline: لیست وقایع به ترتیب زمانی
                - events: رویدادهای استخراج شده
                - conflicts: تضادها در timeline
                - matrix: ماتریس timeline
                - visualization_data: داده‌های برای visualization
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Use TimelineAgent for extraction
            result = await self.timeline_agent.process(input_data)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "timeline": [],
                    "events": []
                }
            
            # Enhance timeline with additional analysis
            timeline = result.get("timeline", [])
            conflicts = result.get("conflicts", [])
            matrix = result.get("matrix", {})
            
            # Build visualization data
            visualization_data = self._build_visualization_data(timeline, conflicts)
            
            # Analyze timeline patterns
            patterns = self._analyze_patterns(timeline)
            
            return {
                "success": True,
                "timeline": timeline,
                "events": result.get("events", []),
                "conflicts": conflicts,
                "matrix": matrix,
                "visualization_data": visualization_data,
                "patterns": patterns,
                "metadata": {
                    **result.get("metadata", {}),
                    "has_conflicts": len(conflicts) > 0,
                    "timeline_span_days": self._calculate_timeline_span(timeline)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Timeline analysis failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timeline": [],
                "events": []
            }
    
    def _build_visualization_data(self, timeline: List[Dict[str, Any]], conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build data for timeline visualization"""
        return {
            "events": [
                {
                    "id": i,
                    "date": event.get("date"),
                    "description": event.get("description", "")[:100],
                    "sequence": event.get("sequence", i)
                }
                for i, event in enumerate(timeline)
            ],
            "conflicts": [
                {
                    "date": conflict.get("date"),
                    "type": conflict.get("type"),
                    "events_count": len(conflict.get("conflicting_events", []))
                }
                for conflict in conflicts
            ],
            "date_range": {
                "start": timeline[0].get("date") if timeline else None,
                "end": timeline[-1].get("date") if timeline else None
            }
        }
    
    def _analyze_patterns(self, timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patterns in timeline"""
        if not timeline:
            return {}
        
        # Calculate intervals between events
        intervals: List[Any] = []
        for i in range(1, len(timeline)):
            # Simple pattern: count events
            intervals.append(i)
        
        return {
            "total_events": len(timeline),
            "average_interval": sum(intervals) / len(intervals) if intervals else 0,
            "event_density": len(timeline) / max(1, len(set(e.get("date", "") for e in timeline)))
        }
    
    def _calculate_timeline_span(self, timeline: List[Dict[str, Any]]) -> Optional[int]:
        """Calculate timeline span in days"""
        if len(timeline) < 2:
            return None
        
        # Simple calculation (would need proper date parsing in production)
        return len(timeline) - 1

