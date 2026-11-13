"""
Agent Evidence Event Protocol - Standardized Agent Output Format
==============================================================

Classification: GOVERNANCE INTEGRATION / AGENT PROTOCOL
Purpose: Defines standardized evidence collection format for all agents

This protocol establishes a unified interface for collecting evidence from
agent executions, ensuring all agent outputs can be traced back to governance
contexts and included in audit trails.

Key Features:
- Standardized evidence event format across all agent types
- Governance correlation tracking for complete audit trails
- Support for both existing agents and new governance-aware agents
- Evidence chain construction for complex workflows
- Provenance tracking compatible with RAGEvidenceNode

Per AGENTS.md Part 1 guidance: This protocol enables standardized agent outputs
without requiring modifications to existing agent implementations.

Author: MAHOUN Architecture Integration Mission
Version: 1.0.0
"""

import hashlib
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from mahoun.agents.base_agent import AgentResult
from mahoun.reasoning.rag_evidence import RAGEvidenceNode, SourceAuthority


class AgentEvidenceType(str, Enum):
    """Types of evidence that agents can produce"""
    
    ANALYSIS_RESULT = "analysis_result"
    DOCUMENT_PARSE = "document_parse" 
    ENTITY_EXTRACTION = "entity_extraction"
    RELATIONSHIP_DISCOVERY = "relationship_discovery"
    CONTRADICTION_DETECTION = "contradiction_detection"
    SIMILARITY_ASSESSMENT = "similarity_assessment"
    QUALITY_VALIDATION = "quality_validation"
    CLASSIFICATION_RESULT = "classification_result"
    WORKFLOW_DECISION = "workflow_decision"
    RISK_ASSESSMENT = "risk_assessment"
    NARRATIVE_GENERATION = "narrative_generation"
    VERIFICATION_CHECK = "verification_check"
    EXTERNAL_API_CALL = "external_api_call"
    USER_INTERACTION = "user_interaction"
    SYSTEM_OPERATION = "system_operation"


class AgentConfidenceLevel(str, Enum):
    """Agent confidence levels for evidence quality assessment"""
    
    HIGH = "high"           # >= 0.8
    MEDIUM = "medium"       # >= 0.6
    LOW = "low"            # >= 0.4
    UNCERTAIN = "uncertain" # < 0.4


@dataclass(frozen=True)
class AgentEvidenceEvent:
    """
    Standardized evidence event from agent execution.
    
    This structure captures all necessary information to create a complete
    audit trail from agent operations, including governance correlation
    and evidence provenance.
    
    Invariants:
    - agent_name must be non-empty
    - correlation_id must be non-empty (governance requirement)
    - confidence must be in [0.0, 1.0]
    - evidence_hash must be 64-char lowercase hex SHA-256
    - timestamp must be ISO format
    """
    
    # Core identification
    agent_name: str
    agent_version: Optional[str]
    correlation_id: str
    
    # Evidence content
    evidence_type: AgentEvidenceType
    evidence_data: Dict[str, Any]
    evidence_hash: str  # SHA-256 of evidence_data
    
    # Quality and confidence
    confidence_score: float
    confidence_level: AgentConfidenceLevel
    
    # Execution metadata
    execution_id: str  # Unique execution identifier
    timestamp: str     # ISO format timestamp
    processing_time_ms: float
    
    # Governance context
    governance_context_id: Optional[str] = None
    governance_execution_mode: str = "UNKNOWN"
    actor_id: Optional[str] = None
    
    # Evidence chain (for workflow agents)
    parent_evidence_ids: List[str] = field(default_factory=list)
    child_evidence_ids: List[str] = field(default_factory=list)
    
    # Agent execution details
    agent_result: Optional[AgentResult] = None
    fallback_used: bool = False
    retries_attempted: int = 0
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate invariants"""
        if not self.agent_name or not self.agent_name.strip():
            raise ValueError("agent_name cannot be empty")
        
        if not self.correlation_id or not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty (governance requirement)")
        
        if not 0.0 <= self.confidence_score <= 1.0:
            raise ValueError(f"confidence_score must be in [0.0, 1.0], got {self.confidence_score}")
        
        if not isinstance(self.evidence_type, AgentEvidenceType):
            raise ValueError(f"evidence_type must be AgentEvidenceType, got {self.evidence_type!r}")
        
        if not isinstance(self.confidence_level, AgentConfidenceLevel):
            raise ValueError(f"confidence_level must be AgentConfidenceLevel, got {self.confidence_level!r}")
        
        if (
            len(self.evidence_hash) != 64
            or any(c not in "0123456789abcdef" for c in self.evidence_hash)
        ):
            raise ValueError("evidence_hash must be a 64-char lowercase hex SHA-256 digest")
        
        # Validate that confidence_score matches confidence_level
        expected_level = self._calculate_confidence_level(self.confidence_score)
        if expected_level != self.confidence_level:
            raise ValueError(
                f"confidence_level {self.confidence_level} does not match "
                f"confidence_score {self.confidence_score} (expected {expected_level})"
            )
    
    @staticmethod
    def _calculate_confidence_level(score: float) -> AgentConfidenceLevel:
        """Calculate confidence level from numerical score"""
        if score >= 0.8:
            return AgentConfidenceLevel.HIGH
        elif score >= 0.6:
            return AgentConfidenceLevel.MEDIUM
        elif score >= 0.4:
            return AgentConfidenceLevel.LOW
        else:
            return AgentConfidenceLevel.UNCERTAIN
    
    @property
    def evidence_id(self) -> str:
        """Stable evidence identifier for deduplication and referencing"""
        return hashlib.sha256(
            f"{self.agent_name}|{self.execution_id}|{self.evidence_hash}".encode("utf-8")
        ).hexdigest()[:16]
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if evidence meets high confidence threshold"""
        return self.confidence_level in [AgentConfidenceLevel.HIGH, AgentConfidenceLevel.MEDIUM]
    
    @property
    def is_governance_compliant(self) -> bool:
        """Check if evidence has required governance metadata"""
        return (
            self.governance_context_id is not None
            and self.governance_execution_mode != "UNKNOWN"
            and self.correlation_id
        )
    
    def to_rag_evidence_node(
        self,
        fact_index: int,
        retrieval_rank: int = 0,
        authority: SourceAuthority = SourceAuthority.TRUSTED_INTERNAL,
    ) -> RAGEvidenceNode:
        """
        Convert agent evidence to RAGEvidenceNode for integration with verdict engine.
        
        Args:
            fact_index: Index in the fact_texts list
            retrieval_rank: Rank in retrieval results (default: 0 for agent-generated)
            authority: Source authority level (default: TRUSTED_INTERNAL for agents)
            
        Returns:
            RAGEvidenceNode compatible with existing evidence chain
        """
        from mahoun.reasoning.rag_evidence import RAGSource
        
        return RAGEvidenceNode(
            fact_index=fact_index,
            doc_id=f"agent:{self.agent_name}:{self.execution_id}",
            source=RAGSource.USER_PROVIDED,  # Agent-generated content
            authority=authority,
            score=self.confidence_score,
            retrieval_rank=retrieval_rank,
            correlation_id=self.correlation_id,
            content_hash=self.evidence_hash,
            is_sensitive=self.metadata.get("is_sensitive", False),
            metadata={
                **self.metadata,
                "agent_name": self.agent_name,
                "agent_version": self.agent_version,
                "evidence_type": self.evidence_type.value,
                "execution_id": self.execution_id,
                "timestamp": self.timestamp,
                "processing_time_ms": self.processing_time_ms,
                "governance_context_id": self.governance_context_id,
                "governance_execution_mode": self.governance_execution_mode,
                "actor_id": self.actor_id,
                "fallback_used": self.fallback_used,
                "retries_attempted": self.retries_attempted,
            },
        )
    
    def to_audit_record(self) -> Dict[str, Any]:
        """
        Convert to audit record format for governance logging.
        
        Returns:
            Dictionary suitable for audit trail storage
        """
        return {
            "evidence_id": self.evidence_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "correlation_id": self.correlation_id,
            "evidence_type": self.evidence_type.value,
            "evidence_hash": self.evidence_hash,
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level.value,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "processing_time_ms": self.processing_time_ms,
            "governance_context_id": self.governance_context_id,
            "governance_execution_mode": self.governance_execution_mode,
            "actor_id": self.actor_id,
            "parent_evidence_ids": list(self.parent_evidence_ids),
            "child_evidence_ids": list(self.child_evidence_ids),
            "fallback_used": self.fallback_used,
            "retries_attempted": self.retries_attempted,
            "is_high_confidence": self.is_high_confidence,
            "is_governance_compliant": self.is_governance_compliant,
            "has_warnings": len(self.warnings) > 0,
            "has_errors": len(self.errors) > 0,
            "metadata_keys": list(self.metadata.keys()),
        }
    
    @staticmethod
    def create_evidence_hash(evidence_data: Dict[str, Any]) -> str:
        """
        Create deterministic hash for evidence data.
        
        Args:
            evidence_data: Evidence data dictionary
            
        Returns:
            64-character lowercase hex SHA-256 hash
        """
        import json
        
        # Create deterministic JSON representation
        normalized_json = json.dumps(
            evidence_data,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        )
        
        return hashlib.sha256(normalized_json.encode('utf-8')).hexdigest()
    
    @classmethod
    def from_agent_result(
        cls,
        agent_name: str,
        agent_result: AgentResult,
        evidence_type: AgentEvidenceType,
        correlation_id: str,
        execution_id: Optional[str] = None,
        governance_context_id: Optional[str] = None,
        governance_execution_mode: str = "UNKNOWN",
        actor_id: Optional[str] = None,
        agent_version: Optional[str] = None,
        parent_evidence_ids: Optional[List[str]] = None,
    ) -> "AgentEvidenceEvent":
        """
        Create evidence event from standard AgentResult.
        
        Args:
            agent_name: Name of the agent that produced the result
            agent_result: AgentResult from agent execution
            evidence_type: Type of evidence produced
            correlation_id: Governance correlation ID
            execution_id: Unique execution identifier (generated if None)
            governance_context_id: Governance context identifier
            governance_execution_mode: Governance execution mode
            actor_id: Actor identifier for audit trail
            agent_version: Agent version string
            parent_evidence_ids: List of parent evidence IDs for workflow chains
            
        Returns:
            AgentEvidenceEvent instance
        """
        import uuid
        
        execution_id = execution_id or str(uuid.uuid4())
        
        # Extract evidence data from agent result
        evidence_data = {
            "success": agent_result.success,
            "data": agent_result.data,
            "error": agent_result.error,
            "error_type": agent_result.error_type,
        }
        
        evidence_hash = cls.create_evidence_hash(evidence_data)
        
        # Calculate confidence from agent result
        confidence_score = 1.0 if agent_result.success else 0.0
        # Adjust based on fallback usage
        if agent_result.fallback_used:
            confidence_score *= 0.7  # Reduce confidence for fallback results
        # Adjust based on retries
        if agent_result.retries_used > 0:
            confidence_score *= max(0.5, 1.0 - (agent_result.retries_used * 0.1))
        
        confidence_level = cls._calculate_confidence_level(confidence_score)
        
        return cls(
            agent_name=agent_name,
            agent_version=agent_version,
            correlation_id=correlation_id,
            evidence_type=evidence_type,
            evidence_data=evidence_data,
            evidence_hash=evidence_hash,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            execution_id=execution_id,
            timestamp=datetime.now(UTC).isoformat(),
            processing_time_ms=agent_result.processing_time_ms,
            governance_context_id=governance_context_id,
            governance_execution_mode=governance_execution_mode,
            actor_id=actor_id,
            parent_evidence_ids=parent_evidence_ids or [],
            child_evidence_ids=[],
            agent_result=agent_result,
            fallback_used=agent_result.fallback_used,
            retries_attempted=agent_result.retries_used,
            warnings=list(agent_result.warnings) if agent_result.warnings else [],
            errors=[agent_result.error] if agent_result.error else [],
        )


@runtime_checkable
class AgentEvidenceProtocol(Protocol):
    """
    Protocol for agents that produce standardized evidence events.
    
    This protocol enables agents to be governance-aware while maintaining
    compatibility with existing agent implementations that use AgentResult.
    """
    
    @abstractmethod
    async def process_with_evidence(
        self,
        input_data: Dict[str, Any],
        correlation_id: str,
        evidence_type: AgentEvidenceType,
        governance_context_id: Optional[str] = None,
        governance_execution_mode: str = "STRICT",
        actor_id: Optional[str] = None,
    ) -> AgentEvidenceEvent:
        """
        Process input and return standardized evidence event.
        
        Args:
            input_data: Input data for processing
            correlation_id: Governance correlation ID
            evidence_type: Type of evidence to produce
            governance_context_id: Governance context ID
            governance_execution_mode: Governance execution mode
            actor_id: Actor identifier for audit trail
            
        Returns:
            AgentEvidenceEvent with complete evidence metadata
        """
        ...


@runtime_checkable
class WorkflowEvidenceManagerProtocol(Protocol):
    """
    Protocol for collecting and managing evidence events across workflow executions.
    
    Note: Named WorkflowEvidenceManagerProtocol to avoid conflict with existing
    EvidenceCollectorProtocol in mahoun.preproduction.base_validator.
    """
    
    @abstractmethod
    def collect_evidence(self, evidence: AgentEvidenceEvent) -> None:
        """
        Collect an evidence event for the current workflow.
        
        Args:
            evidence: AgentEvidenceEvent to collect
        """
        ...
    
    @abstractmethod
    def get_evidence_chain(self, correlation_id: str) -> List[AgentEvidenceEvent]:
        """
        Get complete evidence chain for a correlation ID.
        
        Args:
            correlation_id: Governance correlation ID
            
        Returns:
            List of AgentEvidenceEvent instances in chronological order
        """
        ...
    
    @abstractmethod
    def link_evidence(self, parent_id: str, child_id: str) -> None:
        """
        Link evidence events in a parent-child relationship.
        
        Args:
            parent_id: Evidence ID of the parent event
            child_id: Evidence ID of the child event
        """
        ...


class DefaultWorkflowEvidenceManager:
    """
    Default implementation of WorkflowEvidenceManagerProtocol.
    
    This manager maintains evidence chains in memory and provides
    basic evidence management capabilities for workflow orchestration.
    """
    
    def __init__(self):
        """Initialize evidence manager"""
        self._evidence_store: Dict[str, AgentEvidenceEvent] = {}
        self._correlation_chains: Dict[str, List[str]] = {}
        self._evidence_links: Dict[str, List[str]] = {}  # parent_id -> child_ids
    
    def collect_evidence(self, evidence: AgentEvidenceEvent) -> None:
        """Collect an evidence event"""
        evidence_id = evidence.evidence_id
        self._evidence_store[evidence_id] = evidence
        
        # Add to correlation chain
        correlation_id = evidence.correlation_id
        if correlation_id not in self._correlation_chains:
            self._correlation_chains[correlation_id] = []
        self._correlation_chains[correlation_id].append(evidence_id)
        
        # Process parent links
        for parent_id in evidence.parent_evidence_ids:
            if parent_id not in self._evidence_links:
                self._evidence_links[parent_id] = []
            self._evidence_links[parent_id].append(evidence_id)
    
    def get_evidence_chain(self, correlation_id: str) -> List[AgentEvidenceEvent]:
        """Get complete evidence chain for correlation ID"""
        evidence_ids = self._correlation_chains.get(correlation_id, [])
        return [self._evidence_store[eid] for eid in evidence_ids if eid in self._evidence_store]
    
    def link_evidence(self, parent_id: str, child_id: str) -> None:
        """Link evidence events in parent-child relationship"""
        if parent_id not in self._evidence_links:
            self._evidence_links[parent_id] = []
        if child_id not in self._evidence_links[parent_id]:
            self._evidence_links[parent_id].append(child_id)
    
    def get_evidence_by_id(self, evidence_id: str) -> Optional[AgentEvidenceEvent]:
        """Get evidence event by ID"""
        return self._evidence_store.get(evidence_id)
    
    def get_child_evidence(self, parent_id: str) -> List[AgentEvidenceEvent]:
        """Get all child evidence for a parent"""
        child_ids = self._evidence_links.get(parent_id, [])
        return [self._evidence_store[cid] for cid in child_ids if cid in self._evidence_store]
    
    def get_governance_compliant_evidence(self, correlation_id: str) -> List[AgentEvidenceEvent]:
        """Get only governance-compliant evidence for correlation ID"""
        chain = self.get_evidence_chain(correlation_id)
        return [e for e in chain if e.is_governance_compliant]
    
    def get_high_confidence_evidence(self, correlation_id: str) -> List[AgentEvidenceEvent]:
        """Get only high-confidence evidence for correlation ID"""
        chain = self.get_evidence_chain(correlation_id)
        return [e for e in chain if e.is_high_confidence]
    
    def clear_evidence(self, correlation_id: str) -> None:
        """Clear all evidence for a correlation ID"""
        evidence_ids = self._correlation_chains.get(correlation_id, [])
        
        # Remove from evidence store
        for evidence_id in evidence_ids:
            self._evidence_store.pop(evidence_id, None)
        
        # Remove from correlation chains
        self._correlation_chains.pop(correlation_id, None)
        
        # Remove from links
        for evidence_id in evidence_ids:
            self._evidence_links.pop(evidence_id, None)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics"""
        total_evidence = len(self._evidence_store)
        correlation_count = len(self._correlation_chains)
        
        evidence_types = {}
        confidence_levels = {}
        governance_compliant = 0
        
        for evidence in self._evidence_store.values():
            # Count evidence types
            etype = evidence.evidence_type.value
            evidence_types[etype] = evidence_types.get(etype, 0) + 1
            
            # Count confidence levels
            clevel = evidence.confidence_level.value
            confidence_levels[clevel] = confidence_levels.get(clevel, 0) + 1
            
            # Count governance compliant
            if evidence.is_governance_compliant:
                governance_compliant += 1
        
        return {
            "total_evidence_events": total_evidence,
            "active_correlations": correlation_count,
            "evidence_types": evidence_types,
            "confidence_levels": confidence_levels,
            "governance_compliant_count": governance_compliant,
            "governance_compliance_rate": governance_compliant / max(1, total_evidence),
        }