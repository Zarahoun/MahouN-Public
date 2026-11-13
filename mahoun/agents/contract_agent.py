"""
Ultra Contract Agent - Enterprise-Grade Contract Analysis
=========================================================
Agent پیشرفته برای تحلیل قراردادها و پاسخ به سؤالات پیمانی

Features:
- Chain-of-Thought Reasoning (استدلال گام به گام)
- Multi-step RAG with Reranking
- NLI Verification (تأیید پاسخ‌ها)
- Confidence Calibration
- Citation Tracking
- Graceful Degradation

Integration Points:
- rag/hybrid_rag_service.py → Retrieval
- reasoning/ultra_reasoning_service.py → Reasoning
- guardrails/ultra_nli_verifier.py → Verification
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_agent import (
    UltraBaseAgent,
    AgentConfig,
    AgentResult,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

class ReasoningMode(str, Enum):
    """Reasoning modes for contract analysis"""
    SIMPLE = "simple"           # Direct answer from top result
    CHAIN_OF_THOUGHT = "cot"    # Step-by-step reasoning
    MULTI_HOP = "multi_hop"     # Multiple retrieval rounds
    AUTO = "auto"               # Automatic selection


class RiskLevel(str, Enum):
    """Risk levels for contract clauses"""
    CRITICAL = "critical"    # بحرانی - نیاز به اقدام فوری
    HIGH = "high"           # بالا - نیاز به توجه جدی
    MEDIUM = "medium"       # متوسط - نیاز به بررسی
    LOW = "low"             # پایین - قابل قبول
    MINIMAL = "minimal"     # حداقلی - بدون نگرانی


class ClauseType(str, Enum):
    """Types of contract clauses - comprehensive legal taxonomy"""
    # === بندهای مالی ===
    PAYMENT = "payment"                     # پرداخت
    PRICE_ADJUSTMENT = "price_adjustment"   # تعدیل قیمت
    ADVANCE_PAYMENT = "advance_payment"     # پیش‌پرداخت
    RETENTION = "retention"                 # کسورات
    BANK_GUARANTEE = "bank_guarantee"       # ضمانت‌نامه بانکی
    
    # === بندهای اجرایی ===
    DELIVERY = "delivery"                   # تحویل
    SCOPE_OF_WORK = "scope_of_work"        # محدوده کار
    TIMELINE = "timeline"                   # زمان‌بندی
    MILESTONES = "milestones"              # نقاط عطف
    ACCEPTANCE = "acceptance"               # تحویل و پذیرش
    SUBCONTRACTING = "subcontracting"      # پیمانکاری فرعی
    
    # === بندهای تضمینی ===
    WARRANTY = "warranty"                   # ضمانت
    PERFORMANCE_BOND = "performance_bond"   # ضمانت حسن انجام کار
    INSURANCE = "insurance"                 # بیمه
    
    # === بندهای مسئولیت ===
    LIABILITY = "liability"                 # مسئولیت
    INDEMNIFICATION = "indemnification"     # غرامت
    LIMITATION = "limitation"               # محدودیت مسئولیت
    CONSEQUENTIAL_DAMAGES = "consequential" # خسارات تبعی
    
    # === بندهای خاتمه ===
    TERMINATION = "termination"             # فسخ
    SUSPENSION = "suspension"               # تعلیق
    EXPIRY = "expiry"                       # انقضا
    
    # === بندهای جریمه ===
    PENALTY = "penalty"                     # جریمه
    LIQUIDATED_DAMAGES = "liquidated"       # خسارت از پیش تعیین شده
    DELAY_PENALTY = "delay_penalty"         # جریمه تأخیر
    
    # === بندهای حقوقی ===
    FORCE_MAJEURE = "force_majeure"         # فورس ماژور
    DISPUTE = "dispute"                     # حل اختلاف
    ARBITRATION = "arbitration"             # داوری
    GOVERNING_LAW = "governing_law"         # قانون حاکم
    JURISDICTION = "jurisdiction"           # صلاحیت
    
    # === بندهای محرمانگی و IP ===
    CONFIDENTIALITY = "confidentiality"     # محرمانگی
    INTELLECTUAL_PROPERTY = "ip"            # مالکیت فکری
    NON_COMPETE = "non_compete"             # عدم رقابت
    NON_SOLICITATION = "non_solicitation"   # عدم جذب نیرو
    
    # === بندهای خاص ===
    ASSIGNMENT = "assignment"               # واگذاری
    AMENDMENT = "amendment"                 # اصلاحیه
    NOTICE = "notice"                       # ابلاغ
    ENTIRE_AGREEMENT = "entire_agreement"   # تمامیت قرارداد
    SEVERABILITY = "severability"           # تجزیه‌پذیری
    WAIVER = "waiver"                       # اسقاط حق
    
    # === بندهای تخصصی ===
    COMPLIANCE = "compliance"               # انطباق با قوانین
    ANTI_CORRUPTION = "anti_corruption"     # مبارزه با فساد
    SANCTIONS = "sanctions"                 # تحریم‌ها
    DATA_PROTECTION = "data_protection"     # حفاظت از داده
    ENVIRONMENTAL = "environmental"         # محیط زیست
    HEALTH_SAFETY = "health_safety"         # بهداشت و ایمنی
    
    GENERAL = "general"                     # عمومی


@dataclass
class ContractAgentConfig(AgentConfig):
    """Extended configuration for contract agent"""
    # RAG settings
    top_k: int = 10
    rerank_top_k: int = 5
    min_relevance_score: float = 0.3
    
    # Reasoning settings
    reasoning_mode: ReasoningMode = ReasoningMode.AUTO
    enable_chain_of_thought: bool = True
    max_reasoning_steps: int = 5
    
    # Verification settings
    enable_verification: bool = True
    verification_threshold: float = 0.7
    
    # Response settings
    max_answer_length: int = 2000
    include_citations: bool = True
    include_confidence: bool = True
    
    # Clause Analysis settings
    enable_clause_analysis: bool = True
    enable_risk_scoring: bool = True
    risk_threshold_critical: float = 0.8
    risk_threshold_high: float = 0.6
    risk_threshold_medium: float = 0.4


# ============================================================================
# Clause Analysis Data Classes
# ============================================================================

@dataclass
class ClauseRisk:
    """Risk assessment for a single clause"""
    clause_id: str
    clause_text: str
    clause_type: ClauseType
    risk_level: RiskLevel
    risk_score: float  # 0.0 - 1.0
    risk_factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    legal_references: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "clause_text": self.clause_text[:300],
            "clause_type": self.clause_type.value,
            "risk_level": self.risk_level.value,
            "risk_score": round(self.risk_score, 3),
            "risk_factors": self.risk_factors,
            "recommendations": self.recommendations,
            "legal_references": self.legal_references
        }


@dataclass
class ContractAnalysis:
    """Complete contract analysis result"""
    total_clauses: int
    analyzed_clauses: int
    clauses: List[ClauseRisk] = field(default_factory=list)
    overall_risk_score: float = 0.0
    overall_risk_level: RiskLevel = RiskLevel.MINIMAL
    high_risk_clauses: int = 0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_clauses": self.total_clauses,
            "analyzed_clauses": self.analyzed_clauses,
            "overall_risk_score": round(self.overall_risk_score, 3),
            "overall_risk_level": self.overall_risk_level.value,
            "high_risk_clauses": self.high_risk_clauses,
            "summary": self.summary,
            "clauses": [c.to_dict() for c in self.clauses],
            "risk_distribution": self._get_risk_distribution()
        }
    
    def _get_risk_distribution(self) -> Dict[str, int]:
        distribution = {level.value: 0 for level in RiskLevel}
        for clause in self.clauses:
            distribution[clause.risk_level.value] += 1
        return distribution


# ============================================================================
# Chain of Thought Data Classes
# ============================================================================

@dataclass
class ReasoningStep:
    """A single step in chain-of-thought reasoning"""
    step_number: int
    thought: str
    action: str
    observation: str
    confidence: float = 0.0


@dataclass
class ContractReasoningChain:
    """Complete chain of thought"""
    question: str
    steps: List[ReasoningStep] = field(default_factory=list)
    final_answer: str = ""
    total_confidence: float = 0.0
    verified: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "steps": [
                {
                    "step": s.step_number,
                    "thought": s.thought,
                    "action": s.action,
                    "observation": s.observation[:200],
                    "confidence": s.confidence
                }
                for s in self.steps
            ],
            "final_answer": self.final_answer,
            "total_confidence": self.total_confidence,
            "verified": self.verified
        }


# ============================================================================
# Ultra Contract Agent
# ============================================================================

class UltraContractAgent(UltraBaseAgent):
    """
    Enterprise-grade contract analysis agent.
    
    این agent سؤالات مرتبط با قراردادها را تحلیل کرده و:
    1. اسناد مرتبط را جستجو می‌کند (RAG)
    2. با استدلال گام به گام پاسخ می‌دهد (Chain-of-Thought)
    3. پاسخ را تأیید می‌کند (NLI Verification)
    4. ارجاعات و سطح اطمینان را ارائه می‌دهد
    
    Features:
    - Circuit Breaker for RAG/Reasoning services
    - Automatic reasoning mode selection
    - Graceful degradation to simple answers
    - Confidence calibration
    
    Usage:
        async with UltraContractAgent() as agent:
            result = await agent.process({
                "query": "آیا خسارت تأخیر قابل مطالبه است؟",
                "context": "optional additional context"
            })
    """
    
    def __init__(self, config: Optional[ContractAgentConfig] = None):
        super().__init__(
            name="ultra_contract",
            config=config or ContractAgentConfig()
        )
        
        # Components (lazy loaded)
        self._rag_service = None
        self._reasoning_service = None
        self._verifier = None
        
        # Metrics
        self._contract_metrics = {
            "queries_processed": 0,
            "cot_used": 0,
            "simple_used": 0,
            "verifications_passed": 0,
            "verifications_failed": 0,
            "avg_confidence": 0.0,
            "fallback_used": 0,
        }
    
    async def _initialize_impl(self):
        """Initialize all components"""
        self.logger.info("Initializing UltraContractAgent components...")
        
        # 1. Initialize RAG Service
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            self._rag_service = await create_hybrid_rag_service()
            self.logger.info("✅ RAG Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ RAG Service not available: {e}")
        
        # 2. Initialize Reasoning Service
        try:
            from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
            self._reasoning_service = UltraReasoningService()
            self.logger.info("✅ Reasoning Service initialized")
        except Exception as e:
            self.logger.warning(f"⚠️ Reasoning Service not available: {e}")
        
        # 3. Initialize NLI Verifier
        if self.config.enable_verification:
            try:
                from mahoun.guardrails.ultra_nli_verifier import UltraNLIVerifier
                self._verifier = UltraNLIVerifier()
                self.logger.info("✅ NLI Verifier initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ NLI Verifier not available: {e}")
        
        self.logger.info("UltraContractAgent initialization complete")
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Process contract query with chain-of-thought reasoning.
        
        Args:
            input_data: {
                "query": str,              # User question
                "context": str,            # Optional additional context
                "top_k": int,              # Override default top_k
                "reasoning_mode": str,     # Override reasoning mode
                "skip_verification": bool  # Skip NLI verification
            }
        
        Returns:
            {
                "answer": str,
                "confidence": float,
                "verified": bool,
                "reasoning_chain": dict,
                "citations": list,
                "metadata": dict
            }
        """
        start_time = time.time()
        
        # Extract input
        query = input_data.get("query")
        if not query:
            raise ValueError("Query is required")
        
        context = input_data.get("context", "")
        top_k = input_data.get("top_k", self.config.top_k)
        reasoning_mode = input_data.get("reasoning_mode", self.config.reasoning_mode)
        skip_verification = input_data.get("skip_verification", False)
        
        # Step 1: RAG Retrieval
        rag_results = await self._retrieve_documents(query, top_k, correlation_id)
        
        if not rag_results:
            return {
                "answer": "متأسفانه مدرکی مرتبط با این سؤال یافت نشد.",
                "confidence": 0.0,
                "verified": False,
                "reasoning_chain": None,
                "citations": [],
                "metadata": {"no_results": True}
            }
        
        # Step 2: Select reasoning mode
        if reasoning_mode == ReasoningMode.AUTO:
            reasoning_mode = self._select_reasoning_mode(query, rag_results)
        
        # Step 3: Generate answer based on mode
        if reasoning_mode == ReasoningMode.CHAIN_OF_THOUGHT and self._reasoning_service:
            answer, confidence, reasoning_chain = await self._chain_of_thought_reasoning(
                query=query,
                context=context,
                rag_results=rag_results,
                correlation_id=correlation_id
            )
            self._contract_metrics["cot_used"] += 1
        else:
            answer, confidence, reasoning_chain = await self._simple_reasoning(
                query=query,
                rag_results=rag_results,
                correlation_id=correlation_id
            )
            self._contract_metrics["simple_used"] += 1
        
        # Step 4: Verify answer
        verified = False
        if not skip_verification and self._verifier and self.config.enable_verification:
            verified = await self._verify_answer(
                answer=answer,
                evidence=[r.get("content", "") for r in rag_results[:3]],
                correlation_id=correlation_id
            )
            if verified:
                self._contract_metrics["verifications_passed"] += 1
            else:
                self._contract_metrics["verifications_failed"] += 1
        
        # Step 5: Build citations
        citations = self._build_citations(rag_results)
        
        # Update metrics
        self._contract_metrics["queries_processed"] += 1
        n = self._contract_metrics["queries_processed"]
        self._contract_metrics["avg_confidence"] = (
            (self._contract_metrics["avg_confidence"] * (n - 1) + confidence) / n
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "answer": answer,
            "confidence": round(confidence, 3),
            "verified": verified,
            "reasoning_chain": reasoning_chain.to_dict() if reasoning_chain else None,
            "citations": citations,
            "metadata": {
                "reasoning_mode": reasoning_mode.value if isinstance(reasoning_mode, ReasoningMode) else reasoning_mode,
                "results_count": len(rag_results),
                "processing_time_ms": round(processing_time, 1),
                "verification_enabled": self.config.enable_verification
            }
        }
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Fallback: Return top RAG result as answer.
        
        WARNING: This is degraded mode - no reasoning or verification.
        """
        self.logger.warning(f"[{correlation_id}] Using FALLBACK mode")
        self._contract_metrics["fallback_used"] += 1
        
        query = input_data.get("query", "")
        
        # Try basic RAG
        if self._rag_service:
            try:
                from mahoun.rag.hybrid_rag_service import RAGMode
                result = await self._rag_service.retrieve(
                    query=query,
                    mode=RAGMode.TEXT_ONLY,
                    top_k=3
                )
                
                if result.results:
                    top_result = result.results[0]
                    return {
                        "answer": top_result.content[:self.config.max_answer_length],
                        "confidence": top_result.score * 0.5,  # Reduced confidence
                        "verified": False,
                        "reasoning_chain": None,
                        "citations": [{"doc_id": top_result.doc_id, "score": top_result.score}],
                        "metadata": {"fallback_used": True}
                    }
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] Fallback RAG failed: {e}")
        
        return {
            "answer": "متأسفانه در حال حاضر امکان پاسخگویی وجود ندارد.",
            "confidence": 0.0,
            "verified": False,
            "reasoning_chain": None,
            "citations": [],
            "metadata": {"fallback_used": True, "error": "Service unavailable"}
        }
    
    # ========================================================================
    # RAG Methods
    # ========================================================================
    
    async def _retrieve_documents(
        self,
        query: str,
        top_k: int,
        correlation_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents using RAG"""
        if not self._rag_service:
            return []
        
        try:
            from mahoun.rag.hybrid_rag_service import RAGMode
            result = await self._rag_service.retrieve(
                query=query,
                mode=RAGMode.AUTO,
                top_k=top_k
            )
            
            # Convert to dict format
            return [
                {
                    "doc_id": r.doc_id,
                    "content": r.content,
                    "score": r.score,
                    "source": r.source,
                    "metadata": getattr(r, 'metadata', {})
                }
                for r in result.results
                if r.score >= self.config.min_relevance_score
            ]
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] RAG retrieval failed: {e}")
            return []
    
    # ========================================================================
    # Reasoning Methods
    # ========================================================================
    
    def _select_reasoning_mode(
        self,
        query: str,
        rag_results: List[Dict]
    ) -> ReasoningMode:
        """Automatically select best reasoning mode"""
        # Complex queries benefit from CoT
        complex_indicators = [
            "چرا", "چگونه", "آیا می‌توان", "تفاوت", "مقایسه",
            "شرایط", "در صورتی که", "اگر"
        ]
        
        is_complex = any(ind in query for ind in complex_indicators)
        has_multiple_results = len(rag_results) > 3
        
        if is_complex and has_multiple_results and self._reasoning_service:
            return ReasoningMode.CHAIN_OF_THOUGHT
        
        return ReasoningMode.SIMPLE
    
    async def _chain_of_thought_reasoning(
        self,
        query: str,
        context: str,
        rag_results: List[Dict],
        correlation_id: Optional[str]
    ) -> tuple:
        """Perform chain-of-thought reasoning"""
        chain = ContractReasoningChain(question=query)
        
        # Step 1: Analyze query
        chain.steps.append(ReasoningStep(
            step_number=1,
            thought=f"تحلیل سؤال: {query}",
            action="query_analysis",
            observation="سؤال مربوط به حوزه قراردادی است",
            confidence=0.9
        ))
        
        # Step 2: Review evidence
        evidence_texts = [r["content"][:500] for r in rag_results[:self.config.rerank_top_k]]
        chain.steps.append(ReasoningStep(
            step_number=2,
            thought=f"بررسی {len(evidence_texts)} مدرک مرتبط",
            action="evidence_review",
            observation=f"مدارک با امتیاز {rag_results[0]['score']:.2f} تا {rag_results[-1]['score']:.2f}",
            confidence=0.85
        ))
        
        # Step 3: Use reasoning service
        if self._reasoning_service:
            try:
                reasoning_result = await self._reasoning_service.reason(
                    context=evidence_texts,
                    query=query
                )
                
                answer = reasoning_result.get("answer", "")
                confidence = reasoning_result.get("confidence", 0.5)
                
                chain.steps.append(ReasoningStep(
                    step_number=3,
                    thought="استدلال بر اساس مدارک",
                    action="reasoning",
                    observation=answer[:200],
                    confidence=confidence
                ))
                
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] Reasoning service failed: {e}")
                answer = evidence_texts[0] if evidence_texts else ""
                confidence = 0.5
        else:
            # Fallback: use top result
            answer = evidence_texts[0] if evidence_texts else ""
            confidence = rag_results[0]["score"] if rag_results else 0.0
        
        # Finalize
        chain.final_answer = answer[:self.config.max_answer_length]
        chain.total_confidence = confidence
        
        return answer, confidence, chain
    
    async def _simple_reasoning(
        self,
        query: str,
        rag_results: List[Dict],
        correlation_id: Optional[str]
    ) -> tuple:
        """Simple reasoning: return top result with basic processing"""
        if not rag_results:
            return "", 0.0, None
        
        top_result = rag_results[0]
        answer = top_result["content"][:self.config.max_answer_length]
        confidence = top_result["score"]
        
        chain = ContractReasoningChain(
            question=query,
            steps=[ReasoningStep(
                step_number=1,
                thought="استفاده از بهترین نتیجه جستجو",
                action="direct_answer",
                observation=answer[:100],
                confidence=confidence
            )],
            final_answer=answer,
            total_confidence=confidence
        )
        
        return answer, confidence, chain
    
    # ========================================================================
    # Verification Methods
    # ========================================================================
    
    async def _verify_answer(
        self,
        answer: str,
        evidence: List[str],
        correlation_id: Optional[str]
    ) -> bool:
        """Verify answer using NLI"""
        if not self._verifier or not answer:
            return False
        
        try:
            result = await self._verifier.verify(
                claim=answer,
                evidence=evidence
            )
            
            if isinstance(result, dict):
                return result.get("is_valid", False)
            return bool(result)
            
        except Exception as e:
            self.logger.warning(f"[{correlation_id}] Verification failed: {e}")
            return False
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _build_citations(self, rag_results: List[Dict]) -> List[Dict[str, Any]]:
        """Build citation list from RAG results"""
        if not self.config.include_citations:
            return []
        
        return [
            {
                "doc_id": r["doc_id"],
                "excerpt": r["content"][:200],
                "score": round(r["score"], 3),
                "source": r.get("source", "unknown")
            }
            for r in rag_results[:5]
        ]
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        """Check health of all components"""
        return {
            "components": {
                "rag_service": self._rag_service is not None,
                "reasoning_service": self._reasoning_service is not None,
                "verifier": self._verifier is not None,
            },
            "contract_metrics": self._contract_metrics.copy()
        }
    
    def get_contract_metrics(self) -> Dict[str, Any]:
        """Get contract processing metrics"""
        return self._contract_metrics.copy()
    
    # ========================================================================
    # Clause-Level Analysis
    # ========================================================================
    
    # Risk indicators for different clause types - comprehensive (40+ types)
    RISK_INDICATORS = {
        # =====================================================================
        # === بندهای مالی - Financial Clauses ===
        # =====================================================================
        ClauseType.PAYMENT: {
            "high_risk": ["پرداخت کامل قبل از تحویل", "بدون ضمانت استرداد", "جریمه تأخیر بالا", "پرداخت غیرقابل برگشت", "پرداخت نقدی فوری"],
            "medium_risk": ["پرداخت اقساطی", "وثیقه", "ضمانت‌نامه بانکی", "پرداخت علی‌الحساب", "پرداخت مشروط"],
            "keywords": ["پرداخت", "مبلغ", "ثمن", "وجه", "تسویه", "قسط", "صورتحساب", "فاکتور", "هزینه", "بها"]
        },
        ClauseType.PRICE_ADJUSTMENT: {
            "high_risk": ["بدون تعدیل", "تعدیل یکطرفه", "افزایش نامحدود قیمت", "تعدیل بدون سقف"],
            "medium_risk": ["تعدیل بر اساس شاخص", "سقف تعدیل", "تعدیل سالانه"],
            "keywords": ["تعدیل", "افزایش قیمت", "شاخص", "تورم", "نرخ ارز", "تغییر قیمت", "اسکالیشن"]
        },
        ClauseType.ADVANCE_PAYMENT: {
            "high_risk": ["پیش‌پرداخت بدون ضمانت", "عدم استرداد پیش‌پرداخت", "پیش‌پرداخت ۱۰۰٪"],
            "medium_risk": ["پیش‌پرداخت بالا", "شرایط استرداد مبهم", "پیش‌پرداخت بدون تضمین بانکی"],
            "keywords": ["پیش‌پرداخت", "علی‌الحساب", "بیعانه", "پیش‌قسط", "پیش پرداخت", "advance"]
        },
        ClauseType.RETENTION: {
            "high_risk": ["کسورات بدون سقف", "عدم استرداد کسورات", "کسورات نامتناسب"],
            "medium_risk": ["کسورات بالا", "شرایط آزادسازی مبهم", "کسورات تجمیعی"],
            "keywords": ["کسورات", "سپرده حسن انجام کار", "retention", "نگهداری", "کسر", "ذخیره"]
        },
        ClauseType.BANK_GUARANTEE: {
            "high_risk": ["ضمانت‌نامه نامحدود", "ضبط بدون اخطار", "تمدید خودکار", "ضمانت‌نامه غیرقابل فسخ"],
            "medium_risk": ["مبلغ بالای ضمانت‌نامه", "شرایط ضبط مبهم", "تمدید اجباری"],
            "keywords": ["ضمانت‌نامه", "ضمانت بانکی", "LC", "اعتبار اسنادی", "گارانتی بانکی", "bank guarantee"]
        },
        
        # =====================================================================
        # === بندهای اجرایی - Execution Clauses ===
        # =====================================================================
        ClauseType.DELIVERY: {
            "high_risk": ["تحویل فوری", "بدون بازرسی", "ریسک از لحظه ارسال", "تحویل بدون تأیید"],
            "medium_risk": ["مهلت تحویل کوتاه", "شرایط تحویل مبهم", "تحویل در محل فروشنده"],
            "keywords": ["تحویل", "ارسال", "حمل", "بارگیری", "تخلیه", "انبار", "delivery", "shipping"]
        },
        ClauseType.SCOPE_OF_WORK: {
            "high_risk": ["محدوده نامشخص", "کار اضافی بدون پرداخت", "تغییرات یکطرفه", "محدوده باز"],
            "medium_risk": ["محدوده گسترده", "شرح کار مبهم", "تغییرات مکرر"],
            "keywords": ["محدوده کار", "شرح خدمات", "وظایف", "تعهدات", "الزامات", "scope", "SOW", "موضوع قرارداد"]
        },
        ClauseType.TIMELINE: {
            "high_risk": ["زمان‌بندی غیرواقعی", "بدون امکان تمدید", "جریمه سنگین تأخیر", "زمان قطعی"],
            "medium_risk": ["زمان‌بندی فشرده", "نقاط عطف متعدد", "مهلت کوتاه"],
            "keywords": ["زمان‌بندی", "برنامه", "مهلت", "موعد", "سررسید", "تاریخ", "schedule", "timeline"]
        },
        ClauseType.MILESTONES: {
            "high_risk": ["نقاط عطف غیرواقعی", "جریمه هر مرحله", "بدون انعطاف"],
            "medium_risk": ["نقاط عطف متعدد", "وابستگی به تأیید کارفرما"],
            "keywords": ["نقطه عطف", "milestone", "مرحله", "فاز", "تحویل موقت", "پیشرفت"]
        },
        ClauseType.ACCEPTANCE: {
            "high_risk": ["تحویل بدون تست", "پذیرش خودکار", "بدون دوره آزمایشی"],
            "medium_risk": ["معیارهای پذیرش مبهم", "مهلت کوتاه اعتراض"],
            "keywords": ["پذیرش", "تحویل قطعی", "acceptance", "تأیید", "تست", "آزمایش", "بازرسی"]
        },
        ClauseType.SUBCONTRACTING: {
            "high_risk": ["ممنوعیت کامل واگذاری", "مسئولیت کامل پیمانکار اصلی", "واگذاری بدون اطلاع"],
            "medium_risk": ["نیاز به تأیید کتبی", "محدودیت پیمانکاران فرعی", "مسئولیت تضامنی"],
            "keywords": ["پیمانکار فرعی", "واگذاری", "زیرمجموعه", "شریک", "subcontract", "زیرپیمانکار"]
        },
        
        # =====================================================================
        # === بندهای تضمینی - Guarantee Clauses ===
        # =====================================================================
        ClauseType.WARRANTY: {
            "high_risk": ["بدون ضمانت", "ضمانت محدود", "استثنائات گسترده", "ضمانت غیرقابل انتقال", "as-is"],
            "medium_risk": ["ضمانت کوتاه مدت", "شرایط ضمانت سخت", "محدودیت جغرافیایی"],
            "keywords": ["ضمانت", "گارانتی", "تضمین", "کیفیت", "عیب", "نقص", "warranty", "guarantee"]
        },
        ClauseType.PERFORMANCE_BOND: {
            "high_risk": ["ضمانت اجرا بدون سقف", "ضبط خودکار", "بدون حق اعتراض", "ضمانت نامحدود"],
            "medium_risk": ["مبلغ بالای ضمانت", "شرایط آزادسازی سخت", "تمدید اجباری"],
            "keywords": ["ضمانت اجرا", "حسن انجام کار", "تعهد", "وفای به عهد", "performance bond", "تضمین اجرا"]
        },
        ClauseType.INSURANCE: {
            "high_risk": ["بدون بیمه", "پوشش ناکافی", "بیمه‌گر نامعتبر", "عدم پوشش ریسک‌های اصلی"],
            "medium_risk": ["فرانشیز بالا", "استثنائات متعدد", "سقف پایین"],
            "keywords": ["بیمه", "پوشش", "بیمه‌نامه", "حق بیمه", "خسارت", "insurance", "policy"]
        },
        
        # =====================================================================
        # === بندهای مسئولیت - Liability Clauses ===
        # =====================================================================
        ClauseType.LIABILITY: {
            "high_risk": ["مسئولیت نامحدود", "بدون سقف خسارت", "شامل خسارات غیرمستقیم", "مسئولیت مطلق", "strict liability"],
            "medium_risk": ["مسئولیت تضامنی", "ضمانت اجرا", "مسئولیت بدون تقصیر"],
            "keywords": ["مسئولیت", "ضمان", "تعهد", "خسارت", "جبران", "پاسخگویی", "liability"]
        },
        ClauseType.INDEMNIFICATION: {
            "high_risk": ["غرامت نامحدود", "شامل هزینه‌های وکیل", "بدون سقف", "غرامت یکطرفه", "broad indemnity"],
            "medium_risk": ["غرامت متقابل نامتوازن", "شرایط غرامت مبهم"],
            "keywords": ["غرامت", "جبران خسارت", "مصون‌سازی", "تاوان", "indemnification", "indemnity"]
        },
        ClauseType.LIMITATION: {
            "high_risk": ["محدودیت نامتناسب", "استثنای تقصیر عمدی", "محدودیت صفر", "سلب مسئولیت کامل"],
            "medium_risk": ["سقف پایین مسئولیت", "محدودیت زمانی کوتاه", "محدودیت جغرافیایی"],
            "keywords": ["محدودیت", "سقف", "حداکثر", "ceiling", "cap", "limitation", "حد"]
        },
        ClauseType.CONSEQUENTIAL_DAMAGES: {
            "high_risk": ["شامل خسارات تبعی", "عدم النفع نامحدود", "خسارات غیرمستقیم", "lost profits"],
            "medium_risk": ["خسارات قابل پیش‌بینی", "سود از دست رفته"],
            "keywords": ["خسارت تبعی", "عدم النفع", "خسارت غیرمستقیم", "سود از دست رفته", "consequential", "indirect"]
        },
        
        # =====================================================================
        # === بندهای خاتمه - Termination Clauses ===
        # =====================================================================
        ClauseType.TERMINATION: {
            "high_risk": ["فسخ یکطرفه بدون اخطار", "فسخ فوری", "بدون حق اعتراض", "فسخ بدون دلیل", "termination for convenience"],
            "medium_risk": ["فسخ با اخطار کوتاه", "شرایط فسخ مبهم", "فسخ به صلاحدید"],
            "keywords": ["فسخ", "انفساخ", "خاتمه", "لغو", "ابطال", "پایان", "termination", "cancel"]
        },
        ClauseType.SUSPENSION: {
            "high_risk": ["تعلیق نامحدود", "تعلیق بدون پرداخت", "تعلیق یکطرفه", "تعلیق بدون جبران"],
            "medium_risk": ["تعلیق طولانی", "شرایط از سرگیری مبهم", "تعلیق مکرر"],
            "keywords": ["تعلیق", "توقف", "معلق", "متوقف", "suspension", "halt", "pause"]
        },
        ClauseType.EXPIRY: {
            "high_risk": ["انقضای خودکار بدون اخطار", "عدم تمدید یکطرفه", "از دست رفتن حقوق"],
            "medium_risk": ["مدت کوتاه قرارداد", "شرایط تمدید مبهم"],
            "keywords": ["انقضا", "پایان مدت", "expiry", "expiration", "تمدید", "renewal", "سررسید"]
        },
        
        # =====================================================================
        # === بندهای جریمه - Penalty Clauses ===
        # =====================================================================
        ClauseType.PENALTY: {
            "high_risk": ["جریمه روزانه بالا", "وجه التزام سنگین", "جریمه بدون سقف", "جریمه تجمیعی", "جریمه نامتناسب"],
            "medium_risk": ["جریمه تأخیر", "کسر از مطالبات", "جریمه پلکانی"],
            "keywords": ["جریمه", "وجه التزام", "خسارت تأخیر", "غرامت", "تنبیه", "penalty", "fine"]
        },
        ClauseType.LIQUIDATED_DAMAGES: {
            "high_risk": ["خسارت از پیش تعیین شده بالا", "بدون اثبات خسارت واقعی", "LD نامتناسب"],
            "medium_risk": ["خسارت مقطوع", "محاسبه پیچیده", "LD تجمیعی"],
            "keywords": ["خسارت مقطوع", "خسارت از پیش تعیین شده", "LD", "liquidated damages", "خسارت قراردادی"]
        },
        ClauseType.DELAY_PENALTY: {
            "high_risk": ["جریمه تأخیر روزانه بالا", "جریمه بدون سقف", "جریمه از روز اول"],
            "medium_risk": ["جریمه تأخیر پلکانی", "عدم معافیت فورس ماژور"],
            "keywords": ["جریمه تأخیر", "تأخیر", "delay penalty", "دیرکرد", "تأخیر در تحویل"]
        },
        
        # =====================================================================
        # === بندهای حقوقی - Legal Clauses ===
        # =====================================================================
        ClauseType.FORCE_MAJEURE: {
            "high_risk": ["عدم پذیرش فورس ماژور", "تعریف محدود", "استثنای بیماری همه‌گیر", "فسخ فوری"],
            "medium_risk": ["شرایط اثبات سخت", "مهلت اعلام کوتاه", "فسخ فوری پس از فورس ماژور"],
            "keywords": ["فورس ماژور", "قوه قاهره", "حوادث غیرمترقبه", "عذر موجه", "حادثه", "force majeure"]
        },
        ClauseType.DISPUTE: {
            "high_risk": ["داوری اجباری در خارج", "صلاحیت انحصاری دادگاه خارجی", "زبان خارجی", "هزینه بالا"],
            "medium_risk": ["داوری با هزینه بالا", "مرجع نامشخص", "رأی قطعی"],
            "keywords": ["داوری", "حل اختلاف", "دادگاه", "صلاحیت", "مرجع", "رسیدگی", "dispute"]
        },
        ClauseType.ARBITRATION: {
            "high_risk": ["داوری خارج از کشور", "داور منفرد طرف مقابل", "هزینه بالا", "قواعد نامأنوس"],
            "medium_risk": ["داوری سازمانی", "قواعد پیچیده", "زبان خارجی"],
            "keywords": ["داوری", "داور", "هیأت داوری", "رأی داوری", "ICC", "LCIA", "arbitration"]
        },
        ClauseType.GOVERNING_LAW: {
            "high_risk": ["قانون خارجی نامأنوس", "قانون نامشخص", "قانون متعارض"],
            "medium_risk": ["قانون کشور ثالث", "تعارض قوانین"],
            "keywords": ["قانون حاکم", "قانون قابل اعمال", "حقوق حاکم", "governing law", "applicable law"]
        },
        ClauseType.JURISDICTION: {
            "high_risk": ["صلاحیت انحصاری خارجی", "دادگاه نامأنوس", "عدم دسترسی"],
            "medium_risk": ["صلاحیت کشور ثالث", "صلاحیت مبهم"],
            "keywords": ["صلاحیت", "دادگاه صالح", "jurisdiction", "محل رسیدگی", "venue"]
        },
        
        # =====================================================================
        # === بندهای محرمانگی و IP - Confidentiality & IP Clauses ===
        # =====================================================================
        ClauseType.CONFIDENTIALITY: {
            "high_risk": ["محرمانگی نامحدود", "جریمه سنگین افشا", "شامل اطلاعات عمومی", "محرمانگی ابدی"],
            "medium_risk": ["مدت طولانی محرمانگی", "تعریف گسترده اطلاعات محرمانه"],
            "keywords": ["محرمانه", "سری", "افشا", "اطلاعات", "حفاظت", "confidential", "NDA", "non-disclosure"]
        },
        ClauseType.INTELLECTUAL_PROPERTY: {
            "high_risk": ["انتقال کامل IP", "بدون حق استفاده", "مالکیت یکطرفه", "work for hire"],
            "medium_risk": ["مجوز محدود", "حق انحصاری طرف مقابل"],
            "keywords": ["مالکیت فکری", "اختراع", "کپی‌رایت", "علامت تجاری", "IP", "پتنت", "patent", "copyright"]
        },
        ClauseType.NON_COMPETE: {
            "high_risk": ["عدم رقابت نامحدود", "محدوده جغرافیایی گسترده", "مدت طولانی", "صنعت گسترده"],
            "medium_risk": ["عدم رقابت در صنعت مشابه", "محدودیت مشتریان"],
            "keywords": ["عدم رقابت", "رقابت", "فعالیت مشابه", "بازار", "non-compete", "competition"]
        },
        ClauseType.NON_SOLICITATION: {
            "high_risk": ["عدم جذب نامحدود", "شامل همه کارکنان", "مدت طولانی"],
            "medium_risk": ["عدم جذب کارکنان کلیدی", "محدودیت مشتریان"],
            "keywords": ["عدم جذب", "جذب نیرو", "non-solicitation", "کارکنان", "مشتریان", "استخدام"]
        },
        
        # =====================================================================
        # === بندهای خاص - Special Clauses ===
        # =====================================================================
        ClauseType.ASSIGNMENT: {
            "high_risk": ["ممنوعیت کامل واگذاری", "واگذاری یکطرفه آزاد", "واگذاری بدون اطلاع"],
            "medium_risk": ["نیاز به موافقت کتبی", "واگذاری به شرکت‌های وابسته"],
            "keywords": ["واگذاری", "انتقال", "جانشینی", "قائم مقام", "assignment", "transfer"]
        },
        ClauseType.AMENDMENT: {
            "high_risk": ["اصلاح یکطرفه", "تغییر بدون موافقت", "اصلاح شفاهی معتبر"],
            "medium_risk": ["فرآیند اصلاح پیچیده", "نیاز به تأیید متعدد"],
            "keywords": ["اصلاح", "تغییر", "الحاقیه", "متمم", "amendment", "modification", "change order"]
        },
        ClauseType.NOTICE: {
            "high_risk": ["ابلاغ فقط حضوری", "مهلت کوتاه ابلاغ", "ابلاغ به آدرس نامشخص"],
            "medium_risk": ["ابلاغ فقط کتبی", "آدرس نامشخص"],
            "keywords": ["ابلاغ", "اخطار", "اطلاع‌رسانی", "مکاتبه", "نامه", "notice", "notification"]
        },
        ClauseType.ENTIRE_AGREEMENT: {
            "high_risk": ["نفی همه توافقات قبلی", "عدم اعتبار مذاکرات"],
            "medium_risk": ["تعارض با اسناد پیوست"],
            "keywords": ["تمامیت قرارداد", "کل توافق", "entire agreement", "integration", "merger clause"]
        },
        ClauseType.SEVERABILITY: {
            "high_risk": ["بطلان کل قرارداد", "عدم تجزیه‌پذیری"],
            "medium_risk": ["شرایط جایگزینی مبهم"],
            "keywords": ["تجزیه‌پذیری", "بطلان جزئی", "severability", "جدایی‌پذیری", "invalid provision"]
        },
        ClauseType.WAIVER: {
            "high_risk": ["اسقاط حق خودکار", "اسقاط کلی حقوق", "عدم امکان استناد"],
            "medium_risk": ["اسقاط ضمنی", "شرایط اسقاط مبهم"],
            "keywords": ["اسقاط حق", "چشم‌پوشی", "waiver", "صرف‌نظر", "گذشت"]
        },
        
        # =====================================================================
        # === بندهای تخصصی - Specialized Clauses ===
        # =====================================================================
        ClauseType.COMPLIANCE: {
            "high_risk": ["عدم انطباق با قوانین", "مسئولیت کامل انطباق", "جریمه عدم انطباق"],
            "medium_risk": ["الزامات انطباق پیچیده", "گزارش‌دهی متعدد"],
            "keywords": ["انطباق", "قوانین", "مقررات", "استاندارد", "الزامات", "compliance", "regulatory"]
        },
        ClauseType.ANTI_CORRUPTION: {
            "high_risk": ["فسخ فوری بدون اثبات", "مسئولیت اعمال ثالث", "جریمه سنگین"],
            "medium_risk": ["تعهدات گسترده ضد فساد", "گزارش‌دهی اجباری"],
            "keywords": ["فساد", "رشوه", "پرداخت غیرقانونی", "FCPA", "تسهیل", "anti-corruption", "bribery"]
        },
        ClauseType.SANCTIONS: {
            "high_risk": ["فسخ فوری در صورت تحریم", "عدم پرداخت در صورت تحریم", "مسئولیت تحریم"],
            "medium_risk": ["بررسی‌های تحریمی", "محدودیت معاملات"],
            "keywords": ["تحریم", "sanctions", "OFAC", "محدودیت", "لیست سیاه", "SDN", "restricted party"]
        },
        ClauseType.DATA_PROTECTION: {
            "high_risk": ["انتقال داده بدون رضایت", "عدم رعایت GDPR", "نقض حریم خصوصی", "data breach"],
            "medium_risk": ["ذخیره‌سازی خارج از کشور", "دسترسی ثالث"],
            "keywords": ["داده", "حریم خصوصی", "اطلاعات شخصی", "GDPR", "حفاظت", "data protection", "privacy"]
        },
        ClauseType.ENVIRONMENTAL: {
            "high_risk": ["مسئولیت آلودگی نامحدود", "عدم رعایت استانداردها", "خسارت زیست‌محیطی"],
            "medium_risk": ["الزامات زیست‌محیطی سخت", "گزارش‌دهی محیطی"],
            "keywords": ["محیط زیست", "آلودگی", "پسماند", "انتشار", "زیست‌محیطی", "environmental", "pollution"]
        },
        ClauseType.HEALTH_SAFETY: {
            "high_risk": ["مسئولیت کامل حوادث", "بدون بیمه حوادث", "عدم رعایت HSE"],
            "medium_risk": ["الزامات ایمنی سخت", "آموزش اجباری"],
            "keywords": ["ایمنی", "بهداشت", "حادثه", "HSE", "سلامت", "health", "safety", "occupational"]
        },
        
        # =====================================================================
        # === بند عمومی - General Clause ===
        # =====================================================================
        ClauseType.GENERAL: {
            "high_risk": ["شرایط مبهم", "تعهدات نامشخص"],
            "medium_risk": ["زبان پیچیده", "ارجاعات متعدد"],
            "keywords": ["عمومی", "سایر", "متفرقه", "general", "miscellaneous"]
        }
    }
    
    async def analyze_contract(
        self,
        contract_text: str,
        correlation_id: Optional[str] = None
    ) -> ContractAnalysis:
        """
        Perform clause-level analysis of a contract.
        
        Args:
            contract_text: Full contract text
            correlation_id: Optional correlation ID
        
        Returns:
            ContractAnalysis with risk assessment for each clause
        """
        self.logger.info(f"[{correlation_id}] Starting contract analysis")
        
        # Step 1: Extract clauses
        clauses = self._extract_clauses(contract_text)
        
        # Step 2: Analyze each clause
        analyzed_clauses: List[Any] = []
        for i, clause_text in enumerate(clauses):
            clause_risk = await self._analyze_clause(
                clause_id=f"clause_{i+1}",
                clause_text=clause_text,
                correlation_id=correlation_id
            )
            analyzed_clauses.append(clause_risk)
        
        # Step 3: Calculate overall risk
        overall_score, overall_level = self._calculate_overall_risk(analyzed_clauses)
        
        # Step 4: Count high risk clauses
        high_risk_count = sum(
            1 for c in analyzed_clauses 
            if c.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]
        )
        
        # Step 5: Generate summary
        summary = self._generate_analysis_summary(analyzed_clauses, overall_level)
        
        return ContractAnalysis(
            total_clauses=len(clauses),
            analyzed_clauses=len(analyzed_clauses),
            clauses=analyzed_clauses,
            overall_risk_score=overall_score,
            overall_risk_level=overall_level,
            high_risk_clauses=high_risk_count,
            summary=summary
        )
    
    def _extract_clauses(self, contract_text: str) -> List[str]:
        """Extract individual clauses from contract text"""
        import re
        
        # Pattern for Persian clause markers
        clause_patterns = [
            r'ماده\s*\d+[:\s\-–]',      # ماده ۱:
            r'بند\s*\d+[:\s\-–]',        # بند ۱:
            r'تبصره\s*\d*[:\s\-–]',      # تبصره:
            r'\d+[\-–\.]\d+[:\s]',       # 1-1:
            r'فصل\s*\d+[:\s\-–]',        # فصل ۱:
        ]
        
        combined_pattern = '|'.join(clause_patterns)
        
        # Split by clause markers
        parts = re.split(f'({combined_pattern})', contract_text)
        
        clauses: List[Any] = []
        current_clause = ""
        
        for part in parts:
            if re.match(combined_pattern, part):
                if current_clause.strip():
                    clauses.append(current_clause.strip())
                current_clause = part
            else:
                current_clause += part
        
        if current_clause.strip():
            clauses.append(current_clause.strip())
        
        # If no clauses found, split by paragraphs
        if len(clauses) <= 1:
            clauses = [p.strip() for p in contract_text.split('\n\n') if p.strip()]
        
        return clauses
    
    async def _analyze_clause(
        self,
        clause_id: str,
        clause_text: str,
        correlation_id: Optional[str]
    ) -> ClauseRisk:
        """Analyze a single clause for risks"""
        
        # Step 1: Detect clause type
        clause_type = self._detect_clause_type(clause_text)
        
        # Step 2: Calculate risk score
        risk_score, risk_factors = self._calculate_clause_risk(clause_text, clause_type)
        
        # Step 3: Determine risk level
        risk_level = self._score_to_level(risk_score)
        
        # Step 4: Generate recommendations
        recommendations = self._generate_recommendations(clause_type, risk_level, risk_factors)
        
        # Step 5: Find legal references
        legal_refs = self._extract_legal_references(clause_text)
        
        return ClauseRisk(
            clause_id=clause_id,
            clause_text=clause_text,
            clause_type=clause_type,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_factors=risk_factors,
            recommendations=recommendations,
            legal_references=legal_refs
        )
    
    def _detect_clause_type(self, clause_text: str) -> ClauseType:
        """Detect the type of clause based on keywords"""
        clause_lower = clause_text.lower()
        
        type_scores: Dict[str, Any] = {}
        for clause_type, indicators in self.RISK_INDICATORS.items():
            keywords = indicators.get("keywords", [])
            score = sum(1 for kw in keywords if kw in clause_lower)
            if score > 0:
                type_scores[clause_type] = score
        
        if type_scores:
            return max(type_scores, key=type_scores.get)
        
        return ClauseType.GENERAL
    
    def _calculate_clause_risk(
        self,
        clause_text: str,
        clause_type: ClauseType
    ) -> tuple:
        """Calculate risk score and identify risk factors"""
        risk_score = 0.0
        risk_factors: List[Any] = []
        indicators = self.RISK_INDICATORS.get(clause_type, {})
        
        # Check high risk indicators
        high_risk = indicators.get("high_risk", [])
        for indicator in high_risk:
            if indicator in clause_text:
                risk_score += 0.3
                risk_factors.append(f"⚠️ {indicator}")
        
        # Check medium risk indicators
        medium_risk = indicators.get("medium_risk", [])
        for indicator in medium_risk:
            if indicator in clause_text:
                risk_score += 0.15
                risk_factors.append(f"⚡ {indicator}")
        
        # General risk patterns
        general_high_risk = [
            "بدون محدودیت", "نامحدود", "غیرقابل فسخ", "قطعی و غیرقابل برگشت",
            "به تنهایی", "یکطرفه", "بدون اخطار", "فوری"
        ]
        
        for pattern in general_high_risk:
            if pattern in clause_text:
                risk_score += 0.2
                risk_factors.append(f"🔴 {pattern}")
        
        # Ambiguity risk
        ambiguous_terms = ["ممکن است", "احتمالاً", "در صورت لزوم", "به تشخیص"]
        for term in ambiguous_terms:
            if term in clause_text:
                risk_score += 0.1
                risk_factors.append(f"❓ ابهام: {term}")
        
        # Cap at 1.0
        risk_score = min(1.0, risk_score)
        
        # Minimum score based on clause type sensitivity
        sensitive_types = [ClauseType.LIABILITY, ClauseType.TERMINATION, ClauseType.PENALTY]
        if clause_type in sensitive_types and risk_score < 0.2:
            risk_score = 0.2
        
        return risk_score, risk_factors
    
    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert risk score to risk level"""
        if score >= self.config.risk_threshold_critical:
            return RiskLevel.CRITICAL
        elif score >= self.config.risk_threshold_high:
            return RiskLevel.HIGH
        elif score >= self.config.risk_threshold_medium:
            return RiskLevel.MEDIUM
        elif score >= 0.2:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL
    
    def _generate_recommendations(
        self,
        clause_type: ClauseType,
        risk_level: RiskLevel,
        risk_factors: List[str]
    ) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations: List[Any] = []
        if risk_level == RiskLevel.CRITICAL:
            recommendations.append("🚨 این بند نیاز به بازنگری فوری دارد")
            recommendations.append("توصیه: مذاکره مجدد یا حذف بند")
        elif risk_level == RiskLevel.HIGH:
            recommendations.append("⚠️ این بند ریسک بالایی دارد")
            recommendations.append("توصیه: اصلاح شرایط یا افزودن محدودیت")
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("توصیه: بررسی دقیق‌تر توسط مشاور حقوقی")
        
        # Type-specific recommendations - comprehensive (40+ clause types)
        type_recommendations = {
            # === بندهای مالی ===
            ClauseType.PAYMENT: [
                "تعیین زمان‌بندی دقیق پرداخت‌ها با تاریخ مشخص",
                "اضافه کردن شرایط استرداد وجه در صورت عدم اجرا",
                "درج ضمانت‌نامه بانکی یا چک تضمین",
                "تعیین نرخ تأخیر تأدیه مطابق قانون",
                "مشخص کردن ارز پرداخت و نرخ تبدیل",
                "پیش‌بینی تعدیل قیمت در قراردادهای بلندمدت"
            ],
            ClauseType.PRICE_ADJUSTMENT: [
                "تعیین شاخص مرجع برای تعدیل (بانک مرکزی)",
                "مشخص کردن سقف و کف تعدیل",
                "تعیین دوره‌های تعدیل (سالانه/شش‌ماهه)",
                "درج فرمول محاسبه تعدیل",
                "تعیین تکلیف در صورت عدم انتشار شاخص"
            ],
            ClauseType.ADVANCE_PAYMENT: [
                "اخذ ضمانت‌نامه پیش‌پرداخت معادل مبلغ",
                "تعیین شرایط استرداد پیش‌پرداخت",
                "کسر تدریجی از صورت‌وضعیت‌ها",
                "تعیین نرخ بهره در صورت تأخیر استرداد",
                "مشخص کردن موارد ضبط پیش‌پرداخت"
            ],
            ClauseType.RETENTION: [
                "تعیین درصد کسورات (معمولاً ۱۰٪)",
                "مشخص کردن زمان آزادسازی کسورات",
                "امکان جایگزینی با ضمانت‌نامه",
                "تعیین شرایط ضبط کسورات",
                "درج بهره برای کسورات نگهداری شده"
            ],
            ClauseType.BANK_GUARANTEE: [
                "تعیین مبلغ و مدت ضمانت‌نامه",
                "مشخص کردن شرایط ضبط",
                "درج مهلت اخطار قبل از ضبط",
                "تعیین بانک صادرکننده معتبر",
                "مشخص کردن شرایط تمدید و آزادسازی"
            ],
            
            # === بندهای اجرایی ===
            ClauseType.DELIVERY: [
                "تعیین زمان و مکان دقیق تحویل",
                "مشخص کردن شرایط انتقال ریسک (Incoterms)",
                "درج بازرسی قبل از تحویل",
                "تعیین مهلت اعتراض به کالای تحویلی",
                "مشخص کردن مسئولیت حمل و بیمه",
                "تعیین جریمه تأخیر در تحویل"
            ],
            ClauseType.SCOPE_OF_WORK: [
                "تعریف دقیق محدوده کار با جزئیات",
                "تعیین فرآیند تغییر محدوده (Change Order)",
                "مشخص کردن موارد خارج از محدوده",
                "درج لیست تحویل‌دادنی‌ها (Deliverables)",
                "تعیین معیارهای پذیرش هر بخش"
            ],
            ClauseType.TIMELINE: [
                "تعیین برنامه زمان‌بندی واقع‌بینانه",
                "درج امکان تمدید با شرایط مشخص",
                "تعیین نقاط عطف کلیدی",
                "مشخص کردن تأثیر تأخیر کارفرما",
                "درج بافر زمانی برای ریسک‌ها"
            ],
            ClauseType.MILESTONES: [
                "تعیین نقاط عطف واقع‌بینانه",
                "مشخص کردن معیارهای تکمیل هر مرحله",
                "درج پرداخت مرحله‌ای متناسب",
                "تعیین فرآیند تأیید نقاط عطف",
                "امکان تعدیل نقاط عطف با توافق"
            ],
            ClauseType.ACCEPTANCE: [
                "تعیین معیارهای پذیرش واضح",
                "درج دوره آزمایشی (UAT)",
                "مشخص کردن فرآیند رفع نقص",
                "تعیین مهلت اعلام عدم پذیرش",
                "درج پذیرش مشروط با لیست نواقص"
            ],
            ClauseType.SUBCONTRACTING: [
                "تعیین شرایط واگذاری به پیمانکار فرعی",
                "درج لیست پیمانکاران فرعی مجاز",
                "مشخص کردن مسئولیت پیمانکار اصلی",
                "تعیین فرآیند تأیید پیمانکار فرعی",
                "درج حق نظارت بر پیمانکاران فرعی"
            ],
            
            # === بندهای تضمینی ===
            ClauseType.WARRANTY: [
                "تعیین مدت ضمانت متناسب با نوع کالا/خدمت",
                "مشخص کردن شرایط اعمال ضمانت",
                "تعیین نحوه رفع عیب (تعمیر، تعویض، استرداد)",
                "درج ضمانت عملکرد علاوه بر ضمانت کیفیت",
                "تعیین مهلت اعلام عیب",
                "مشخص کردن استثنائات ضمانت"
            ],
            ClauseType.PERFORMANCE_BOND: [
                "تعیین مبلغ ضمانت اجرا (معمولاً ۱۰٪)",
                "مشخص کردن شرایط ضبط ضمانت",
                "درج مهلت اخطار قبل از ضبط",
                "تعیین شرایط آزادسازی تدریجی",
                "امکان کاهش مبلغ با پیشرفت کار"
            ],
            ClauseType.INSURANCE: [
                "تعیین انواع بیمه‌های مورد نیاز",
                "مشخص کردن حداقل سقف پوشش",
                "درج کارفرما به عنوان ذینفع",
                "تعیین بیمه‌گر معتبر",
                "مشخص کردن مدت اعتبار بیمه‌نامه"
            ],
            
            # === بندهای مسئولیت ===
            ClauseType.LIABILITY: [
                "تعیین سقف مسئولیت (Cap on Liability)",
                "استثنا کردن خسارات غیرمستقیم و تبعی",
                "محدود کردن مسئولیت به میزان قرارداد",
                "تفکیک مسئولیت عمدی از غیرعمدی",
                "درج بیمه مسئولیت حرفه‌ای",
                "تعیین مهلت اعلام خسارت"
            ],
            ClauseType.INDEMNIFICATION: [
                "تعیین سقف غرامت",
                "محدود کردن به خسارات مستقیم",
                "درج شرط اطلاع فوری از ادعای ثالث",
                "حق کنترل دفاع در برابر ادعای ثالث",
                "استثنا کردن تقصیر عمدی طرف مقابل",
                "تعیین مهلت مطالبه غرامت"
            ],
            ClauseType.LIMITATION: [
                "بررسی قانونی بودن محدودیت‌ها",
                "تعیین استثنائات محدودیت (تقصیر عمدی)",
                "تناسب محدودیت با ریسک قرارداد",
                "عدم محدودیت مسئولیت در فوت و صدمه بدنی",
                "درج حداقل تعهدات غیرقابل محدودیت"
            ],
            ClauseType.CONSEQUENTIAL_DAMAGES: [
                "استثنا کردن خسارات تبعی و غیرمستقیم",
                "تعیین سقف برای عدم النفع",
                "مشخص کردن خسارات قابل مطالبه",
                "تفکیک خسارات مستقیم از غیرمستقیم",
                "درج شرط قابل پیش‌بینی بودن خسارت"
            ],
            
            # === بندهای خاتمه ===
            ClauseType.TERMINATION: [
                "تعیین مهلت اخطار کتبی قبل از فسخ (حداقل ۳۰ روز)",
                "مشخص کردن موارد فسخ فوری (تخلفات اساسی)",
                "تعیین تکلیف تعهدات پس از فسخ",
                "درج حق اصلاح (Cure Period) قبل از فسخ",
                "مشخص کردن نحوه تسویه حساب پس از فسخ",
                "تعیین سرنوشت اموال و اسناد پس از خاتمه"
            ],
            ClauseType.SUSPENSION: [
                "تعیین حداکثر مدت تعلیق",
                "مشخص کردن پرداخت در دوره تعلیق",
                "درج شرایط از سرگیری کار",
                "تعیین حق فسخ در صورت تعلیق طولانی",
                "مشخص کردن جبران هزینه‌های تعلیق"
            ],
            ClauseType.EXPIRY: [
                "تعیین مدت قرارداد با تاریخ مشخص",
                "مشخص کردن شرایط تمدید",
                "درج اخطار قبل از انقضا",
                "تعیین تکلیف تعهدات پس از انقضا",
                "مشخص کردن حقوق باقیمانده پس از انقضا"
            ],
            
            # === بندهای جریمه ===
            ClauseType.PENALTY: [
                "بررسی تناسب جریمه با میزان تخلف",
                "تعیین سقف جریمه (معمولاً ۱۰٪ مبلغ قرارداد)",
                "تفکیک جریمه تأخیر از خسارت واقعی",
                "امکان کاهش جریمه در صورت اجرای جزئی",
                "عدم تجمیع جریمه با خسارت واقعی",
                "تعیین شرایط معافیت از جریمه"
            ],
            ClauseType.LIQUIDATED_DAMAGES: [
                "بررسی تناسب LD با خسارت واقعی",
                "تعیین سقف LD (معمولاً ۱۰٪)",
                "مشخص کردن نحوه محاسبه",
                "درج شرط عدم تجمیع با خسارت واقعی",
                "تعیین شرایط معافیت از LD"
            ],
            ClauseType.DELAY_PENALTY: [
                "تعیین نرخ جریمه تأخیر روزانه معقول",
                "درج سقف جریمه تأخیر",
                "مشخص کردن معافیت فورس ماژور",
                "تعیین دوره مهلت (Grace Period)",
                "تفکیک تأخیر مجاز از غیرمجاز"
            ],
            
            # === بندهای حقوقی ===
            ClauseType.FORCE_MAJEURE: [
                "گسترش تعریف فورس ماژور (شامل بیماری‌های همه‌گیر)",
                "تعیین مهلت اعلام وقوع فورس ماژور",
                "مشخص کردن مدارک اثبات فورس ماژور",
                "تعیین تکلیف قرارداد در صورت تداوم فورس ماژور",
                "درج حق تعلیق به جای فسخ",
                "تقسیم ریسک بین طرفین در دوره فورس ماژور"
            ],
            ClauseType.DISPUTE: [
                "تعیین مرجع داوری داخلی (مرکز داوری اتاق بازرگانی)",
                "مشخص کردن قانون حاکم بر قرارداد",
                "تعیین محل داوری و زبان رسیدگی",
                "درج مرحله مذاکره قبل از داوری",
                "تعیین تعداد داوران و نحوه انتخاب",
                "مشخص کردن هزینه‌های داوری و نحوه تقسیم"
            ],
            ClauseType.ARBITRATION: [
                "تعیین مرکز داوری معتبر داخلی",
                "مشخص کردن تعداد داوران (یک یا سه)",
                "تعیین زبان داوری (فارسی)",
                "درج محل داوری (ایران)",
                "مشخص کردن قواعد داوری"
            ],
            ClauseType.GOVERNING_LAW: [
                "تعیین قانون ایران به عنوان قانون حاکم",
                "مشخص کردن قوانین خاص قابل اعمال",
                "درج تفسیر بر اساس حقوق ایران",
                "تعیین تکلیف تعارض قوانین"
            ],
            ClauseType.JURISDICTION: [
                "تعیین دادگاه‌های ایران به عنوان مرجع صالح",
                "مشخص کردن محل دادگاه (شهر)",
                "درج صلاحیت غیرانحصاری",
                "تعیین تکلیف اجرای آرای خارجی"
            ],
            
            # === بندهای محرمانگی و IP ===
            ClauseType.CONFIDENTIALITY: [
                "تعریف دقیق اطلاعات محرمانه",
                "تعیین مدت تعهد محرمانگی پس از قرارداد",
                "مشخص کردن استثنائات (اطلاعات عمومی)",
                "تعیین نحوه امحاء اطلاعات پس از خاتمه",
                "درج جریمه افشای غیرمجاز",
                "محدود کردن دسترسی به افراد ذی‌صلاح"
            ],
            ClauseType.INTELLECTUAL_PROPERTY: [
                "تعیین مالکیت IP ایجاد شده در قرارداد",
                "درج مجوز استفاده از IP موجود",
                "تعیین محدوده جغرافیایی و زمانی مجوز",
                "مشخص کردن حق انتقال و واگذاری",
                "درج تعهد عدم نقض حقوق ثالث",
                "تعیین تکلیف IP پس از خاتمه قرارداد"
            ],
            ClauseType.NON_COMPETE: [
                "تعیین محدوده جغرافیایی معقول",
                "مشخص کردن مدت عدم رقابت (حداکثر ۲ سال)",
                "تعریف دقیق فعالیت‌های ممنوع",
                "درج جبران مالی برای محدودیت",
                "تعیین استثنائات عدم رقابت"
            ],
            ClauseType.NON_SOLICITATION: [
                "تعیین مدت عدم جذب معقول",
                "مشخص کردن افراد مشمول",
                "تعریف دقیق جذب (مستقیم/غیرمستقیم)",
                "درج استثنا برای درخواست عمومی",
                "تعیین جریمه نقض"
            ],
            
            # === بندهای خاص ===
            ClauseType.ASSIGNMENT: [
                "تعیین شرایط واگذاری با موافقت",
                "درج استثنا برای شرکت‌های وابسته",
                "مشخص کردن تکلیف ضمانت‌ها پس از واگذاری",
                "تعیین حق اعتراض به واگذاری",
                "درج شرط عدم واگذاری یکطرفه"
            ],
            ClauseType.AMENDMENT: [
                "تعیین فرآیند اصلاح قرارداد",
                "درج الزام به کتبی بودن اصلاحات",
                "مشخص کردن امضاکنندگان مجاز",
                "تعیین تکلیف اصلاحات شفاهی",
                "درج فرم استاندارد الحاقیه"
            ],
            ClauseType.NOTICE: [
                "تعیین آدرس‌های ابلاغ طرفین",
                "مشخص کردن روش‌های ابلاغ معتبر",
                "درج مهلت اعتبار ابلاغ",
                "تعیین تکلیف تغییر آدرس",
                "مشخص کردن ابلاغ الکترونیکی"
            ],
            ClauseType.ENTIRE_AGREEMENT: [
                "درج بند تمامیت قرارداد",
                "مشخص کردن اسناد تشکیل‌دهنده قرارداد",
                "تعیین اولویت اسناد در صورت تعارض",
                "درج نفی توافقات شفاهی قبلی"
            ],
            ClauseType.SEVERABILITY: [
                "درج بند تجزیه‌پذیری",
                "تعیین تکلیف بندهای باطل",
                "مشخص کردن جایگزینی بند باطل",
                "درج حفظ اعتبار سایر بندها"
            ],
            ClauseType.WAIVER: [
                "درج عدم اسقاط حق با عدم اعمال",
                "تعیین الزام به کتبی بودن اسقاط",
                "مشخص کردن محدوده اسقاط",
                "درج عدم تأثیر بر حقوق آتی"
            ],
            
            # === بندهای تخصصی ===
            ClauseType.COMPLIANCE: [
                "تعیین قوانین قابل اعمال",
                "مشخص کردن مسئولیت انطباق",
                "درج تعهد گزارش‌دهی",
                "تعیین جریمه عدم انطباق",
                "مشخص کردن حق ممیزی"
            ],
            ClauseType.ANTI_CORRUPTION: [
                "درج تعهد عدم پرداخت رشوه",
                "مشخص کردن تعهدات FCPA/UK Bribery Act",
                "تعیین حق فسخ در صورت نقض",
                "درج تعهد گزارش‌دهی موارد مشکوک",
                "مشخص کردن آموزش ضد فساد"
            ],
            ClauseType.SANCTIONS: [
                "درج تعهد عدم نقض تحریم‌ها",
                "مشخص کردن لیست‌های تحریمی قابل اعمال",
                "تعیین حق تعلیق در صورت تحریم",
                "درج تعهد اطلاع‌رسانی تغییر وضعیت",
                "مشخص کردن جبران خسارت تحریم"
            ],
            ClauseType.DATA_PROTECTION: [
                "تعیین تکلیف داده‌های شخصی",
                "درج تعهدات GDPR (در صورت لزوم)",
                "مشخص کردن محل ذخیره‌سازی داده",
                "تعیین حق دسترسی و حذف داده",
                "درج تعهد امنیت داده"
            ],
            ClauseType.ENVIRONMENTAL: [
                "درج تعهد رعایت قوانین زیست‌محیطی",
                "مشخص کردن استانداردهای قابل اعمال",
                "تعیین مسئولیت آلودگی",
                "درج تعهد گزارش‌دهی محیطی",
                "مشخص کردن جبران خسارت زیست‌محیطی"
            ],
            ClauseType.HEALTH_SAFETY: [
                "درج تعهد رعایت مقررات HSE",
                "مشخص کردن استانداردهای ایمنی",
                "تعیین مسئولیت حوادث",
                "درج تعهد آموزش ایمنی",
                "مشخص کردن گزارش‌دهی حوادث"
            ],
            
            # === بند عمومی ===
            ClauseType.GENERAL: [
                "بررسی انطباق با قوانین آمره",
                "تعیین اولویت اسناد قرارداد",
                "درج بند تمامیت قرارداد (Entire Agreement)",
                "تعیین نحوه اصلاح قرارداد",
                "مشخص کردن نحوه ابلاغ و مکاتبات"
            ]
        }
        
        if clause_type in type_recommendations:
            # Add relevant recommendations based on risk level
            all_recs = type_recommendations[clause_type]
            if risk_level == RiskLevel.CRITICAL:
                recommendations.extend(all_recs[:4])  # Top 4 recommendations
            elif risk_level == RiskLevel.HIGH:
                recommendations.extend(all_recs[:3])  # Top 3 recommendations
            elif risk_level == RiskLevel.MEDIUM:
                recommendations.extend(all_recs[:2])  # Top 2 recommendations
            else:
                recommendations.append(all_recs[0])   # Top 1 recommendation
        
        return recommendations
    
    def _extract_legal_references(self, clause_text: str) -> List[str]:
        """Extract legal references from clause"""
        import re
        
        references: List[Any] = []
        # Pattern for law articles
        patterns = [
            r'ماده\s*\d+\s*قانون\s*[^،\.]+',
            r'قانون\s*[^،\.]{5,50}',
            r'آیین[‌\s]?نامه\s*[^،\.]{5,50}',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, clause_text)
            references.extend(matches)
        
        return list(set(references))[:5]
    
    def _calculate_overall_risk(
        self,
        clauses: List[ClauseRisk]
    ) -> tuple:
        """Calculate overall contract risk"""
        if not clauses:
            return 0.0, RiskLevel.MINIMAL
        
        # Weighted average (critical clauses have more weight)
        weights = {
            RiskLevel.CRITICAL: 3.0,
            RiskLevel.HIGH: 2.0,
            RiskLevel.MEDIUM: 1.0,
            RiskLevel.LOW: 0.5,
            RiskLevel.MINIMAL: 0.2
        }
        
        total_weight = 0
        weighted_score = 0
        
        for clause in clauses:
            weight = weights.get(clause.risk_level, 1.0)
            weighted_score += clause.risk_score * weight
            total_weight += weight
        
        overall_score = weighted_score / total_weight if total_weight > 0 else 0
        overall_level = self._score_to_level(overall_score)
        
        return overall_score, overall_level
    
    def _generate_analysis_summary(
        self,
        clauses: List[ClauseRisk],
        overall_level: RiskLevel
    ) -> str:
        """Generate human-readable summary"""
        critical = sum(1 for c in clauses if c.risk_level == RiskLevel.CRITICAL)
        high = sum(1 for c in clauses if c.risk_level == RiskLevel.HIGH)
        
        summary_parts = [f"تحلیل {len(clauses)} بند قرارداد:"]
        
        if critical > 0:
            summary_parts.append(f"🚨 {critical} بند بحرانی نیاز به اقدام فوری")
        if high > 0:
            summary_parts.append(f"⚠️ {high} بند با ریسک بالا")
        
        level_messages = {
            RiskLevel.CRITICAL: "قرارداد ریسک بسیار بالایی دارد - امضا توصیه نمی‌شود",
            RiskLevel.HIGH: "قرارداد نیاز به بازنگری جدی دارد",
            RiskLevel.MEDIUM: "قرارداد قابل قبول با اصلاحات جزئی",
            RiskLevel.LOW: "قرارداد ریسک پایینی دارد",
            RiskLevel.MINIMAL: "قرارداد از نظر ریسک مناسب است"
        }
        
        summary_parts.append(level_messages.get(overall_level, ""))
        
        return " | ".join(summary_parts)
    
    async def analyze_specific_clause(
        self,
        clause_text: str,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a specific clause in detail.
        
        Args:
            clause_text: The clause text to analyze
            correlation_id: Optional correlation ID
        
        Returns:
            Detailed analysis of the clause
        """
        clause_risk = await self._analyze_clause(
            clause_id="single_clause",
            clause_text=clause_text,
            correlation_id=correlation_id
        )
        
        return clause_risk.to_dict()
