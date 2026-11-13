"""
MAHOUN Multi-Agent Architecture (Ultra Refactored)
===================================================

Enterprise-grade multi-agent system for legal document processing.

Features:
    - Circuit Breaker Pattern
    - Retry with Exponential Backoff
    - DAG-based Workflow Execution
    - Health Check & Monitoring

Agents:
    - DocParserAgent: Document parsing and text extraction
    - DisputeAgent: Legal dispute identification
    - ClaimAgent: Claim generation and structuring
    - TimelineAgent: Event timeline extraction
    - DelayAgent: Delay analysis in legal cases
    - NarrativeAgent: Legal-technical narrative generation
    - ContractAgent: Contract clause analysis

Usage:
    from mahoun.agents import UltraAgentFactory, UltraOrchestrator
    
    agent = await UltraAgentFactory.create("doc_parser")
    result = await agent.process({"text": "..."})
"""

__version__ = "3.1.0"

# Core - Ultra Base Agent
from .base_agent import (
    UltraBaseAgent,
    AgentConfig,
    AgentResult,
    AgentState,
    CircuitBreaker,
    CircuitBreakerState,
)
BaseAgent = UltraBaseAgent

# Orchestrator
from .orchestrator import (
    UltraOrchestrator,
    WorkflowDAG,
    WorkflowNode,
    NodeStatus,
    WorkflowStatus,
    ExecutionContext,
)
Orchestrator = UltraOrchestrator

# Factory
from .ultra_factory import (
    UltraAgentFactory,
    ULTRA_AGENT_REGISTRY
)
AgentFactory = UltraAgentFactory
AGENT_REGISTRY = ULTRA_AGENT_REGISTRY

# Domain Agents
# ----------------------------------------------------------------------------
# Group 1: Files named without 'ultra_' prefix but containing Ultra agents
# ----------------------------------------------------------------------------
from .contract_agent import (
    UltraContractAgent,
    ContractAgentConfig,
    ReasoningMode
)
ContractAgent = UltraContractAgent

from .doc_parser_agent import (
    UltraDocParserAgent,
    DocParserConfig
)
DocParserAgent = UltraDocParserAgent

# Dispute Agent (Legacy/Hybrid)
from .dispute_agent import (
    DisputeAgent,
    DisputeType,
    DisputeSeverity
)
UltraDisputeAgent = DisputeAgent # Alias for consistency

from .claim_agent import (
    UltraClaimAgent,
    ClaimAgentConfig,
    ClaimType
)
ClaimAgent = UltraClaimAgent

# ----------------------------------------------------------------------------
# Group 2: Files named WITH 'ultra_' prefix
# ----------------------------------------------------------------------------
from .ultra_narrative_agent import (
    UltraNarrativeAgent,
    NarrativeAgentConfig,
    NarrativeType,
    NarrativeSection
)
NarrativeAgent = UltraNarrativeAgent

from .ultra_precedent_agent import (
    UltraPrecedentAgent,
    PrecedentAgentConfig,
    PrecedentType,
    RelevanceLevel
)
LegalPrecedentAgent = UltraPrecedentAgent

from .ultra_timeline_agent import (
    UltraTimelineAgent,
    TimelineConfig
)
TimelineAgent = UltraTimelineAgent

from .ultra_delay_agent import (
    UltraDelayAgent,
    DelayConfig
)
DelayAgent = UltraDelayAgent

from .ultra_risk_assessment_agent import (
    UltraRiskAssessmentAgent,
    RiskAgentConfig
)
RiskAssessmentAgent = UltraRiskAssessmentAgent

__all__ = [
    # Core
    "UltraBaseAgent", "BaseAgent",
    "AgentConfig", "AgentResult", "AgentState",
    "CircuitBreaker", "CircuitBreakerState",
    
    # Orchestrator
    "UltraOrchestrator", "Orchestrator",
    "WorkflowDAG", "WorkflowNode", "NodeStatus",
    "WorkflowStatus", "ExecutionContext",
    
    # Factory
    "UltraAgentFactory", "AgentFactory",
    "ULTRA_AGENT_REGISTRY", "AGENT_REGISTRY",
    
    # Agents
    "UltraContractAgent", "ContractAgent", "ContractAgentConfig", "ReasoningMode",
    "UltraDocParserAgent", "DocParserAgent", "DocParserConfig",
    "UltraDisputeAgent", "DisputeAgent", "DisputeType", "DisputeSeverity",
    "UltraClaimAgent", "ClaimAgent", "ClaimAgentConfig", "ClaimType",
    "UltraNarrativeAgent", "NarrativeAgent", "NarrativeAgentConfig", "NarrativeType", "NarrativeSection",
    "UltraPrecedentAgent", "LegalPrecedentAgent", "PrecedentAgentConfig", "PrecedentType", "RelevanceLevel",
    "UltraTimelineAgent", "TimelineAgent", "TimelineConfig",
    "UltraDelayAgent", "DelayAgent", "DelayConfig",
    "UltraRiskAssessmentAgent", "RiskAssessmentAgent", "RiskAgentConfig"
]
