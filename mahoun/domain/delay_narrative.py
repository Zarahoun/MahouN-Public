"""
Delay Narrative Generator
=========================

موتور تولید روایت حقوقی-فنی تأخیرات
از کامپوننت‌های موجود استفاده می‌کند:
- NarrativeAgent برای تولید روایت
- DelayAnalysisEngine برای تحلیل
"""

from typing import Any, Dict, List, Optional
import logging

from .base_engine import BaseDomainEngine

logger = logging.getLogger(__name__)


class DelayNarrativeGenerator(BaseDomainEngine):
    """
    موتور تولید روایت حقوقی-فنی تأخیرات
    
    این engine از کامپوننت‌های موجود استفاده می‌کند:
    - NarrativeAgent: برای تولید روایت
    - DelayAnalysisEngine: برای تحلیل تأخیرات
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("delay_narrative_generator", config)
        self.narrative_agent = None
        self.delay_analyzer = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.agents.narrative_agent import NarrativeAgent
            from .delay_analyzer import DelayAnalysisEngine
            
            self.narrative_agent = NarrativeAgent()
            await self.narrative_agent.initialize()
            
            self.delay_analyzer = DelayAnalysisEngine()
            await self.delay_analyzer.initialize()
            
            self._initialized = True
            self.logger.info("✅ DelayNarrativeGenerator fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize DelayNarrativeGenerator: {e}", exc_info=True)
            raise
    
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تولید روایت حقوقی-فنی تأخیرات
        
        Args:
            input_data: شامل:
                - project_id: شناسه پروژه
                - delay_data: داده‌های تأخیر (optional)
                - narrative_type: نوع روایت (legal/technical/combined)
        
        Returns:
            نتیجه شامل:
                - narrative: روایت کامل
                - sections: بخش‌های روایت
                - legal_arguments: استدلال‌های حقوقی
                - technical_analysis: تحلیل فنی
                - conclusions: نتیجه‌گیری
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            project_id = input_data.get("project_id", "")
            delay_data = input_data.get("delay_data", {})
            narrative_type = input_data.get("narrative_type", "combined")
            
            # Get delay analysis if not provided
            if not delay_data:
                delay_analysis = await self.delay_analyzer.analyze(input_data)
                delay_data = delay_analysis
            else:
                delay_analysis = delay_data
            
            # Build context for narrative
            context = self._build_narrative_context(delay_analysis)
            
            # Generate narrative
            narrative_result = await self.narrative_agent.process({
                "topic": f"تحلیل تأخیرات پروژه {project_id}",
                "context": context,
                "analysis_results": delay_analysis,
                "narrative_type": narrative_type
            })
            
            if not narrative_result.get("success"):
                return {
                    "success": False,
                    "error": narrative_result.get("error", "Unknown error"),
                    "narrative": ""
                }
            
            # Enhance narrative with delay-specific sections
            enhanced_narrative = self._enhance_narrative(
                narrative_result.get("narrative", ""),
                delay_analysis
            )
            
            # Extract legal and technical sections
            legal_arguments = self._extract_legal_arguments(narrative_result, delay_analysis)
            technical_analysis = self._extract_technical_analysis(narrative_result, delay_analysis)
            
            return {
                "success": True,
                "narrative": enhanced_narrative,
                "sections": narrative_result.get("sections", {}),
                "legal_arguments": legal_arguments,
                "technical_analysis": technical_analysis,
                "conclusions": narrative_result.get("conclusions", []),
                "citations": narrative_result.get("citations", []),
                "metadata": {
                    **narrative_result.get("metadata", {}),
                    "narrative_type": narrative_type,
                    "delay_analysis_included": True
                }
            }
            
        except Exception as e:
            self.logger.error(f"Delay narrative generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "narrative": ""
            }
    
    def _build_narrative_context(self, delay_analysis: Dict[str, Any]) -> str:
        """Build context for narrative generation"""
        context_parts: List[Any] = []
        delays = delay_analysis.get("delays", [])
        if delays:
            context_parts.append(f"تعداد تأخیرات: {len(delays)}")
            total_delay = sum(d.get("delay_days", 0) for d in delays)
            context_parts.append(f"مجموع روزهای تأخیر: {total_delay}")
        
        attribution = delay_analysis.get("attribution", {})
        if attribution:
            context_parts.append("مسئولیت‌ها:")
            for party, data in attribution.items():
                if isinstance(data, dict) and data.get("delay_count", 0) > 0:
                    context_parts.append(f"  - {party}: {data.get('total_delay_days', 0)} روز")
        
        return "\n".join(context_parts)
    
    def _enhance_narrative(self, base_narrative: str, delay_analysis: Dict[str, Any]) -> str:
        """Enhance narrative with delay-specific information"""
        enhanced_parts = [base_narrative]
        
        # Add delay summary
        delays = delay_analysis.get("delays", [])
        if delays:
            enhanced_parts.append("\n\nخلاصه تأخیرات:")
            for i, delay in enumerate(delays[:5], 1):
                enhanced_parts.append(f"{i}. {delay.get('description', '')[:150]}")
        
        return "\n".join(enhanced_parts)
    
    def _extract_legal_arguments(self, narrative_result: Dict[str, Any], delay_analysis: Dict[str, Any]) -> List[str]:
        """Extract legal arguments from narrative"""
        legal_keywords = ["قانون", "مقررات", "بند", "ماده", "تعهد", "مسئولیت"]
        arguments: List[Any] = []
        narrative = narrative_result.get("narrative", "")
        for keyword in legal_keywords:
            if keyword in narrative:
                # Extract sentences containing keyword
                sentences = narrative.split(".")
                for sentence in sentences:
                    if keyword in sentence:
                        arguments.append(sentence.strip())
        
        return arguments[:10]  # Top 10
    
    def _extract_technical_analysis(self, narrative_result: Dict[str, Any], delay_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract technical analysis from narrative"""
        return {
            "delay_statistics": delay_analysis.get("delay_analysis", {}),
            "critical_path": delay_analysis.get("critical_path", []),
            "delay_windows": delay_analysis.get("delay_windows", []),
            "attribution": delay_analysis.get("attribution", {})
        }

