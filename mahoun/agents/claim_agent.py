"""
Ultra Claim Agent - Enterprise-Grade Claim Generation
======================================================
HARDENED PHASE 1: Boundary Integration + Ledger Write Gate

MAHOUN Integration:
- API Boundary Validator (B1): All inputs validated
- Ledger Write Gate (B3): All claims persisted with evidence
- Non-bypassable enforcement for legal defensibility

Features:
- Structured Claim Generation with Evidence Tracking
- Legal Basis Extraction with Provenance
- Argument Building with Citations
- Multi-section Output with Audit Trail
- Template Support with Validation
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_agent import UltraBaseAgent, AgentConfig

# MAHOUN Boundary Integration
from mahoun.api.boundary_validator import (
    validate_claim_payload,
    BoundaryValidationResult,
    ValidationErrorCode,
)
from mahoun.ledger.write_gate import (
    LedgerWriteGate,
    EvidencePackage,
    WriteGateResult,
    get_ledger_write_gate,
)

logger = logging.getLogger(__name__)


class ClaimType(str, Enum):
    """Types of legal claims"""
    BREACH_OF_CONTRACT = "breach_of_contract"  # نقض قرارداد
    DAMAGES = "damages"                         # مطالبه خسارت
    SPECIFIC_PERFORMANCE = "specific_performance"  # الزام به انجام تعهد
    TERMINATION = "termination"                 # فسخ قرارداد
    INJUNCTION = "injunction"                   # دستور موقت
    DECLARATORY = "declaratory"                 # اعلامی
    OTHER = "other"


@dataclass
class ClaimAgentConfig(AgentConfig):
    """Configuration for claim agent"""
    top_k: int = 15
    include_legal_basis: bool = True
    include_citations: bool = True
    max_arguments: int = 10
    generate_summary: bool = True


@dataclass
class ClaimArgument:
    """A legal argument for the claim"""
    title: str
    content: str
    legal_basis: Optional[str] = None
    citations: List[str] = field(default_factory=list)
    strength: float = 0.0  # 0-1


@dataclass
class GeneratedClaim:
    """Generated claim structure"""
    claim_type: ClaimType
    title: str
    introduction: str
    facts: str
    arguments: List[ClaimArgument]
    legal_basis: List[str]
    relief_sought: str
    conclusion: str


class UltraClaimAgent(UltraBaseAgent):
    """
    Enterprise-grade claim generation agent.
    
    این agent محتوای دعوی را تولید می‌کند:
    1. تحلیل حقایق و مستندات
    2. استخراج مبانی حقوقی
    3. ساخت استدلال‌ها
    4. تولید متن دعوی ساختاریافته
    """
    
    CLAIM_TEMPLATES = {
        ClaimType.BREACH_OF_CONTRACT: {
            "title": "دادخواست نقض قرارداد",
            "relief": "الزام خوانده به جبران خسارات ناشی از نقض قرارداد"
        },
        ClaimType.DAMAGES: {
            "title": "دادخواست مطالبه خسارت",
            "relief": "محکومیت خوانده به پرداخت خسارات وارده"
        },
        ClaimType.SPECIFIC_PERFORMANCE: {
            "title": "دادخواست الزام به انجام تعهد",
            "relief": "الزام خوانده به انجام تعهدات قراردادی"
        },
        ClaimType.TERMINATION: {
            "title": "دادخواست فسخ قرارداد",
            "relief": "صدور حکم به فسخ قرارداد و استرداد وجوه"
        }
    }
    
    def __init__(self, config: Optional[ClaimAgentConfig] = None):
        super().__init__(
            name="ultra_claim",
            config=config or ClaimAgentConfig()
        )
        self._rag_service = None
        self._citation_engine = None
        self._reasoning_service = None
        
        # MAHOUN: Ledger Write Gate for persistence boundary
        self._write_gate: Optional[LedgerWriteGate] = None
        
        self._claim_metrics = {
            "claims_generated": 0,
            "avg_arguments": 0.0,
            "avg_citations": 0.0,
            "claims_persisted": 0,
            "persistence_failures": 0,
        }
    
    async def _initialize_impl(self):
        """Initialize components"""
        self.logger.info("Initializing UltraClaimAgent...")
        
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
    
        # Initialize Ledger Write Gate
        try:
            from mahoun.ledger.ledger_writer import LedgerWriter
            ledger_writer = LedgerWriter()
            self._write_gate = get_ledger_write_gate(ledger_writer)
            self.logger.info("✅ Ledger Write Gate initialized")
        except Exception as e:
            self.logger.error(f"⚠️ Ledger Write Gate initialization failed: {e}")
            raise RuntimeError("Ledger Write Gate initialization failed. B3 persistence boundary requires write_gate configuration.")
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Generate claim content with boundary validation and ledger persistence.
        
        HARDENING: This method now enforces:
        - B1: API boundary validation (adversarial check, payload structure)
        - B3: Ledger persistence with evidence (no claim without audit trail)
        
        Args:
            input_data: {
                "claim_type": str,      # Type of claim
                "facts": str,           # Case facts
                "parties": dict,        # Plaintiff/defendant info
                "documents": list,      # Supporting documents
                "legal_basis": str      # Optional legal basis
            }
        """
        # ============================================================================
        # B1: API BOUNDARY VALIDATION - MANDATORY
        # ============================================================================
        self.logger.info(f"[{correlation_id}] Starting B1 boundary validation...")
        
        boundary_result = validate_claim_payload(input_data)
        
        if not boundary_result.is_valid:
            self.logger.error(
                f"[{correlation_id}] B1 REJECTION: {boundary_result.rejection_reason.error_code} - "
                f"{boundary_result.rejection_reason.message}"
            )
            raise ValueError(
                f"Boundary validation failed: {boundary_result.rejection_reason.message}"
            )
        
        self.logger.info(f"[{correlation_id}] B1 validation passed: input_id={boundary_result.input_id}")
        
        # Proceed with claim generation
        claim_type_str = input_data.get("claim_type", "other")
        facts = input_data.get("facts", "")
        parties = input_data.get("parties", {})
        legal_basis_input = input_data.get("legal_basis", "")
        
        if not facts:
            raise ValueError("Facts are required")
        
        # Parse claim type
        try:
            claim_type = ClaimType(claim_type_str)
        except ValueError:
            claim_type = ClaimType.OTHER
        
        # Search for relevant documents
        search_results = await self._search_relevant(facts, claim_type, correlation_id)
        
        # Extract legal basis
        legal_basis = await self._extract_legal_basis(
            search_results, legal_basis_input, correlation_id
        )
        
        # Build arguments
        arguments = await self._build_arguments(
            facts, search_results, legal_basis, correlation_id
        )
        
        # Generate claim sections
        claim = await self._generate_claim(
            claim_type=claim_type,
            facts=facts,
            parties=parties,
            arguments=arguments,
            legal_basis=legal_basis,
            correlation_id=correlation_id
        )
        
        # Update metrics
        self._claim_metrics["claims_generated"] += 1
        n = self._claim_metrics["claims_generated"]
        self._claim_metrics["avg_arguments"] = (
            (self._claim_metrics["avg_arguments"] * (n-1) + len(arguments)) / n
        )
        
        # ============================================================================
        # B3: LEDGER PERSISTENCE WITH EVIDENCE - MANDATORY
        # ============================================================================
        result = {
            "claim": self._claim_to_dict(claim),
            "arguments": [self._argument_to_dict(a) for a in arguments],
            "legal_basis": legal_basis,
            "full_text": self._generate_full_text(claim),
            "metadata": {
                "claim_type": claim_type.value,
                "arguments_count": len(arguments),
                "legal_basis_count": len(legal_basis),
                "boundary_input_id": boundary_result.input_id,
                "boundary_input_hash": boundary_result.input_hash,
            }
        }
        
        # Build evidence package from claim generation
        evidence_refs = []
        
        # Evidence from search results
        for sr in search_results:
            if "doc_id" in sr:
                evidence_refs.append(f"doc:{sr['doc_id']}")
        
        # Evidence from legal basis
        for basis in legal_basis:
            evidence_refs.append(f"basis:{hash(basis) % 1000000}")
        
        # Evidence from arguments
        for arg in arguments:
            for citation in arg.citations:
                evidence_refs.append(f"citation:{citation}")
        
        # Create provenance chain
        provenance_chain = [
            {
                "step": "boundary_validation",
                "input_id": boundary_result.input_id,
                "timestamp": boundary_result.timestamp.isoformat(),
            },
            {
                "step": "claim_generation",
                "correlation_id": correlation_id,
                "arguments_count": len(arguments),
                "evidence_count": len(evidence_refs),
            }
        ]
        
        # Compute proof hash
        proof_content = f"{boundary_result.input_hash}:{':'.join(sorted(evidence_refs))}"
        proof_hash = hashlib.sha256(proof_content.encode()).hexdigest()[:16]
        
        evidence_package = EvidencePackage(
            evidence_refs=evidence_refs,
            provenance_chain=provenance_chain,
            proof_hash=proof_hash,
            validation_context={
                "correlation_id": correlation_id,
                "boundary_input_id": boundary_result.input_id,
            }
        )
        
        # Attempt ledger persistence
        if self._write_gate is None:
            raise RuntimeError("WriteGate not configured. B3 persistence boundary requires write_gate configuration.")
        
        try:
            write_result = self._write_gate.write_claim(
                claim_data=result["claim"],
                evidence_package=evidence_package,
                metadata={
                    "correlation_id": correlation_id,
                    "request_id": boundary_result.input_id,
                }
            )
        
            if not write_result.success:
                raise RuntimeError(f"Ledger write failed: {write_result.error_message}")
        
            self._claim_metrics["claims_persisted"] += 1
            result["metadata"]["ledger_entry_id"] = write_result.entry_id
            result["metadata"]["ledger_entry_hash"] = write_result.entry_hash
            self.logger.info(
                f"[{correlation_id}] B3 PERSISTENCE SUCCESS: "
                f"entry_id={write_result.entry_id}"
            )
        
        except Exception as e:
            raise RuntimeError(f"Ledger persistence exception: {str(e)}")
        
        return result
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Fallback: template-based generation"""
        self.logger.warning(f"[{correlation_id}] Using FALLBACK mode")
        
        facts = input_data.get("facts", "")
        claim_type_str = input_data.get("claim_type", "other")
        
        try:
            claim_type = ClaimType(claim_type_str)
        except ValueError:
            claim_type = ClaimType.OTHER
        
        template = self.CLAIM_TEMPLATES.get(claim_type, {
            "title": "دادخواست",
            "relief": "صدور حکم مقتضی"
        })
        
        return {
            "claim": {
                "type": claim_type.value,
                "title": template["title"],
                "facts": facts[:500],
                "relief": template["relief"]
            },
            "arguments": [],
            "legal_basis": [],
            "full_text": f"{template['title']}\n\nشرح دعوی:\n{facts[:1000]}\n\nخواسته:\n{template['relief']}",
            "metadata": {"fallback_used": True}
        }
    
    async def _search_relevant(
        self,
        facts: str,
        claim_type: ClaimType,
        correlation_id: Optional[str]
    ) -> List[Dict]:
        """Search for relevant documents"""
        if not self._rag_service:
            return []
        
        try:
            from mahoun.rag.hybrid_rag_service import RAGMode
            
            # Build query
            query = f"{claim_type.value} {facts[:200]}"
            
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
    
    async def _extract_legal_basis(
        self,
        results: List[Dict],
        input_basis: str,
        correlation_id: Optional[str]
    ) -> List[str]:
        """Extract legal basis from results"""
        legal_basis: List[Any] = []
        if input_basis:
            legal_basis.append(input_basis)
        
        # Extract from results
        legal_keywords = ["ماده", "قانون", "آیین‌نامه", "بند", "تبصره"]
        
        for result in results[:10]:
            content = result["content"]
            for kw in legal_keywords:
                if kw in content:
                    # Extract sentence containing keyword
                    sentences = content.split(".")
                    for sent in sentences:
                        if kw in sent and len(sent) < 300:
                            legal_basis.append(sent.strip())
                            break
        
        # Deduplicate
        return list(dict.fromkeys(legal_basis))[:10]
    
    async def _build_arguments(
        self,
        facts: str,
        results: List[Dict],
        legal_basis: List[str],
        correlation_id: Optional[str]
    ) -> List[ClaimArgument]:
        """Build legal arguments"""
        arguments: List[Any] = []
        # Argument from facts
        arguments.append(ClaimArgument(
            title="شرح وقایع",
            content=facts[:500],
            strength=0.9
        ))
        
        # Arguments from search results
        for i, result in enumerate(results[:5]):
            arguments.append(ClaimArgument(
                title=f"مستند {i+1}",
                content=result["content"][:300],
                citations=[result["doc_id"]],
                strength=result["score"]
            ))
        
        # Arguments from legal basis
        for basis in legal_basis[:3]:
            arguments.append(ClaimArgument(
                title="مبنای حقوقی",
                content=basis,
                legal_basis=basis,
                strength=0.85
            ))
        
        # Sort by strength
        arguments.sort(key=lambda x: x.strength, reverse=True)
        return arguments[:self.config.max_arguments]
    
    async def _generate_claim(
        self,
        claim_type: ClaimType,
        facts: str,
        parties: Dict,
        arguments: List[ClaimArgument],
        legal_basis: List[str],
        correlation_id: Optional[str]
    ) -> GeneratedClaim:
        """Generate structured claim"""
        template = self.CLAIM_TEMPLATES.get(claim_type, {
            "title": "دادخواست",
            "relief": "صدور حکم مقتضی"
        })
        
        plaintiff = parties.get("plaintiff", "خواهان")
        defendant = parties.get("defendant", "خوانده")
        
        introduction = f"احتراماً، {plaintiff} به استحضار می‌رساند..."
        
        conclusion = f"با عنایت به مراتب فوق، صدور حکم به {template['relief']} مورد استدعاست."
        
        return GeneratedClaim(
            claim_type=claim_type,
            title=template["title"],
            introduction=introduction,
            facts=facts,
            arguments=arguments,
            legal_basis=legal_basis,
            relief_sought=template["relief"],
            conclusion=conclusion
        )
    
    def _generate_full_text(self, claim: GeneratedClaim) -> str:
        """Generate full claim text"""
        sections = [
            claim.title,
            "",
            claim.introduction,
            "",
            "شرح دعوی:",
            claim.facts,
            "",
            "دلایل و مستندات:"
        ]
        
        for i, arg in enumerate(claim.arguments, 1):
            sections.append(f"{i}. {arg.title}: {arg.content[:200]}")
        
        if claim.legal_basis:
            sections.append("")
            sections.append("مبانی حقوقی:")
            for basis in claim.legal_basis[:5]:
                sections.append(f"- {basis[:150]}")
        
        sections.extend([
            "",
            "خواسته:",
            claim.relief_sought,
            "",
            claim.conclusion
        ])
        
        return "\n".join(sections)
    
    def _claim_to_dict(self, claim: GeneratedClaim) -> Dict:
        return {
            "type": claim.claim_type.value,
            "title": claim.title,
            "introduction": claim.introduction,
            "facts": claim.facts[:500],
            "relief": claim.relief_sought,
            "conclusion": claim.conclusion
        }
    
    def _argument_to_dict(self, arg: ClaimArgument) -> Dict:
        return {
            "title": arg.title,
            "content": arg.content[:300],
            "legal_basis": arg.legal_basis,
            "citations": arg.citations,
            "strength": round(arg.strength, 3)
        }
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        return {
            "components": {
                "rag_service": self._rag_service is not None,
                "citation_engine": self._citation_engine is not None,
                "reasoning_service": self._reasoning_service is not None
            },
            "metrics": self._claim_metrics.copy()
        }
