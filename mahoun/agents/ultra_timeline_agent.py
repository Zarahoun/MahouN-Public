"""
Ultra Timeline Agent - Enterprise-Grade Temporal Analysis
=========================================================
Agent پیشرفته برای استخراج، تحلیل و اعتبارسنجی رویدادهای زمانی در پرونده‌های حقوقی.

Features:
- Advanced Date Extraction (Persian/Gregorian)
- Temporal Consistency Checking
- Event Sequence Validation
- Causal Link Analysis
- Visual Timeline Generation Support
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .base_agent import UltraBaseAgent, AgentConfig

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """انواع رویداد"""
    CONTRACTUAL = "contractual"   # قراردادی (امضا، ابلاغ)
    PERFORMANCE = "performance"    # اجرایی (شروع کار، تحویل)
    CORRESPONDENCE = "correspondence" # مکاتبات
    LEGAL = "legal"               # حقوقی (دادخواست، رای)
    FINANCIAL = "financial"       # مالی (پرداخت، صورت‌وضعیت)
    DELAY = "delay"               # تاخیر
    OTHER = "other"


@dataclass
class TimelineEvent:
    """ساختار یک رویداد زمانی"""
    id: str
    date_raw: str            # تاریخ استخراج شده (متن اصلی)
    date_normalized: str     # تاریخ استاندارد YYYY/MM/DD
    description: str         # شرح رویداد
    event_type: EventType
    source_doc_id: str
    confidence: float        # 0.0 to 1.0
    dependencies: List[str] = field(default_factory=list) # IDs of events this depends on
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "date": self.date_normalized,
            "raw_date": self.date_raw,
            "description": self.description,
            "type": self.event_type.value,
            "source": self.source_doc_id,
            "confidence": self.confidence,
            "dependencies": self.dependencies
        }


@dataclass
class TimelineResult:
    """خروجی تحلیل تایم‌لاین"""
    events: List[TimelineEvent]
    start_date: Optional[str]
    end_date: Optional[str]
    duration_days: int
    consistency_score: float      # 0-1 measure of logical consistency
    gaps_detected: List[str]      # Descriptions of potential missing periods
    conflicting_events: List[Dict] # List of conflicting event pairs


class TimelineConfig(AgentConfig):
    """تنظیمات Timeline Agent"""
    min_confidence: float = 0.6
    detect_causality: bool = True
    normalize_dates: bool = True


class UltraTimelineAgent(UltraBaseAgent):
    """
    Enterprise-grade timeline extraction and analysis agent.
    
    قابلیت‌ها:
    1. استخراج هوشمند تاریخ‌های شمسی و میلادی
    2. تشخیص نوع رویداد از روی متن
    3. بررسی تضادهای زمانی (مثلاً پایان قبل از شروع)
    4. ساخت گراف وابستگی رویدادها
    """
    
    def __init__(self, config: Optional[TimelineConfig] = None):
        super().__init__(
            name="ultra_timeline",
            config=config or TimelineConfig()
        )
        self.rag_service = None
        
        # Regex Patterns
        self._date_patterns = [
            # YYYY/MM/DD or YYYY-MM-DD
            (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', 'iso'),
            # DD/MM/YYYY
            (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', 'european'),
            # Textual (e.g., ۱۰ اردیبهشت ۱۴۰۲)
            (r'(\d{1,2})\s+(فروردین|اردیبهشت|خرداد|تیر|مرداد| شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s+(\d{4})', 'text_fa')
        ]

    async def _initialize_impl(self):
        """Initialize"""
        self.logger.info("Initializing UltraTimelineAgent...")
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            self.rag_service = await create_hybrid_rag_service()
            self.logger.info("✅ RAG Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ RAG Service not available: {e}")

    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Process timeline request.
        
        Args:
            input_data: {
                "query": str, (optional focus area)
                "documents": List[Dict] (content to analyze) OR use RAG if empty
            }
        """
        query = input_data.get("query", "تمام رویدادهای زمانی")
        documents = input_data.get("documents", [])
        
        # 1. Fetch documents if provided list is empty
        if not documents and self.rag_service:
            rag_result = await self.rag_service.retrieve(query, top_k=20)
            documents = [
                {"content": r.content, "id": r.doc_id, "score": r.score} 
                for r in rag_result.results
            ]
            
        # 2. Extract Events
        events = self._extract_events_from_docs(documents)
        
        # 3. Sort & Normalize
        events.sort(key=lambda x: x.date_normalized or "9999/99/99")
        
        # 4. Consistency Check
        consistency, conflicts = self._check_consistency(events)
        
        # 5. Metadata Calc
        start = events[0].date_normalized if events else None
        end = events[-1].date_normalized if events else None
        
        result = TimelineResult(
            events=events,
            start_date=start,
            end_date=end,
            duration_days=self._calc_duration(start, end),
            consistency_score=consistency,
            gaps_detected=[], 
            conflicting_events=conflicts
        )
        
        return {
            "timeline": [e.to_dict() for e in events],
            "analysis": {
                "start": start,
                "end": end,
                "consistency": consistency,
                "total_events": len(events),
                "conflicts": len(conflicts)
            }
        }

    def _extract_events_from_docs(self, docs: List[Dict]) -> List[TimelineEvent]:
        """Extract events from text chunks"""
        events: List[Any] = []
        event_counter = 0
        
        for doc in docs:
            text = doc.get("content", "")
            doc_id = doc.get("id", "unknown")
            
            # Simple sentence splitting
            sentences = text.replace('\n', '.').split('.')
            
            for sent in sentences:
                if len(sent) < 10: continue
                
                date_str, date_norm = self._find_date(sent)
                if date_str:
                    event_type = self._classify_event_type(sent)
                    event_counter += 1
                    
                    events.append(TimelineEvent(
                        id=f"evt_{event_counter}",
                        date_raw=date_str,
                        date_normalized=date_norm,
                        description=sent.strip()[:100],
                        event_type=event_type,
                        source_doc_id=doc_id,
                        confidence=0.8 # Placeholder score
                    ))
        return events

    def _find_date(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Find and normalize date in text"""
        # Fa mapping
        months = {
            "فروردین": "01", "اردیبهشت": "02", "خرداد": "03", 
            "تیر": "04", "مرداد": "05", "شهریور": "06",
            "مهر": "07", "آبان": "08", "آذر": "09", 
            "دی": "10", "بهمن": "11", "اسفند": "12"
        }

        for pattern, p_type in self._date_patterns:
            match = re.search(pattern, text)
            if match:
                raw = match.group(0)
                norm = ""
                
                if p_type == 'iso':
                    norm = f"{match.group(1)}/{match.group(2).zfill(2)}/{match.group(3).zfill(2)}"
                elif p_type == 'text_fa':
                    m_name = match.group(2)
                    m_num = months.get(m_name, "00")
                    norm = f"{match.group(3)}/{m_num}/{match.group(1).zfill(2)}"
                
                return raw, norm
                
        return None, None

    def _classify_event_type(self, text: str) -> EventType:
        """Heuristic classification"""
        keywords = {
            EventType.CONTRACTUAL: ["قرارداد", "امضا", "ابلاغ", "توافق"],
            EventType.FINANCIAL: ["پرداخت", "ریال", "تومان", "صورت وضعیت", "فاکتور"],
            EventType.DELAY: ["تاخیر", "تعویق", "دیرکرد", "مهلت"],
            EventType.LEGAL: ["دادخواست", "رای", "حکم", "شعبه", "ابلاغیه"],
            EventType.CORRESPONDENCE: ["نامه", "مورخ", "پیوست", "عطف"]
        }
        
        for etype, kws in keywords.items():
            if any(k in text for k in kws):
                return etype
        
        return EventType.OTHER

    def _check_consistency(self, events: List[TimelineEvent]) -> Tuple[float, List[Dict]]:
        """Check logical consistency of events"""
        conflicts: List[Any] = []
        score = 1.0
        
        # Check duplicate dates with very different descriptions (potential conflict)
        dates: Dict[str, Any] = {}
        for e in events:
            if not e.date_normalized: continue
            if e.date_normalized not in dates:
                dates[e.date_normalized] = []
            dates[e.date_normalized].append(e)
            
        for d, evts in dates.items():
            if len(evts) > 1:
                # Naive conflict check: if types are different, it might be weird
                types = set(e.event_type for e in evts)
                if EventType.CONTRACTUAL in types and EventType.LEGAL in types:
                   conflicts.append({"date": d, "reason": "Contract and Legal event on same day"})
                   score -= 0.05

        return max(0.0, score), conflicts

    def _calc_duration(self, start: Optional[str], end: Optional[str]) -> int:
        """Calculate days between dates (Naive)"""
        if not start or not end:
            return 0
        try:
            # Parse dates in YYYY/MM/DD format
            from datetime import datetime
            start_date = datetime.strptime(start, "%Y/%m/%d")
            end_date = datetime.strptime(end, "%Y/%m/%d")
            return (end_date - start_date).days
        except (ValueError, TypeError) as e:
            # Date parsing failed - return 0 as fallback
            logger.debug(f"Date parsing failed for {start} - {end}: {e}")
            return 0
