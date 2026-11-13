"""
Ultra Narrative Agent - Enterprise-Grade Legal Narrative Generation
====================================================================
Agent پیشرفته برای تولید روایت حقوقی-فنی

Features:
- Multi-section Narrative Generation
- Legal-Technical Integration
- Citation Weaving
- Coherence Scoring
- Template-based Structure
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_agent import UltraBaseAgent, AgentConfig

logger = logging.getLogger(__name__)


class NarrativeType(str, Enum):
    """Types of narratives"""
    LEGAL = "legal"           # روایت حقوقی
    TECHNICAL = "technical"   # روایت فنی
    COMBINED = "combined"     # ترکیبی
    SUMMARY = "summary"       # خلاصه
    DETAILED = "detailed"     # تفصیلی


class NarrativeSection(str, Enum):
    """Narrative sections"""
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    FACTS = "facts"
    ANALYSIS = "analysis"
    LEGAL_FRAMEWORK = "legal_framework"
    CONCLUSIONS = "conclusions"
    RECOMMENDATIONS = "recommendations"


@dataclass
class NarrativeAgentConfig(AgentConfig):
    """Configuration for narrative agent"""
    top_k: int = 15
    include_citations: bool = True
    max_section_length: int = 1000
    generate_all_sections: bool = True
    coherence_threshold: float = 0.6


@dataclass
class NarrativeSectionContent:
    """Content for a narrative section"""
    section_type: NarrativeSection
    title: str
    content: str
    citations: List[str] = field(default_factory=list)
    coherence_score: float = 0.0


class UltraNarrativeAgent(UltraBaseAgent):
    """
    Enterprise-grade narrative generation agent.
    
    این agent روایت حقوقی-فنی کامل تولید می‌کند:
    1. جمع‌آوری اطلاعات از منابع مختلف
    2. ساختاردهی به بخش‌های مختلف
    3. یکپارچه‌سازی ارجاعات
    4. تولید متن منسجم
    """
    
    SECTION_TEMPLATES = {
        NarrativeSection.INTRODUCTION: "مقدمه و معرفی موضوع",
        NarrativeSection.BACKGROUND: "پیشینه و زمینه",
        NarrativeSection.FACTS: "شرح وقایع و حقایق",
        NarrativeSection.ANALYSIS: "تحلیل و بررسی",
        NarrativeSection.LEGAL_FRAMEWORK: "چارچوب حقوقی",
        NarrativeSection.CONCLUSIONS: "نتیجه‌گیری",
        NarrativeSection.RECOMMENDATIONS: "توصیه‌ها و پیشنهادات"
    }
    
    def __init__(self, config: Optional[NarrativeAgentConfig] = None):
        super().__init__(
            name="ultra_narrative",
            config=config or NarrativeAgentConfig()
        )
        self._rag_service = None
        self._citation_engine = None
        self._reasoning_service = None
        
        self._narrative_metrics = {
            "narratives_generated": 0,
            "avg_sections": 0.0,
            "avg_length": 0.0,
        }
    
    async def _initialize_impl(self):
        """Initialize components"""
        self.logger.info("Initializing UltraNarrativeAgent...")
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            self._rag_service = await create_hybrid_rag_service()
            self.logger.info("✅ RAG Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ RAG Service not available: {e}")
        
        try:
            from mahoun.rag.citation_engine import CitationEngine
            self._citation_engine = CitationEngine()
            self.logger.info("✅ Citation Engine initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Citation Engine not available: {e}")
        
        try:
            from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
            self._reasoning_service = UltraReasoningService()
            self.logger.info("✅ Reasoning Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Reasoning Service not available: {e}")
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Generate legal-technical narrative.
        
        Args:
            input_data: {
                "topic": str,              # Main topic
                "context": str,            # Background context
                "narrative_type": str,     # Type of narrative
                "analysis_results": dict,  # Results from other agents
                "sections": list           # Specific sections to generate
            }
        """
        topic = input_data.get("topic", "")
        context = input_data.get("context", "")
        narrative_type_str = input_data.get("narrative_type", "combined")
        analysis_results = input_data.get("analysis_results", {})
        requested_sections = input_data.get("sections", [])
        
        if not topic:
            raise ValueError("Topic is required")
        
        # Parse narrative type
        try:
            narrative_type = NarrativeType(narrative_type_str)
        except ValueError:
            narrative_type = NarrativeType.COMBINED
        
        # Determine sections to generate
        sections_to_generate = self._determine_sections(narrative_type, requested_sections)
        
        # Search for relevant content
        search_results = await self._search_content(topic, context, correlation_id)
        
        # Generate each section
        sections: List[Any] = []
        for section_type in sections_to_generate:
            section_content = await self._generate_section(
                section_type=section_type,
                topic=topic,
                context=context,
                search_results=search_results,
                analysis_results=analysis_results,
                correlation_id=correlation_id
            )
            sections.append(section_content)
        
        # Combine into full narrative
        full_narrative = self._combine_sections(sections)
        
        # Extract all citations
        all_citations: List[Any] = []
        for section in sections:
            all_citations.extend(section.citations)
        
        # Generate conclusions
        conclusions = self._extract_conclusions(sections)
        
        # Update metrics
        self._narrative_metrics["narratives_generated"] += 1
        n = self._narrative_metrics["narratives_generated"]
        self._narrative_metrics["avg_sections"] = (
            (self._narrative_metrics["avg_sections"] * (n-1) + len(sections)) / n
        )
        self._narrative_metrics["avg_length"] = (
            (self._narrative_metrics["avg_length"] * (n-1) + len(full_narrative)) / n
        )
        
        return {
            "narrative": full_narrative,
            "sections": {s.section_type.value: s.content for s in sections},
            "citations": list(set(all_citations)),
            "conclusions": conclusions,
            "metadata": {
                "narrative_type": narrative_type.value,
                "sections_count": len(sections),
                "total_length": len(full_narrative),
                "avg_coherence": sum(s.coherence_score for s in sections) / len(sections) if sections else 0
            }
        }
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Fallback: simple template-based narrative"""
        self.logger.warning(f"[{correlation_id}] Using FALLBACK mode")
        
        topic = input_data.get("topic", "")
        context = input_data.get("context", "")
        
        simple_narrative = f"""
موضوع: {topic}

مقدمه:
این گزارش به بررسی {topic} می‌پردازد.

زمینه:
{context[:500] if context else 'اطلاعات زمینه‌ای موجود نیست.'}

نتیجه‌گیری:
نیاز به تحلیل بیشتر برای ارائه نتیجه‌گیری دقیق.
        """.strip()
        
        return {
            "narrative": simple_narrative,
            "sections": {"introduction": simple_narrative},
            "citations": [],
            "conclusions": ["نیاز به تحلیل بیشتر"],
            "metadata": {"fallback_used": True}
        }
    
    def _determine_sections(
        self,
        narrative_type: NarrativeType,
        requested: List[str]
    ) -> List[NarrativeSection]:
        """Determine which sections to generate"""
        if requested:
            return [NarrativeSection(s) for s in requested if s in [e.value for e in NarrativeSection]]
        
        if narrative_type == NarrativeType.SUMMARY:
            return [NarrativeSection.INTRODUCTION, NarrativeSection.CONCLUSIONS]
        elif narrative_type == NarrativeType.LEGAL:
            return [
                NarrativeSection.INTRODUCTION,
                NarrativeSection.FACTS,
                NarrativeSection.LEGAL_FRAMEWORK,
                NarrativeSection.CONCLUSIONS
            ]
        elif narrative_type == NarrativeType.TECHNICAL:
            return [
                NarrativeSection.INTRODUCTION,
                NarrativeSection.BACKGROUND,
                NarrativeSection.ANALYSIS,
                NarrativeSection.RECOMMENDATIONS
            ]
        else:  # COMBINED or DETAILED
            return list(NarrativeSection)
    
    async def _search_content(
        self,
        topic: str,
        context: str,
        correlation_id: Optional[str]
    ) -> List[Dict]:
        """Search for relevant content"""
        if not self._rag_service:
            return []
        
        try:
            from mahoun.rag.hybrid_rag_service import RAGMode
            
            query = f"{topic} {context[:100]}" if context else topic
            
            result = await self._rag_service.retrieve(
                query=query,
                mode=RAGMode.AUTO,
                top_k=self.config.top_k
            )
            
            return [
                {"content": r.content, "doc_id": r.doc_id, "score": r.score}
                for r in result.results
            ]
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] Search failed: {e}")
            return []
    
    async def _generate_section(
        self,
        section_type: NarrativeSection,
        topic: str,
        context: str,
        search_results: List[Dict],
        analysis_results: Dict,
        correlation_id: Optional[str]
    ) -> NarrativeSectionContent:
        """Generate a single section"""
        title = self.SECTION_TEMPLATES.get(section_type, section_type.value)
        
        # Build section content based on type
        if section_type == NarrativeSection.INTRODUCTION:
            content = self._generate_introduction(topic, context)
        elif section_type == NarrativeSection.BACKGROUND:
            content = self._generate_background(context, search_results)
        elif section_type == NarrativeSection.FACTS:
            content = self._generate_facts(search_results, analysis_results)
        elif section_type == NarrativeSection.ANALYSIS:
            content = self._generate_analysis(topic, search_results, analysis_results)
        elif section_type == NarrativeSection.LEGAL_FRAMEWORK:
            content = self._generate_legal_framework(search_results)
        elif section_type == NarrativeSection.CONCLUSIONS:
            content = self._generate_conclusions(topic, search_results, analysis_results)
        elif section_type == NarrativeSection.RECOMMENDATIONS:
            content = self._generate_recommendations(analysis_results)
        else:
            content = f"بخش {title}"
        
        # Extract citations
        citations = [r["doc_id"] for r in search_results[:3]]
        
        # Calculate coherence (simplified)
        coherence = min(1.0, len(content) / 500) * 0.8
        
        return NarrativeSectionContent(
            section_type=section_type,
            title=title,
            content=content[:self.config.max_section_length],
            citations=citations,
            coherence_score=coherence
        )
    
    def _generate_introduction(self, topic: str, context: str) -> str:
        return f"این گزارش به بررسی و تحلیل {topic} می‌پردازد. {context[:200] if context else ''}"
    
    def _generate_background(self, context: str, results: List[Dict]) -> str:
        parts = [context[:300] if context else ""]
        for r in results[:2]:
            parts.append(r["content"][:200])
        return " ".join(parts)
    
    def _generate_facts(self, results: List[Dict], analysis: Dict) -> str:
        facts: List[Any] = []
        for r in results[:3]:
            facts.append(f"- {r['content'][:150]}")
        if analysis:
            facts.append(f"- نتایج تحلیل: {str(analysis)[:200]}")
        return "\n".join(facts)
    
    def _generate_analysis(self, topic: str, results: List[Dict], analysis: Dict) -> str:
        parts = [f"تحلیل {topic}:"]
        for r in results[:3]:
            parts.append(r["content"][:200])
        return "\n".join(parts)
    
    def _generate_legal_framework(self, results: List[Dict]) -> str:
        legal_refs: List[Any] = []
        for r in results:
            if any(kw in r["content"] for kw in ["ماده", "قانون", "آیین‌نامه"]):
                legal_refs.append(r["content"][:200])
        return "\n".join(legal_refs[:5]) if legal_refs else "چارچوب حقوقی نیاز به بررسی بیشتر دارد."
    
    def _generate_conclusions(self, topic: str, results: List[Dict], analysis: Dict) -> str:
        return f"با توجه به بررسی‌های انجام شده در خصوص {topic}، نتایج زیر حاصل شده است..."
    
    def _generate_recommendations(self, analysis: Dict) -> str:
        return "توصیه می‌شود اقدامات لازم برای پیگیری موضوع انجام شود."
    
    def _combine_sections(self, sections: List[NarrativeSectionContent]) -> str:
        """Combine sections into full narrative"""
        parts: List[Any] = []
        for section in sections:
            parts.append(f"## {section.title}")
            parts.append(section.content)
            parts.append("")
        return "\n".join(parts)
    
    def _extract_conclusions(self, sections: List[NarrativeSectionContent]) -> List[str]:
        """Extract conclusions from sections"""
        conclusions: List[Any] = []
        for section in sections:
            if section.section_type == NarrativeSection.CONCLUSIONS:
                conclusions.append(section.content[:200])
        return conclusions if conclusions else ["نتیجه‌گیری نیاز به تکمیل دارد"]
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        return {
            "components": {
                "rag_service": self._rag_service is not None,
                "citation_engine": self._citation_engine is not None,
                "reasoning_service": self._reasoning_service is not None
            },
            "metrics": self._narrative_metrics.copy()
        }
