"""
Domain-Specific Q&A Templates
=============================
Templates for generating high-quality Q&A pairs across different domains.

Each domain has specialized templates that:
- Extract domain-specific information
- Generate contextually relevant questions
- Ensure answers are grounded in source text
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import re

from .config import DomainType


@dataclass
class QATemplate:
    """Template for generating Q&A pairs"""
    template_id: str
    domain: DomainType
    question_pattern: str
    answer_extraction: str  # Regex or instruction for answer extraction
    question_type: str  # factual, reasoning, comparison, etc.
    difficulty: str  # easy, medium, hard
    requires_context: bool = True
    
    # Optional: specific entity types this template targets
    target_entities: List[str] = field(default_factory=list)
    
    # Optional: validation function
    validator: Optional[Callable[[str, str], bool]] = None


# =============================================================================
# Legal Domain Templates
# =============================================================================

LEGAL_TEMPLATES: List[QATemplate] = [
    # Factual Questions
    QATemplate(
        template_id="legal_parties",
        domain=DomainType.LEGAL,
        question_pattern="طرفین این پرونده چه کسانی هستند؟",
        answer_extraction=r"(خواهان|شاکی|مدعی).*?[:،].*?(?=خوانده|متهم|مدعی‌علیه)|(?:خوانده|متهم).*?[:،].*?(?=\n|$)",
        question_type="factual",
        difficulty="easy",
        target_entities=["PERSON", "ORGANIZATION"]
    ),
    QATemplate(
        template_id="legal_verdict",
        domain=DomainType.LEGAL,
        question_pattern="رأی دادگاه در این پرونده چه بود؟",
        answer_extraction=r"رأی.*?(?:صادر|اعلام).*?(?:\.|$)",
        question_type="factual",
        difficulty="easy",
        target_entities=["VERDICT"]
    ),
    QATemplate(
        template_id="legal_date",
        domain=DomainType.LEGAL,
        question_pattern="تاریخ صدور رأی چه زمانی است؟",
        answer_extraction=r"\d{4}/\d{2}/\d{2}|\d{2}/\d{2}/\d{4}",
        question_type="factual",
        difficulty="easy",
        target_entities=["DATE"]
    ),
    QATemplate(
        template_id="legal_case_number",
        domain=DomainType.LEGAL,
        question_pattern="شماره پرونده چیست؟",
        answer_extraction=r"(?:شماره پرونده|کلاسه).*?[:،\s].*?(?:\d+[-/]\d+|\d+)",
        question_type="factual",
        difficulty="easy",
        target_entities=["CASE_NUMBER"]
    ),
    
    # Reasoning Questions
    QATemplate(
        template_id="legal_reasoning",
        domain=DomainType.LEGAL,
        question_pattern="استدلال دادگاه برای صدور این رأی چه بود؟",
        answer_extraction=r"(?:نظر به|با توجه به|چون|زیرا).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="medium",
        target_entities=["REASONING"]
    ),
    QATemplate(
        template_id="legal_evidence",
        domain=DomainType.LEGAL,
        question_pattern="چه مستنداتی در این پرونده ارائه شده است؟",
        answer_extraction=r"(?:مستندات|دلایل|مدارک).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="medium",
        target_entities=["EVIDENCE"]
    ),
    QATemplate(
        template_id="legal_law_reference",
        domain=DomainType.LEGAL,
        question_pattern="به کدام مواد قانونی استناد شده است؟",
        answer_extraction=r"(?:ماده|تبصره|بند).*?\d+.*?(?:قانون|آیین‌نامه).*?(?:\.|$)",
        question_type="factual",
        difficulty="medium",
        target_entities=["LAW_ARTICLE"]
    ),
    
    # Complex Questions
    QATemplate(
        template_id="legal_precedent",
        domain=DomainType.LEGAL,
        question_pattern="آیا این رأی با رویه قضایی قبلی سازگار است؟",
        answer_extraction=r"(?:رویه|سابقه|آراء مشابه).*?(?:\.|$)",
        question_type="comparison",
        difficulty="hard",
        target_entities=["PRECEDENT"]
    ),
    QATemplate(
        template_id="legal_implications",
        domain=DomainType.LEGAL,
        question_pattern="پیامدهای حقوقی این رأی چیست؟",
        answer_extraction=r"(?:محکوم|ملزم|مکلف).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="hard",
        target_entities=["IMPLICATION"]
    ),
]


# =============================================================================
# Healthcare Domain Templates
# =============================================================================

HEALTHCARE_TEMPLATES: List[QATemplate] = [
    QATemplate(
        template_id="health_diagnosis",
        domain=DomainType.HEALTHCARE,
        question_pattern="تشخیص پزشکی در این مورد چیست؟",
        answer_extraction=r"(?:تشخیص|diagnosis).*?(?:\.|$)",
        question_type="factual",
        difficulty="easy",
        target_entities=["DIAGNOSIS"]
    ),
    QATemplate(
        template_id="health_treatment",
        domain=DomainType.HEALTHCARE,
        question_pattern="درمان پیشنهادی چیست؟",
        answer_extraction=r"(?:درمان|treatment|دارو|medication).*?(?:\.|$)",
        question_type="factual",
        difficulty="medium",
        target_entities=["TREATMENT"]
    ),
    QATemplate(
        template_id="health_symptoms",
        domain=DomainType.HEALTHCARE,
        question_pattern="علائم بیمار چه بود؟",
        answer_extraction=r"(?:علائم|symptoms|نشانه).*?(?:\.|$)",
        question_type="factual",
        difficulty="easy",
        target_entities=["SYMPTOM"]
    ),
    QATemplate(
        template_id="health_contraindications",
        domain=DomainType.HEALTHCARE,
        question_pattern="موارد منع مصرف چیست؟",
        answer_extraction=r"(?:منع مصرف|contraindication|احتیاط).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="hard",
        target_entities=["CONTRAINDICATION"]
    ),
]


# =============================================================================
# Financial Domain Templates
# =============================================================================

FINANCIAL_TEMPLATES: List[QATemplate] = [
    QATemplate(
        template_id="finance_amount",
        domain=DomainType.FINANCIAL,
        question_pattern="مبلغ مورد نظر چقدر است؟",
        answer_extraction=r"(?:\d+[,،]\d+|\d+).*?(?:ریال|تومان|دلار|یورو)",
        question_type="factual",
        difficulty="easy",
        target_entities=["MONEY"]
    ),
    QATemplate(
        template_id="finance_transaction",
        domain=DomainType.FINANCIAL,
        question_pattern="نوع تراکنش چیست؟",
        answer_extraction=r"(?:واریز|برداشت|انتقال|پرداخت).*?(?:\.|$)",
        question_type="factual",
        difficulty="easy",
        target_entities=["TRANSACTION"]
    ),
    QATemplate(
        template_id="finance_risk",
        domain=DomainType.FINANCIAL,
        question_pattern="ریسک‌های مالی این معامله چیست؟",
        answer_extraction=r"(?:ریسک|خطر|احتمال).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="hard",
        target_entities=["RISK"]
    ),
]


# =============================================================================
# General Domain Templates
# =============================================================================

GENERAL_TEMPLATES: List[QATemplate] = [
    QATemplate(
        template_id="general_what",
        domain=DomainType.GENERAL,
        question_pattern="موضوع اصلی این متن چیست؟",
        answer_extraction=r".*",  # Full text for general
        question_type="factual",
        difficulty="easy",
        target_entities=[]
    ),
    QATemplate(
        template_id="general_who",
        domain=DomainType.GENERAL,
        question_pattern="افراد کلیدی ذکر شده در متن چه کسانی هستند؟",
        answer_extraction=r"(?:[A-Z][a-z]+\s[A-Z][a-z]+|[\u0600-\u06FF]+\s[\u0600-\u06FF]+)",
        question_type="factual",
        difficulty="easy",
        target_entities=["PERSON"]
    ),
    QATemplate(
        template_id="general_when",
        domain=DomainType.GENERAL,
        question_pattern="این رویداد چه زمانی اتفاق افتاد؟",
        answer_extraction=r"\d{4}|\d{2}/\d{2}/\d{4}",
        question_type="factual",
        difficulty="easy",
        target_entities=["DATE"]
    ),
    QATemplate(
        template_id="general_why",
        domain=DomainType.GENERAL,
        question_pattern="دلیل این موضوع چیست؟",
        answer_extraction=r"(?:زیرا|چون|به دلیل|because).*?(?:\.|$)",
        question_type="reasoning",
        difficulty="medium",
        target_entities=[]
    ),
    QATemplate(
        template_id="general_summary",
        domain=DomainType.GENERAL,
        question_pattern="خلاصه این متن چیست؟",
        answer_extraction=r".*",
        question_type="summarization",
        difficulty="medium",
        target_entities=[]
    ),
]


# =============================================================================
# Template Registry
# =============================================================================

class TemplateRegistry:
    """Registry for managing Q&A templates"""
    
    def __init__(self):
        self._templates: Dict[DomainType, List[QATemplate]] = {
            DomainType.LEGAL: LEGAL_TEMPLATES,
            DomainType.HEALTHCARE: HEALTHCARE_TEMPLATES,
            DomainType.FINANCIAL: FINANCIAL_TEMPLATES,
            DomainType.GENERAL: GENERAL_TEMPLATES,
        }
        self._custom_templates: Dict[str, QATemplate] = {}
    
    def get_templates(
        self,
        domain: DomainType,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None
    ) -> List[QATemplate]:
        """Get templates for a domain with optional filters"""
        templates = self._templates.get(domain, GENERAL_TEMPLATES)
        
        if difficulty:
            templates = [t for t in templates if t.difficulty == difficulty]
        
        if question_type:
            templates = [t for t in templates if t.question_type == question_type]
        
        return templates
    
    def register_template(self, template: QATemplate) -> None:
        """Register a custom template"""
        self._custom_templates[template.template_id] = template
        
        # Also add to domain list
        if template.domain not in self._templates:
            self._templates[template.domain] = []
        self._templates[template.domain].append(template)
    
    def get_template_by_id(self, template_id: str) -> Optional[QATemplate]:
        """Get a specific template by ID"""
        # Check custom templates first
        if template_id in self._custom_templates:
            return self._custom_templates[template_id]
        
        # Search in all domains
        for templates in self._templates.values():
            for template in templates:
                if template.template_id == template_id:
                    return template
        
        return None
    
    def list_all_templates(self) -> Dict[str, List[str]]:
        """List all available templates by domain"""
        return {
            domain.value: [t.template_id for t in templates]
            for domain, templates in self._templates.items()
        }


# =============================================================================
# LLM Prompts for Q&A Generation
# =============================================================================

LLM_QA_GENERATION_PROMPT = """You are an expert at generating high-quality question-answer pairs from text.

Given the following text chunk, generate {num_pairs} question-answer pairs.

Domain: {domain}
Text:
---
{text}
---

Requirements:
1. Questions should be diverse (factual, reasoning, comparison)
2. Answers MUST be directly supported by the text (grounded)
3. Avoid yes/no questions
4. Questions should be in {language}
5. Each answer should be 1-3 sentences

Output format (JSON):
[
  {{"question": "...", "answer": "...", "type": "factual|reasoning|comparison", "evidence": "exact quote from text"}},
  ...
]

Generate {num_pairs} Q&A pairs:"""


LLM_QA_REFINEMENT_PROMPT = """Review and improve this Q&A pair:

Question: {question}
Answer: {answer}
Source Text: {source}

Check:
1. Is the answer factually correct based on the source?
2. Is the question clear and unambiguous?
3. Is the answer complete but concise?

If improvements needed, provide refined version. If good, return as-is.

Output format (JSON):
{{"question": "...", "answer": "...", "improved": true|false, "reason": "..."}}"""


# Global registry instance
template_registry = TemplateRegistry()
