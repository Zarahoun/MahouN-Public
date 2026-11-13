"""
Narrative Agent
===============

Agent برای تولید روایت حقوقی-فنی
از کامپوننت‌های موجود استفاده می‌کند:
- UltraReasoningService برای reasoning
- CitationEngine برای ارجاع
- سایر agents برای جمع‌آوری اطلاعات
"""

from typing import Any, Dict, List, Optional
import logging

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class NarrativeAgent(BaseAgent):
    """
    Agent برای تولید روایت حقوقی-فنی کامل
    
    این agent از کامپوننت‌های موجود استفاده می‌کند:
    - UltraReasoningService: برای reasoning و تحلیل
    - CitationEngine: برای ارجاع
    - سایر agents: برای جمع‌آوری اطلاعات
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("narrative_agent", config)
        self.reasoning_service = None
        self.citation_engine = None
        self.rag_service = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies from existing components"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from mahoun.rag.citation_engine import CitationEngine
            
            self.rag_service = await create_hybrid_rag_service()
            self.citation_engine = CitationEngine()
            
            try:
                from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
                self.reasoning_service = UltraReasoningService()
            except Exception as e:
                self.logger.warning(f"Could not initialize UltraReasoningService: {e}")
                self.reasoning_service = None
            
            self._initialized = True
            self.logger.info("✅ NarrativeAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize NarrativeAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تولید روایت حقوقی-فنی
        
        Args:
            input_data: شامل:
                - topic: موضوع روایت
                - context: اطلاعات زمینه‌ای
                - analysis_results: نتایج تحلیل‌های دیگر (optional)
                - narrative_type: نوع روایت (legal/technical/combined)
        
        Returns:
            نتیجه شامل:
                - narrative: روایت کامل
                - sections: بخش‌های روایت
                - citations: ارجاعات
                - conclusions: نتیجه‌گیری‌ها
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            topic = input_data.get("topic", "")
            context = input_data.get("context", "")
            analysis_results = input_data.get("analysis_results", {})
            narrative_type = input_data.get("narrative_type", "combined")
            
            # Build comprehensive context
            full_context = self._build_context(topic, context, analysis_results)
            
            # Retrieve relevant documents
            rag_result = await self.rag_service.retrieve(
                query=topic,
                top_k=15
            )
            
            # Extract citations
            citation_result = await self.citation_engine.extract_citations(
                rag_result=rag_result,
                query=topic
            )
            
            # Generate narrative using reasoning
            narrative = ""
            sections: Dict[str, Any] = {}
            if self.reasoning_service:
                # Generate different sections
                sections["introduction"] = await self._generate_section(
                    f"مقدمه و زمینه {topic}",
                    full_context,
                    rag_result.results
                )
                
                sections["analysis"] = await self._generate_section(
                    f"تحلیل {topic}",
                    full_context,
                    rag_result.results
                )
                
                sections["conclusions"] = await self._generate_section(
                    f"نتیجه‌گیری {topic}",
                    full_context,
                    rag_result.results
                )
                
                # Combine sections
                narrative = self._combine_sections(sections)
            else:
                # Fallback: simple narrative
                narrative = self._generate_simple_narrative(topic, full_context, rag_result.results)
            
            # Extract conclusions
            conclusions = self._extract_conclusions(narrative, rag_result.results)
            
            return {
                "success": True,
                "narrative": narrative,
                "sections": sections,
                "citations": [
                    {
                        "doc_id": c.doc_id,
                        "clause": c.clause_number,
                        "citation_text": c.citation_text
                    }
                    for c in citation_result.citations
                ],
                "conclusions": conclusions,
                "metadata": {
                    "narrative_type": narrative_type,
                    "total_citations": len(citation_result.citations),
                    "narrative_length": len(narrative)
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    def _build_context(self, topic: str, context: str, analysis_results: dict) -> str:
        """Build comprehensive context"""
        context_parts = [f"موضوع: {topic}"]
        
        if context:
            context_parts.append(f"زمینه: {context}")
        
        if analysis_results:
            context_parts.append(f"نتایج تحلیل: {str(analysis_results)[:500]}")
        
        return "\n".join(context_parts)
    
    async def _generate_section(self, section_title: str, context: str, results: list) -> str:
        """Generate a narrative section"""
        if self.reasoning_service:
            reasoning_result = await self.reasoning_service.reason(
                query=section_title,
                context=[r.content for r in results[:5]] + [context]
            )
            return reasoning_result.answer if hasattr(reasoning_result, 'answer') else str(reasoning_result)
        else:
            return f"{section_title}\n{context[:200]}"
    
    def _combine_sections(self, sections: dict) -> str:
        """Combine sections into full narrative"""
        narrative_parts: List[Any] = []
        if "introduction" in sections:
            narrative_parts.append(f"مقدمه:\n{sections['introduction']}")
        
        if "analysis" in sections:
            narrative_parts.append(f"\nتحلیل:\n{sections['analysis']}")
        
        if "conclusions" in sections:
            narrative_parts.append(f"\nنتیجه‌گیری:\n{sections['conclusions']}")
        
        return "\n".join(narrative_parts)
    
    def _generate_simple_narrative(self, topic: str, context: str, results: list) -> str:
        """Generate simple narrative without reasoning"""
        narrative_parts = [
            f"روایت مربوط به: {topic}",
            f"\nزمینه: {context[:300]}",
            "\nمستندات مرتبط:"
        ]
        
        for i, result in enumerate(results[:5], 1):
            narrative_parts.append(f"\n{i}. {result.content[:200]}...")
        
        return "\n".join(narrative_parts)
    
    def _extract_conclusions(self, narrative: str, results: list) -> list:
        """Extract conclusions from narrative"""
        conclusions: List[Any] = []
        conclusion_keywords = ["نتیجه", "خلاصه", "در نهایت", "به طور کلی"]
        
        for keyword in conclusion_keywords:
            if keyword in narrative:
                # Extract sentence containing keyword
                sentences = narrative.split(".")
                for sentence in sentences:
                    if keyword in sentence:
                        conclusions.append(sentence.strip())
        
        return conclusions[:5]  # Top 5

