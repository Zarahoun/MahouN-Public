#!/usr/bin/env python3
"""
AI Models Module - G-0 FREEZE CANDIDATE

This module consolidates AI-related data models:
- AIResponse: Standard AI response format
- PromptTemplate: Evidence-linked prompt templates

CRITICAL: These data models MUST be frozen before first GGUF integration
to ensure consistent patterns across all AI operations.

Version: 1.0.0-rc1 (Release Candidate - Pre-G-0)
Freeze Status: PENDING (Must freeze before Task A.2 implementation)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set
from enum import Enum
import time
import hashlib
import json
import re


# ═══════════════════════════════════════════════════════════════════════════════
# AI RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class ResponseStatus(Enum):
    """AI Response generation status"""
    SUCCESS = "success"
    PARTIAL = "partial"  # Partial generation due to limits
    ERROR = "error"
    GOVERNANCE_BLOCKED = "governance_blocked"
    RESOURCE_EXHAUSTED = "resource_exhausted"


@dataclass(frozen=True)
class TokenUsage:
    """
    Token usage information for AI generation
    
    G-0 FREEZE CANDIDATE: This structure must remain stable
    """
    prompt_tokens: int
    completion_tokens: int 
    total_tokens: int
    
    def __post_init__(self):
        """Validation for token usage"""
        if self.prompt_tokens < 0:
            raise ValueError("prompt_tokens must be non-negative")
        if self.completion_tokens < 0:
            raise ValueError("completion_tokens must be non-negative")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")


@dataclass(frozen=True)
class GenerationMetadata:
    """
    Metadata about AI generation process
    
    G-0 FREEZE CANDIDATE: This structure must remain stable
    """
    model_id: str
    model_format: str  # "GGUF", "SafeTensors", etc.
    quantization: Optional[str]  # Q4_K_M, Q8_0, etc.
    parameters_count: Optional[int]  # 1B, 3B, 7B, etc.
    generation_params: Dict[str, Any]  # temperature, top_k, etc.
    inference_time_ms: float
    tokens_per_second: Optional[float]
    memory_usage_mb: float
    deployment_profile: str
    
    def __post_init__(self):
        """Validation for generation metadata"""
        if not self.model_id:
            raise ValueError("model_id cannot be empty")
        if self.inference_time_ms <= 0:
            raise ValueError("inference_time_ms must be positive")
        if self.memory_usage_mb < 0:
            raise ValueError("memory_usage_mb must be non-negative")
        if self.tokens_per_second is not None and self.tokens_per_second < 0:
            raise ValueError("tokens_per_second must be non-negative")


@dataclass(frozen=True)
class AIResponse:
    """
    Standard AI Runtime Response Format - G-0 FREEZE CANDIDATE
    
    This is the canonical response format that all AI runtime implementations
    must return. This ensures consistent audit trails, governance validation,
    and fortress validator compatibility across all model types.
    
    Design Principles:
    1. Immutable: All fields are frozen to prevent modification
    2. Auditable: Contains all information needed for audit trails
    3. Governable: Includes governance validation status
    4. Traceable: Links to evidence and correlation IDs
    5. Verifiable: Cryptographic hashes for integrity
    
    Contract Guarantees:
    - fortress_validated MUST be True before response is returned to user
    - audit_hash MUST be set when fortress_validated = True
    - All timestamps are Unix timestamps (seconds since epoch)
    - All hashes use SHA-256 format (64 hex characters)
    """
    
    # Core Response Data
    request_id: str  # Unique request identifier
    correlation_id: Optional[str]  # Cross-service tracing ID
    response_text: str  # Generated text content
    status: ResponseStatus  # Generation status
    
    # Quality and Confidence Metrics
    confidence_score: float  # Model confidence (0.0 to 1.0)
    quality_score: Optional[float]  # Optional quality assessment
    
    # Token and Performance Information  
    token_usage: TokenUsage
    generation_metadata: GenerationMetadata
    
    # Governance and Audit Fields
    fortress_validated: bool = False  # FortressValidator approval
    governance_context: Optional[Dict[str, Any]] = None  # Governance decision context
    evidence_links: List[str] = field(default_factory=list)  # Links to evidence sources
    
    # Audit and Integrity Fields
    audit_hash: Optional[str] = None  # SHA-256 hash for integrity
    created_timestamp: float = field(default_factory=time.time)
    validation_timestamp: Optional[float] = None  # When fortress validation completed
    
    # Optional Fields for Advanced Use Cases
    reasoning_chain: Optional[List[Dict[str, Any]]] = None  # Step-by-step reasoning
    citations: Optional[List[Dict[str, Any]]] = None  # Source citations
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata
    
    def __post_init__(self):
        """
        Comprehensive validation for AI response integrity
        
        This validation ensures all responses meet governance requirements
        and maintain audit trail integrity.
        """
        # Core field validation
        if not self.request_id:
            raise ValueError("request_id cannot be empty")
        if not isinstance(self.response_text, str):
            raise ValueError("response_text must be a string")
        
        # Confidence score validation
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        
        # Quality score validation (if provided)
        if self.quality_score is not None:
            if not (0.0 <= self.quality_score <= 1.0):
                raise ValueError("quality_score must be between 0.0 and 1.0")
        
        # Fortress validation requirements
        if self.fortress_validated and not self.audit_hash:
            raise ValueError("audit_hash required when fortress_validated=True")
        
        # Audit hash format validation
        if self.audit_hash is not None:
            if len(self.audit_hash) != 64:
                raise ValueError("audit_hash must be valid SHA-256 hash (64 hex chars)")
            # Verify it's valid hex
            try:
                int(self.audit_hash, 16)
            except ValueError:
                raise ValueError("audit_hash must contain only hexadecimal characters")
        
        # Timestamp validation
        if self.created_timestamp <= 0:
            raise ValueError("created_timestamp must be positive")
        if self.validation_timestamp is not None and self.validation_timestamp <= 0:
            raise ValueError("validation_timestamp must be positive")
        if (self.validation_timestamp is not None and 
            self.validation_timestamp < self.created_timestamp):
            raise ValueError("validation_timestamp cannot be before created_timestamp")
    
    def calculate_content_hash(self) -> str:
        """
        Calculate SHA-256 hash of response content for integrity verification
        
        This hash includes all core content but excludes audit fields to
        avoid circular dependencies. Used for integrity verification.
        
        Returns:
            SHA-256 hash of response content as hex string
        """
        # Create deterministic content representation
        content_dict = {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "response_text": self.response_text,
            "status": self.status.value,
            "confidence_score": self.confidence_score,
            "quality_score": self.quality_score,
            "token_usage": {
                "prompt_tokens": self.token_usage.prompt_tokens,
                "completion_tokens": self.token_usage.completion_tokens,
                "total_tokens": self.token_usage.total_tokens
            },
            "generation_metadata": {
                "model_id": self.generation_metadata.model_id,
                "model_format": self.generation_metadata.model_format,
                "quantization": self.generation_metadata.quantization,
                "parameters_count": self.generation_metadata.parameters_count,
                "inference_time_ms": self.generation_metadata.inference_time_ms,
                "deployment_profile": self.generation_metadata.deployment_profile
            },
            "evidence_links": sorted(self.evidence_links),  # Ensure deterministic order
            "created_timestamp": self.created_timestamp
        }
        
        # Convert to deterministic JSON and hash
        content_json = json.dumps(content_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content_json.encode('utf-8')).hexdigest()
    
    def validate_integrity(self) -> bool:
        """
        Validate response integrity against stored audit hash
        
        Returns:
            True if integrity check passes, False otherwise
        """
        if not self.audit_hash:
            return False
        
        calculated_hash = self.calculate_content_hash()
        return calculated_hash == self.audit_hash
    
    def to_audit_dict(self) -> Dict[str, Any]:
        """
        Convert response to dictionary format for audit logging
        
        Returns:
            Dictionary containing audit-relevant fields
        """
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "status": self.status.value,
            "confidence_score": self.confidence_score,
            "fortress_validated": self.fortress_validated,
            "model_id": self.generation_metadata.model_id,
            "deployment_profile": self.generation_metadata.deployment_profile,
            "token_count": self.token_usage.total_tokens,
            "inference_time_ms": self.generation_metadata.inference_time_ms,
            "created_timestamp": self.created_timestamp,
            "validation_timestamp": self.validation_timestamp,
            "audit_hash": self.audit_hash,
            "evidence_count": len(self.evidence_links),
            "has_reasoning_chain": self.reasoning_chain is not None,
            "has_citations": self.citations is not None
        }
    
    def is_production_ready(self) -> bool:
        """
        Check if response meets all production requirements
        
        Returns:
            True if response is ready for production use
        """
        return (
            self.fortress_validated and
            self.audit_hash is not None and
            self.validation_timestamp is not None and
            self.status == ResponseStatus.SUCCESS and
            self.confidence_score >= 0.7  # Minimum confidence threshold
        )
    
    def get_semantic_content_hash(self) -> str:
        """
        Calculate hash of semantic content only (text + reasoning)
        
        This hash is used for semantic equivalence testing across
        deployment profiles to ensure consistent reasoning quality.
        
        Returns:
            SHA-256 hash of semantic content
        """
        semantic_content = {
            "response_text": self.response_text,
            "confidence_score": round(self.confidence_score, 3),  # Round for consistency
            "reasoning_chain": self.reasoning_chain,
            "evidence_links": sorted(self.evidence_links)
        }
        
        content_json = json.dumps(semantic_content, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content_json.encode('utf-8')).hexdigest()


# Factory functions for creating responses

def create_success_response(
    request_id: str,
    response_text: str,
    token_usage: TokenUsage,
    generation_metadata: GenerationMetadata,
    confidence_score: float,
    quality_score: Optional[float] = None,
    correlation_id: Optional[str] = None,
    evidence_links: Optional[List[str]] = None
) -> AIResponse:
    """
    Create a successful AI response with audit hash
    
    This factory function ensures all successful responses have
    proper audit hashes calculated automatically.
    """
    response = AIResponse(
        request_id=request_id,
        correlation_id=correlation_id,
        response_text=response_text,
        status=ResponseStatus.SUCCESS,
        confidence_score=confidence_score,
        quality_score=quality_score,
        token_usage=token_usage,
        generation_metadata=generation_metadata,
        evidence_links=evidence_links or []
    )
    
    # Calculate and set audit hash
    audit_hash = response.calculate_content_hash()
    
    # Create new response with audit hash (dataclass is frozen)
    return AIResponse(
        request_id=response.request_id,
        correlation_id=response.correlation_id,
        response_text=response.response_text,
        status=response.status,
        confidence_score=response.confidence_score,
        quality_score=response.quality_score,
        token_usage=response.token_usage,
        generation_metadata=response.generation_metadata,
        evidence_links=response.evidence_links,
        audit_hash=audit_hash,
        created_timestamp=response.created_timestamp
    )


def create_error_response(
    request_id: str,
    error_message: str,
    generation_metadata: GenerationMetadata,
    correlation_id: Optional[str] = None,
    status: ResponseStatus = ResponseStatus.ERROR
) -> AIResponse:
    """
    Create an error response with minimal token usage
    """
    token_usage = TokenUsage(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0
    )
    
    response = AIResponse(
        request_id=request_id,
        correlation_id=correlation_id,
        response_text=error_message,
        status=status,
        confidence_score=0.0,
        token_usage=token_usage,
        generation_metadata=generation_metadata
    )
    
    # Calculate audit hash for error responses too
    audit_hash = response.calculate_content_hash()
    
    return AIResponse(
        request_id=response.request_id,
        correlation_id=response.correlation_id,
        response_text=response.response_text,
        status=response.status,
        confidence_score=response.confidence_score,
        token_usage=response.token_usage,
        generation_metadata=response.generation_metadata,
        audit_hash=audit_hash,
        created_timestamp=response.created_timestamp
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class EvidenceSlotType(Enum):
    """Types of evidence slots in prompt templates"""
    LEGAL_PRECEDENT = "legal_precedent"
    CASE_LAW = "case_law"
    STATUTORY_TEXT = "statutory_text"
    EXPERT_OPINION = "expert_opinion"
    FACTUAL_FINDING = "factual_finding"
    GRAPH_CONTEXT = "graph_context"
    RETRIEVAL_CONTEXT = "retrieval_context"
    CUSTOM = "custom"


@dataclass(frozen=True)
class EvidenceSlot:
    """
    Evidence slot definition for prompt templates
    
    G-0 FREEZE CANDIDATE: This structure must remain stable
    """
    slot_name: str
    slot_type: EvidenceSlotType
    required: bool = True
    max_length: Optional[int] = None
    validation_regex: Optional[str] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        """Validation for evidence slots"""
        if not self.slot_name:
            raise ValueError("slot_name cannot be empty")
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.slot_name):
            raise ValueError("slot_name must be valid identifier (alphanumeric + underscore)")
        if self.max_length is not None and self.max_length <= 0:
            raise ValueError("max_length must be positive")
    
    def validate_content(self, content: str) -> bool:
        """
        Validate evidence content against slot constraints
        
        Args:
            content: Evidence content to validate
            
        Returns:
            True if content is valid for this slot
        """
        if not content and self.required:
            return False
        
        if self.max_length and len(content) > self.max_length:
            return False
        
        if self.validation_regex:
            if not re.match(self.validation_regex, content):
                return False
        
        return True


@dataclass(frozen=True)
class ContextRequirement:
    """
    Context requirements for prompt generation
    
    G-0 FREEZE CANDIDATE: This structure must remain stable
    """
    requirement_name: str
    requirement_type: str  # "graph_query", "retrieval_query", "ledger_lookup", etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    optional: bool = False
    cache_key: Optional[str] = None
    
    def __post_init__(self):
        """Validation for context requirements"""
        if not self.requirement_name:
            raise ValueError("requirement_name cannot be empty")
        if not self.requirement_type:
            raise ValueError("requirement_type cannot be empty")
    
    def to_cache_key(self) -> str:
        """
        Generate cache key for this context requirement
        
        Returns:
            Cache key string for context lookup
        """
        if self.cache_key:
            return self.cache_key
        
        cache_data = {
            "name": self.requirement_name,
            "type": self.requirement_type,
            "params": self.parameters
        }
        
        cache_json = json.dumps(cache_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(cache_json.encode('utf-8')).hexdigest()[:16]


@dataclass(frozen=True)
class PromptTemplate:
    """
    Evidence-Linked Prompt Template - G-0 FREEZE CANDIDATE
    
    This is the canonical prompt template format that ensures all AI
    generations are grounded in verifiable evidence from the knowledge
    graph, retrieval system, and evidence ledger.
    
    Design Principles:
    1. Evidence-First: All prompts must be linked to evidence sources
    2. Immutable: Templates are frozen to prevent modification
    3. Traceable: All evidence slots are named and typed
    4. Validatable: Content must pass validation before use
    5. Auditable: Template usage is tracked in audit trails
    
    Contract Guarantees:
    - All evidence_slots must be filled before prompt generation
    - Context requirements must be satisfied before generation
    - Generated prompts are deterministic given same evidence
    - Template structure supports proof tree generation
    """
    
    # Core Template Definition
    template_id: str  # Unique template identifier
    template_text: str  # Template with {slot_name} placeholders
    template_version: str  # Semantic version (e.g., "1.0.0")
    
    # Evidence Integration
    evidence_slots: List[EvidenceSlot]  # Required evidence slots
    context_requirements: List[ContextRequirement] = field(default_factory=list)
    
    # Metadata
    description: Optional[str] = None
    category: Optional[str] = None  # "legal_reasoning", "contract_analysis", etc.
    created_timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """
        Comprehensive validation for prompt templates
        """
        # Core field validation
        if not self.template_id:
            raise ValueError("template_id cannot be empty")
        if not self.template_text:
            raise ValueError("template_text cannot be empty")
        if not self.template_version:
            raise ValueError("template_version cannot be empty")
        
        # Version format validation
        if not re.match(r'^\d+\.\d+\.\d+', self.template_version):
            raise ValueError("template_version must follow semantic versioning (X.Y.Z)")
        
        # Evidence slots validation
        if not self.evidence_slots:
            raise ValueError("At least one evidence_slot required")
        
        # Check for duplicate slot names
        slot_names = [slot.slot_name for slot in self.evidence_slots]
        if len(slot_names) != len(set(slot_names)):
            raise ValueError("Duplicate evidence slot names found")
        
        # Validate that all template placeholders have corresponding slots
        template_placeholders = self._extract_placeholders(self.template_text)
        slot_name_set = set(slot_names)
        
        for placeholder in template_placeholders:
            if placeholder not in slot_name_set:
                raise ValueError(f"Template placeholder '{placeholder}' has no corresponding evidence slot")
        
        # Validate that all required slots are used in template
        for slot in self.evidence_slots:
            if slot.required and slot.slot_name not in template_placeholders:
                raise ValueError(f"Required evidence slot '{slot.slot_name}' not used in template")
    
    def _extract_placeholders(self, template: str) -> Set[str]:
        """
        Extract placeholder names from template text
        
        Args:
            template: Template text with {placeholder} format
            
        Returns:
            Set of placeholder names
        """
        # Match {placeholder_name} patterns
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        matches = re.findall(pattern, template)
        return set(matches)
    
    def validate_evidence(self, evidence: Dict[str, str]) -> bool:
        """
        Validate that provided evidence satisfies all slot requirements
        
        Args:
            evidence: Dictionary mapping slot names to evidence content
            
        Returns:
            True if all requirements are satisfied
        """
        # Check all required slots are present
        for slot in self.evidence_slots:
            if slot.required:
                if slot.slot_name not in evidence:
                    return False
                
                content = evidence[slot.slot_name]
                if not slot.validate_content(content):
                    return False
        
        return True
    
    def generate_prompt(
        self,
        evidence: Dict[str, str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate final prompt by filling template with evidence
        
        Args:
            evidence: Dictionary mapping slot names to evidence content
            context: Optional additional context for generation
            
        Returns:
            Generated prompt with all evidence slots filled
            
        Raises:
            ValueError: If evidence validation fails
        """
        # Validate evidence before generation
        if not self.validate_evidence(evidence):
            raise ValueError("Evidence validation failed")
        
        # Fill template with evidence
        prompt = self.template_text
        for slot_name, content in evidence.items():
            placeholder = f"{{{slot_name}}}"
            prompt = prompt.replace(placeholder, content)
        
        # Verify all placeholders were filled
        remaining_placeholders = self._extract_placeholders(prompt)
        if remaining_placeholders:
            raise ValueError(f"Unfilled placeholders: {remaining_placeholders}")
        
        return prompt
    
    def get_required_evidence_slots(self) -> List[EvidenceSlot]:
        """
        Get list of required evidence slots
        
        Returns:
            List of required evidence slots
        """
        return [slot for slot in self.evidence_slots if slot.required]
    
    def get_optional_evidence_slots(self) -> List[EvidenceSlot]:
        """
        Get list of optional evidence slots
        
        Returns:
            List of optional evidence slots
        """
        return [slot for slot in self.evidence_slots if not slot.required]
    
    def to_audit_dict(self) -> Dict[str, Any]:
        """
        Convert template to dictionary for audit logging
        
        Returns:
            Dictionary containing audit-relevant fields
        """
        return {
            "template_id": self.template_id,
            "template_version": self.template_version,
            "category": self.category,
            "evidence_slot_count": len(self.evidence_slots),
            "required_slot_count": len(self.get_required_evidence_slots()),
            "context_requirement_count": len(self.context_requirements),
            "created_timestamp": self.created_timestamp
        }


# Standard Templates for Common Use Cases

LEGAL_REASONING_TEMPLATE = PromptTemplate(
    template_id="legal_reasoning_v1",
    template_text="""Analyze the following legal question with evidence-based reasoning:

Question: {query}

Relevant Legal Precedents:
{legal_precedents}

Applicable Statutory Text:
{statutory_text}

Factual Context:
{factual_context}

Provide a reasoned analysis that:
1. Identifies applicable legal principles
2. Analyzes relevant precedents
3. Applies law to facts
4. Reaches a defensible conclusion

Analysis:""",
    template_version="1.0.0",
    evidence_slots=[
        EvidenceSlot(
            slot_name="query",
            slot_type=EvidenceSlotType.CUSTOM,
            required=True,
            max_length=1000,
            description="Legal question to analyze"
        ),
        EvidenceSlot(
            slot_name="legal_precedents",
            slot_type=EvidenceSlotType.CASE_LAW,
            required=True,
            max_length=5000,
            description="Relevant case law and precedents"
        ),
        EvidenceSlot(
            slot_name="statutory_text",
            slot_type=EvidenceSlotType.STATUTORY_TEXT,
            required=True,
            max_length=3000,
            description="Applicable statutory provisions"
        ),
        EvidenceSlot(
            slot_name="factual_context",
            slot_type=EvidenceSlotType.FACTUAL_FINDING,
            required=True,
            max_length=2000,
            description="Relevant factual context"
        )
    ],
    context_requirements=[
        ContextRequirement(
            requirement_name="graph_context",
            requirement_type="graph_query",
            parameters={"max_depth": 3, "min_confidence": 0.7}
        ),
        ContextRequirement(
            requirement_name="retrieval_context",
            requirement_type="retrieval_query",
            parameters={"top_k": 5, "similarity_threshold": 0.75}
        )
    ],
    description="Standard template for evidence-based legal reasoning",
    category="legal_reasoning"
)


CONTRACT_ANALYSIS_TEMPLATE = PromptTemplate(
    template_id="contract_analysis_v1",
    template_text="""Analyze the following contract provision with legal context:

Contract Clause:
{contract_clause}

Relevant Case Law:
{case_law}

Legal Interpretation Guidelines:
{interpretation_guidelines}

Provide analysis addressing:
1. Plain meaning of the clause
2. Applicable interpretation principles
3. Relevant precedents
4. Potential ambiguities or risks

Analysis:""",
    template_version="1.0.0",
    evidence_slots=[
        EvidenceSlot(
            slot_name="contract_clause",
            slot_type=EvidenceSlotType.CUSTOM,
            required=True,
            max_length=2000,
            description="Contract provision to analyze"
        ),
        EvidenceSlot(
            slot_name="case_law",
            slot_type=EvidenceSlotType.CASE_LAW,
            required=True,
            max_length=4000,
            description="Relevant case law on similar clauses"
        ),
        EvidenceSlot(
            slot_name="interpretation_guidelines",
            slot_type=EvidenceSlotType.EXPERT_OPINION,
            required=False,
            max_length=2000,
            description="Legal interpretation guidelines"
        )
    ],
    description="Template for contract provision analysis",
    category="contract_analysis"
)


# Factory functions

def create_custom_template(
    template_id: str,
    template_text: str,
    evidence_slots: List[EvidenceSlot],
    version: str = "1.0.0",
    **kwargs
) -> PromptTemplate:
    """
    Create a custom prompt template with validation
    
    Args:
        template_id: Unique template identifier
        template_text: Template with {slot_name} placeholders
        evidence_slots: List of evidence slot definitions
        version: Template version (semantic versioning)
        **kwargs: Additional template parameters
        
    Returns:
        Validated PromptTemplate instance
    """
    return PromptTemplate(
        template_id=template_id,
        template_text=template_text,
        template_version=version,
        evidence_slots=evidence_slots,
        **kwargs
    )
