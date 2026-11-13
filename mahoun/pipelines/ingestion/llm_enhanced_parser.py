"""
LLM-Enhanced Verdict Parser
============================
Uses LLM to refine and improve the accuracy of verdict parsing.

This module enhances the rule-based minimal_verdict_parser with LLM-based
refinement to improve accuracy and handle edge cases.

Strategy:
1. Use minimal_verdict_parser for initial extraction (fast, rule-based)
2. Use LLM to refine ambiguous or low-confidence fields
3. Cross-validate critical fields
4. Fallback gracefully if LLM is unavailable
"""

import logging
import json
from typing import Any, Dict, List, Optional, Tuple
from .minimal_verdict_parser import parse_verdict_text
from mahoun.pipelines.llm.ollama_llm import OllamaLLMService

logger = logging.getLogger(__name__)


class LLMEnhancedParser:
    """
    LLM-enhanced parser that refines rule-based parsing results.
    
    Usage:
        parser = LLMEnhancedParser()
        verdict_struct = await parser.parse_enhanced(raw_text)
    """
    
    def __init__(
        self,
        llm_service: Optional[OllamaLLMService] = None,
        enable_refinement: bool = True,
        confidence_threshold: float = 0.6
    ):
        """
        Initialize LLM-Enhanced Parser.
        
        Args:
            llm_service: Optional LLM service (created if None)
            enable_refinement: Whether to use LLM refinement
            confidence_threshold: Minimum confidence to trigger refinement
        """
        self.enable_refinement = enable_refinement
        self.confidence_threshold = confidence_threshold
        
        # Initialize LLM service lazily
        if llm_service:
            self.llm_service = llm_service
            self._llm_initialized = True
        else:
            self.llm_service = None
            self._llm_initialized = False
        
        logger.info(
            f"LLMEnhancedParser initialized "
            f"(refinement={'enabled' if enable_refinement else 'disabled'})"
        )
    
    def _get_llm_service(self) -> Optional[OllamaLLMService]:
        """Get or create LLM service"""
        if not self.enable_refinement:
            return None
        
        if not self._llm_initialized:
            try:
                import os
                from mahoun.core.runtime_config import get_runtime_settings
                settings = get_runtime_settings()
                model = os.getenv("MAHOUN_OLLAMA_MODEL") or getattr(settings, 'ollama_model', 'llama2')
                base_url = os.getenv("MAHOUN_OLLAMA_URI") or getattr(settings, 'ollama_uri', 'http://localhost:11434')
                
                self.llm_service = OllamaLLMService(model=model, base_url=base_url)
                self._llm_initialized = True
                logger.info("LLM service initialized for parser refinement")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM service: {e}. Continuing without refinement.")
                self.enable_refinement = False
                return None
        
        return self.llm_service
    
    async def parse_enhanced(
        self,
        raw_text: str,
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse verdict text with LLM enhancement.
        
        Args:
            raw_text: Raw verdict text
            doc_id: Optional document ID
        
        Returns:
            Enhanced verdict structure
        """
        # Step 1: Initial rule-based parsing
        base_result = parse_verdict_text(raw_text)
        
        # Step 2: Check if refinement is needed
        confidence = base_result.get("_parsing_quality", {}).get("confidence_score", 1.0)
        
        if confidence >= self.confidence_threshold and not self.enable_refinement:
            logger.debug(f"High confidence ({confidence:.2f}), skipping LLM refinement")
            return base_result
        
        # Step 3: LLM refinement for low-confidence or ambiguous fields
        if self.enable_refinement:
            refined_result = await self._refine_with_llm(base_result, raw_text)
            
            # Merge refined fields into base result
            base_result = self._merge_results(base_result, refined_result)
            
            # Recalculate confidence
            base_result["_parsing_quality"]["confidence_score"] = self._recalculate_confidence(base_result)
        
        return base_result
    
    async def _refine_with_llm(
        self,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """
        Use LLM to refine parsing results.
        
        Focuses on:
        - Ambiguous fields (missing or low confidence)
        - Cross-validation of extracted entities
        - Improving party extraction
        - Refining legal references
        """
        llm = self._get_llm_service()
        if not llm:
            logger.debug("LLM not available, skipping refinement")
            return {}
        
        # Identify fields that need refinement
        fields_to_refine = self._identify_fields_to_refine(base_result)
        
        if not fields_to_refine:
            logger.debug("No fields need refinement")
            return {}
        
        logger.info(f"Refining {len(fields_to_refine)} fields with LLM")
        
        refined_fields: Dict[str, Any] = {}
        # Refine each field category
        for field_category in fields_to_refine:
            try:
                refined = await self._refine_field_category(
                    llm, field_category, base_result, raw_text
                )
                if refined:
                    refined_fields.update(refined)
            except Exception as e:
                logger.warning(f"Failed to refine {field_category}: {e}")
                continue
        
        return refined_fields
    
    def _identify_fields_to_refine(self, result: Dict[str, Any]) -> List[str]:
        """Identify which fields need LLM refinement"""
        fields_to_refine: List[Any] = []
        # Check case_meta
        case_meta = result.get("case_meta", {})
        if not case_meta.get("court_level"):
            fields_to_refine.append("court_level")
        if not case_meta.get("case_type"):
            fields_to_refine.append("case_type")
        
        # Check parties
        parties = result.get("parties", {})
        if not parties.get("third_party_objector") and not parties.get("respondents"):
            fields_to_refine.append("parties")
        
        # Check legal references
        legal_refs = result.get("legal_references", {})
        if not legal_refs.get("substantive_law") and not legal_refs.get("procedural_law"):
            fields_to_refine.append("legal_references")
        
        # Check claims
        claims = result.get("claims", {})
        if not claims.get("main") or len(claims.get("main", [])) == 0:
            fields_to_refine.append("claims")
        
        return fields_to_refine
    
    async def _refine_field_category(
        self,
        llm: OllamaLLMService,
        category: str,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """Refine a specific field category using LLM"""
        
        # Build prompt for specific category
        if category == "parties":
            return await self._refine_parties(llm, base_result, raw_text)
        elif category == "legal_references":
            return await self._refine_legal_references(llm, base_result, raw_text)
        elif category == "claims":
            return await self._refine_claims(llm, base_result, raw_text)
        elif category in ["court_level", "case_type"]:
            return await self._refine_case_meta(llm, category, base_result, raw_text)
        
        return {}
    
    async def _refine_parties(
        self,
        llm: OllamaLLMService,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """Refine party extraction using LLM"""
        
        prompt = f"""استخراج دقیق طرفین دعوی از متن زیر.

متن رأی:
{raw_text[:2000]}

لطفا استخراج کن:
1. معترض ثالث (نام، عنوان، نام پدر)
2. خواندگان (نام، عنوان، نام پدر)
3. وکلای طرفین

پاسخ را به صورت JSON بده:
{{
    "third_party_objector": {{"title": "...", "name": "...", "father_name": "..."}},
    "respondents": [{{"title": "...", "name": "...", "father_name": "..."}}],
    "attorneys": [{{"title": "...", "name": "...", "father_name": "...", "client": "..."}}]
}}

فقط JSON برگردان، بدون توضیح اضافی."""

        try:
            response = await llm.generate(prompt, temperature=0.1, max_tokens=500)
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                refined_parties = json.loads(json_str)
                
                # Convert to expected format
                return {
                    "parties": {
                        "third_party_objector": refined_parties.get("third_party_objector"),
                        "respondents": refined_parties.get("respondents", []),
                        "third_party_objector_attorney": None,
                        "respondents_attorneys": refined_parties.get("attorneys", [])
                    }
                }
        except Exception as e:
            logger.warning(f"Failed to refine parties with LLM: {e}")
        
        return {}
    
    async def _refine_legal_references(
        self,
        llm: OllamaLLMService,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """Refine legal article references using LLM"""
        
        prompt = f"""استخراج تمام ارجاعات به مواد قانون از متن زیر.

متن رأی:
{raw_text[:2000]}

لطفا تمام ارجاعات به مواد قانون را استخراج کن. برای هر ماده شماره ماده و نام قانون را مشخص کن.

پاسخ را به صورت JSON بده:
{{
    "substantive_law": ["ماده X قانون Y", ...],
    "procedural_law": ["ماده X قانون Y", ...],
    "fiqh_principles": ["اصاله الصحه", ...]
}}

فقط JSON برگردان."""

        try:
            response = await llm.generate(prompt, temperature=0.1, max_tokens=500)
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                refined_refs = json.loads(json_str)
                
                return {
                    "legal_references": {
                        "substantive_law": refined_refs.get("substantive_law", []),
                        "procedural_law": refined_refs.get("procedural_law", []),
                        "fiqh_principles": refined_refs.get("fiqh_principles", [])
                    }
                }
        except Exception as e:
            logger.warning(f"Failed to refine legal references with LLM: {e}")
        
        return {}
    
    async def _refine_claims(
        self,
        llm: OllamaLLMService,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """Refine claim extraction using LLM"""
        
        prompt = f"""استخراج دقیق خواسته‌های دعوی از متن زیر.

متن رأی:
{raw_text[:2000]}

لطفا تمام خواسته‌های اصلی دعوی را استخراج کن.

پاسخ را به صورت JSON بده:
{{
    "main": ["خواسته 1", "خواسته 2", ...],
    "execution_files": ["پرونده شماره X شعبه Y", ...]
}}

فقط JSON برگردان."""

        try:
            response = await llm.generate(prompt, temperature=0.1, max_tokens=300)
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                refined_claims = json.loads(json_str)
                
                return {
                    "claims": {
                        "main": refined_claims.get("main", []),
                        "execution_files": refined_claims.get("execution_files", [])
                    }
                }
        except Exception as e:
            logger.warning(f"Failed to refine claims with LLM: {e}")
        
        return {}
    
    async def _refine_case_meta(
        self,
        llm: OllamaLLMService,
        field: str,
        base_result: Dict[str, Any],
        raw_text: str
    ) -> Dict[str, Any]:
        """Refine case metadata fields"""
        
        if field == "court_level":
            prompt = f"""از متن زیر سطح دادگاه را استخراج کن (مثل: دادگاه تجدیدنظر استان تهران شعبه ۵).

متن:
{raw_text[:500]}

فقط نام کامل دادگاه را برگردان، بدون توضیح اضافی."""
        else:  # case_type
            prompt = f"""از متن زیر نوع دعوی را استخراج کن (مثل: اعتراض ثالث اجرایی).

متن:
{raw_text[:500]}

فقط نوع دعوی را برگردان، بدون توضیح اضافی."""

        try:
            response = await llm.generate(prompt, temperature=0.1, max_tokens=100)
            value = response.strip()
            
            if field == "court_level":
                return {
                    "case_meta": {
                        "court_level": value
                    }
                }
            else:
                return {
                    "case_meta": {
                        "case_type": value
                    }
                }
        except Exception as e:
            logger.warning(f"Failed to refine {field} with LLM: {e}")
        
        return {}
    
    def _merge_results(
        self,
        base: Dict[str, Any],
        refined: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge refined fields into base result"""
        result = base.copy()
        
        for key, value in refined.items():
            if isinstance(value, dict) and key in result:
                # Deep merge for nested dicts
                if isinstance(result[key], dict):
                    result[key].update(value)
                else:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _recalculate_confidence(self, result: Dict[str, Any]) -> float:
        """Recalculate confidence score after refinement"""
        quality = result.get("_parsing_quality", {})
        metrics = quality.get("metrics", {})
        
        score = 1.0
        if not metrics.get("court_level_found"):
            score -= 0.15  # Reduced penalty after refinement
        if not metrics.get("case_type_found"):
            score -= 0.15
        if not metrics.get("parties_found"):
            score -= 0.15
        if not metrics.get("articles_found"):
            score -= 0.10
        if not metrics.get("claims_found"):
            score -= 0.05
        
        return max(0.0, min(1.0, score))


# Convenience function
async def parse_verdict_enhanced(
    raw_text: str,
    doc_id: Optional[str] = None,
    enable_refinement: bool = True
) -> Dict[str, Any]:
    """
    Parse verdict with LLM enhancement.
    
    Args:
        raw_text: Raw verdict text
        doc_id: Optional document ID
        enable_refinement: Whether to use LLM refinement
    
    Returns:
        Enhanced verdict structure
    """
    parser = LLMEnhancedParser(enable_refinement=enable_refinement)
    return await parser.parse_enhanced(raw_text, doc_id=doc_id)

