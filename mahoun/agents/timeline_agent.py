"""
Timeline Agent
==============

Agent برای استخراج توالی وقایع و timeline
از کامپوننت‌های موجود استفاده می‌کند:
- HybridRAGService برای جستجو
- Metadata Extractor برای استخراج تاریخ‌ها
"""

from typing import Any, Dict, List, Optional
import logging
import re
from datetime import datetime

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class TimelineAgent(BaseAgent):
    """
    Agent برای استخراج توالی وقایع و timeline
    
    این agent از کامپوننت‌های موجود استفاده می‌کند:
    - HybridRAGService: برای جستجو در مدارک
    - Metadata Extractor: برای استخراج تاریخ‌ها
    - QueryRouter: برای routing
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("timeline_agent", config)
        self.rag_service = None
        self.query_router = None
        self.metadata_extractor = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies from existing components"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from mahoun.rag.query_router import QueryRouter
            from mahoun.pipelines.ingestion.metadata_extractor import MetadataExtractor
            
            self.rag_service = await create_hybrid_rag_service()
            self.query_router = QueryRouter(rag_service=self.rag_service)
            self.metadata_extractor = MetadataExtractor()
            
            self._initialized = True
            self.logger.info("✅ TimelineAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize TimelineAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        استخراج timeline و توالی وقایع
        
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
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            query = input_data.get("query", "")
            documents = input_data.get("documents", [])
            date_range = input_data.get("date_range", {})
            
            # Search for timeline-related information
            timeline_queries = [
                query,
                f"{query} تاریخ",
                f"{query} زمان",
                f"{query} مهلت"
            ]
            
            all_events: List[Any] = []
            for search_query in timeline_queries[:3]:
                # Route and retrieve
                routed_result = await self.query_router.route(
                    query=search_query,
                    top_k=10
                )
                
                # Extract events from results
                events = self._extract_events(routed_result.rag_result.results)
                all_events.extend(events)
            
            # Sort events by date
            timeline = self._build_timeline(all_events)
            
            # Detect conflicts
            conflicts = self._detect_conflicts(timeline)
            
            # Build timeline matrix
            matrix = self._build_timeline_matrix(timeline)
            
            return {
                "success": True,
                "timeline": timeline,
                "events": all_events,
                "conflicts": conflicts,
                "matrix": matrix,
                "metadata": {
                    "total_events": len(timeline),
                    "total_conflicts": len(conflicts),
                    "date_range": {
                        "start": timeline[0]["date"] if timeline else None,
                        "end": timeline[-1]["date"] if timeline else None
                    }
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    def _extract_events(self, results: List[Any]) -> List[Dict[str, Any]]:
        """Extract events from retrieval results"""
        events: List[Any] = []
        for result in results:
            content = result.content
            metadata = result.metadata or {}
            
            # Extract dates
            dates = self._extract_dates(content)
            
            # Extract event description
            event_keywords = ["رویداد", "اتفاق", "اقدام", "انجام", "تاریخ"]
            if any(kw in content for kw in event_keywords):
                for date in dates:
                    events.append({
                        "date": date,
                        "description": content[:200],
                        "source": result.doc_id,
                        "metadata": metadata
                    })
        
        return events
    
    def _extract_dates(self, text: str) -> List[str]:
        """Extract dates from text"""
        dates: List[Any] = []
        # Persian date patterns
        patterns = [
            r'(\d{4})/(\d{1,2})/(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    dates.append("/".join(match))
                else:
                    dates.append(match)
        
        return dates
    
    def _build_timeline(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build sorted timeline from events"""
        # Sort by date
        sorted_events = sorted(events, key=lambda x: x.get("date", ""))
        
        # Add sequence numbers
        for i, event in enumerate(sorted_events, 1):
            event["sequence"] = i
        
        return sorted_events
    
    def _detect_conflicts(self, timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect conflicts in timeline"""
        conflicts: List[Any] = []
        # Check for duplicate dates with different descriptions
        date_groups: Dict[str, Any] = {}
        for event in timeline:
            date = event.get("date")
            if date:
                if date not in date_groups:
                    date_groups[date] = []
                date_groups[date].append(event)
        
        # Find conflicts
        for date, events in date_groups.items():
            if len(events) > 1:
                # Check if descriptions conflict
                descriptions = [e.get("description", "") for e in events]
                if len(set(descriptions)) > 1:
                    conflicts.append({
                        "date": date,
                        "conflicting_events": events,
                        "type": "duplicate_date"
                    })
        
        return conflicts
    
    def _build_timeline_matrix(self, timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build timeline matrix for visualization"""
        matrix = {
            "events": [],
            "dates": [],
            "sources": []
        }
        
        for event in timeline:
            matrix["events"].append({
                "sequence": event.get("sequence"),
                "date": event.get("date"),
                "description": event.get("description", "")[:100],
                "source": event.get("source")
            })
            
            if event.get("date") not in matrix["dates"]:
                matrix["dates"].append(event.get("date"))
            
            if event.get("source") not in matrix["sources"]:
                matrix["sources"].append(event.get("source"))
        
        return matrix

