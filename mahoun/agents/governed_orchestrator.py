"""
Governed Workflow Orchestrator - Governance-Aware Wrapper
========================================================

Classification: GOVERNANCE INTEGRATION / ARCHITECTURAL WRAPPER
Purpose: Ensures all UltraOrchestrator operations execute under governance context

This wrapper implements the composition pattern around UltraOrchestrator to ensure
that all workflow executions are properly governed without modifying the original
orchestrator logic.

Key Features:
- Mandatory governance context enforcement for all workflow executions
- Preserves all existing UltraOrchestrator functionality
- Zero-impact rollout capability via dependency injection
- Comprehensive governance attestation for workflow operations
- Agent evidence correlation tracking

Per AGENTS.md Part 3 guidance: This wrapper extends existing components rather than
creating duplicates, following the established pattern.

Author: MAHOUN Architecture Integration Mission
Version: 1.0.0
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from mahoun.core.governance.governance_context import (
    GovernanceContext,
    GovernanceContextManager,
    GovernanceScopeEnforcer,
)
from mahoun.core.governance.violations import (
    GovernanceViolation,
    GovernanceViolationError,
    ViolationCategory,
    ViolationSeverity,
)
from mahoun.agents.orchestrator import (
    UltraOrchestrator,
    WorkflowDAG,
    WorkflowCheckpoint,
    WorkflowStatus,
    NodeStatus,
)
from mahoun.agents.base_agent import UltraBaseAgent, AgentResult

logger = logging.getLogger(__name__)


@dataclass
class GovernanceWorkflowMetadata:
    """Governance-specific metadata for workflow execution"""
    
    governance_context_id: str
    correlation_id: str
    execution_mode: str
    actor_id: Optional[str] = None
    governance_attestation: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.governance_attestation is None:
            self.governance_attestation = {}


class GovernedWorkflowOrchestrator:
    """
    Governance-aware wrapper around UltraOrchestrator.
    
    This wrapper ensures that ALL workflow executions go through proper
    governance context enforcement while preserving the complete functionality
    of the underlying UltraOrchestrator.
    
    Architecture:
        GovernedWorkflowOrchestrator (governance layer)
            ↓ (composition)
        UltraOrchestrator (workflow logic)
    
    Usage:
        # Create governed orchestrator
        base_orchestrator = UltraOrchestrator()
        orchestrator = GovernedWorkflowOrchestrator(base_orchestrator)
        
        # Register agents (same interface as UltraOrchestrator)
        orchestrator.register_agent("parser", ParserAgent())
        
        # Execute workflow (automatically governed)
        result = await orchestrator.execute_workflow(
            dag=workflow_dag,
            initial_data={"text": "..."},
            correlation_id="req-123"  # Optional governance correlation
        )
    """
    
    def __init__(
        self,
        base_orchestrator: UltraOrchestrator,
        enforce_governance: bool = True,
        enable_attestation: bool = True,
    ):
        """
        Initialize governed orchestrator.
        
        Args:
            base_orchestrator: UltraOrchestrator instance to wrap
            enforce_governance: Whether to enforce governance context (default: True)
            enable_attestation: Whether to collect governance attestation (default: True)
        """
        self._base_orchestrator = base_orchestrator
        self._enforce_governance = enforce_governance
        self._enable_attestation = enable_attestation
        
        # Track governance metadata for active workflows
        self._workflow_governance: Dict[str, GovernanceWorkflowMetadata] = {}
        
        logger.info(
            f"GovernedWorkflowOrchestrator initialized with governance_enforcement={enforce_governance}"
        )
    
    # ========================================================================
    # Agent Management (Delegate to Base Orchestrator)
    # ========================================================================
    
    def register_agent(self, name: str, agent: UltraBaseAgent):
        """Register an agent (delegates to base orchestrator)"""
        return self._base_orchestrator.register_agent(name, agent)
    
    def unregister_agent(self, name: str):
        """Unregister an agent (delegates to base orchestrator)"""
        return self._base_orchestrator.unregister_agent(name)
    
    def get_agent(self, name: str) -> Optional[UltraBaseAgent]:
        """Get agent by name (delegates to base orchestrator)"""
        return self._base_orchestrator.get_agent(name)
    
    def get_all_agent_status(self) -> Dict[str, Any]:
        """Get status of all registered agents (delegates to base orchestrator)"""
        return self._base_orchestrator.get_all_agent_status()
    
    # ========================================================================
    # Governance-Aware Workflow Execution
    # ========================================================================
    
    @GovernanceScopeEnforcer.enforce()
    async def execute_workflow(
        self,
        dag: WorkflowDAG,
        initial_data: Dict[str, Any],
        checkpoint: Optional[WorkflowCheckpoint] = None,
        max_parallel: int = 5,
        correlation_id: Optional[str] = None,
        execution_mode: str = "STRICT",
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a workflow DAG under governance context.
        
        This is the primary governance integration point. It ensures that:
        1. Governance context is active (enforced by decorator)
        2. All workflow execution is correlated with governance scope
        3. Agent executions inherit governance context
        4. Governance attestation is collected
        
        Args:
            dag: Workflow DAG definition
            initial_data: Initial input data
            checkpoint: Optional checkpoint to resume from
            max_parallel: Maximum parallel node executions
            correlation_id: Optional governance correlation ID
            execution_mode: Governance execution mode
            actor_id: Optional actor identity for audit trail
            
        Returns:
            Workflow result with governance metadata
            
        Raises:
            GovernanceViolationError: If governance context is not active
        """
        # Get current governance context (guaranteed to exist by @enforce decorator)
        governance_ctx = GovernanceContextManager.require_context()
        
        # Use provided correlation_id or inherit from governance context
        final_correlation_id = correlation_id or governance_ctx.correlation_id
        
        logger.info(
            f"Starting governed workflow execution",
            extra={
                "dag_name": dag.name,
                "governance_context_id": governance_ctx.context_id,
                "correlation_id": final_correlation_id,
                "execution_mode": execution_mode,
                "actor_id": actor_id,
                "enforce_governance": self._enforce_governance,
            },
        )
        
        # Create governance metadata for this workflow
        workflow_governance = GovernanceWorkflowMetadata(
            governance_context_id=governance_ctx.context_id,
            correlation_id=final_correlation_id,
            execution_mode=execution_mode,
            actor_id=actor_id,
            governance_attestation=governance_ctx.get_attestation() if self._enable_attestation else {},
        )
        
        try:
            # Validate governance requirements
            if self._enforce_governance:
                governance_ctx.validate_governance_scope()
            
            # Enhance initial_data with governance correlation
            enhanced_data = {
                **initial_data,
                "_governance_correlation_id": final_correlation_id,
                "_governance_context_id": governance_ctx.context_id,
                "_governance_execution_mode": execution_mode,
                "_governance_actor_id": actor_id,
            }
            
            # Execute workflow using base orchestrator
            # NOTE: The governance context remains active throughout this call
            result = await self._base_orchestrator.execute_workflow(
                dag=dag,
                initial_data=enhanced_data,
                checkpoint=checkpoint,
                max_parallel=max_parallel,
            )
            
            # Track governance metadata for completed workflow
            if result.get("success") and result.get("workflow_id"):
                workflow_id = result["workflow_id"]
                self._workflow_governance[workflow_id] = workflow_governance
            
            # Enhance result with governance information
            governance_result = self._enhance_result_with_governance(
                result, workflow_governance, governance_ctx
            )
            
            logger.info(
                f"Governed workflow execution completed",
                extra={
                    "workflow_id": result.get("workflow_id"),
                    "success": result.get("success", False),
                    "governance_context_id": governance_ctx.context_id,
                    "correlation_id": final_correlation_id,
                },
            )
            
            return governance_result
            
        except Exception as e:
            logger.error(
                f"Governed workflow execution failed",
                extra={
                    "dag_name": dag.name,
                    "governance_context_id": governance_ctx.context_id,
                    "correlation_id": final_correlation_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            
            # Re-raise with governance context if it's not already a governance error
            if not isinstance(e, GovernanceViolationError):
                raise GovernanceViolationError(
                    GovernanceViolation(
                        category=ViolationCategory.WORKFLOW_EXECUTION_FAILURE,
                        severity=ViolationSeverity.HIGH,
                        message=f"Governed workflow execution failed: {str(e)}",
                        details={
                            "dag_name": dag.name,
                            "governance_context_id": governance_ctx.context_id,
                            "correlation_id": final_correlation_id,
                            "original_error": str(e),
                            "error_type": type(e).__name__,
                        },
                        source="GovernedWorkflowOrchestrator",
                        correlation_id=final_correlation_id,
                    )
                ) from e
            else:
                raise
    
    def _enhance_result_with_governance(
        self,
        result: Dict[str, Any],
        workflow_governance: GovernanceWorkflowMetadata,
        governance_ctx: GovernanceContext,
    ) -> Dict[str, Any]:
        """
        Enhance workflow result with governance information.
        
        Args:
            result: Original workflow result
            workflow_governance: Governance metadata
            governance_ctx: Active governance context
            
        Returns:
            Enhanced result with governance attestation
        """
        enhanced_result = result.copy()
        
        # Add governance metadata
        enhanced_result["governance"] = {
            "context_id": workflow_governance.governance_context_id,
            "correlation_id": workflow_governance.correlation_id,
            "execution_mode": workflow_governance.execution_mode,
            "actor_id": workflow_governance.actor_id,
            "governance_active": True,
            "attestation": workflow_governance.governance_attestation,
            "correlation_lineage": governance_ctx.correlation_lineage,
        }
        
        return enhanced_result
    
    # ========================================================================
    # Checkpoint Management (Enhanced with Governance)
    # ========================================================================
    
    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        """Get checkpoint for a workflow (delegates to base orchestrator)"""
        return self._base_orchestrator.get_checkpoint(workflow_id)
    
    def get_workflow_governance_metadata(self, workflow_id: str) -> Optional[GovernanceWorkflowMetadata]:
        """Get governance metadata for a workflow"""
        return self._workflow_governance.get(workflow_id)
    
    # ========================================================================
    # Status and Metrics (Enhanced with Governance)
    # ========================================================================
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a workflow with governance information"""
        status = self._base_orchestrator.get_workflow_status(workflow_id)
        
        if status and workflow_id in self._workflow_governance:
            governance_metadata = self._workflow_governance[workflow_id]
            status["governance"] = {
                "context_id": governance_metadata.governance_context_id,
                "correlation_id": governance_metadata.correlation_id,
                "execution_mode": governance_metadata.execution_mode,
                "actor_id": governance_metadata.actor_id,
                "governance_active": True,
            }
        
        return status
    
    # ========================================================================
    # Progress Tracking (Delegate to Base)
    # ========================================================================
    
    def on_progress(self, callback):
        """Register progress callback (delegates to base orchestrator)"""
        return self._base_orchestrator.on_progress(callback)
    
    # ========================================================================
    # Workflow Visualization (Delegate to Base)
    # ========================================================================
    
    def visualize_dag(self, dag: WorkflowDAG, format: str = "ascii") -> str:
        """Generate visual representation of workflow DAG (delegates to base orchestrator)"""
        return self._base_orchestrator.visualize_dag(dag, format)
    
    # ========================================================================
    # Direct LLM Access (Governance-Aware)
    # ========================================================================
    
    @GovernanceScopeEnforcer.enforce()
    async def ask(self, prompt: str) -> str:
        """
        Direct query to the Ultra LLM engine under governance context.
        
        Args:
            prompt: Input text
            
        Returns:
            Generated text with governance correlation
        """
        governance_ctx = GovernanceContextManager.require_context()
        
        logger.info(
            "Direct LLM query under governance context",
            extra={
                "governance_context_id": governance_ctx.context_id,
                "correlation_id": governance_ctx.correlation_id,
            },
        )
        
        return await self._base_orchestrator.ask(prompt)
    
    # ========================================================================
    # Governance Configuration
    # ========================================================================
    
    def enable_governance_enforcement(self):
        """Enable governance enforcement for all workflow operations"""
        self._enforce_governance = True
        logger.info("Governance enforcement enabled")
    
    def disable_governance_enforcement(self):
        """
        Disable governance enforcement (for testing/migration only).
        
        WARNING: This should only be used during migration or testing phases.
        """
        self._enforce_governance = False
        logger.warning("Governance enforcement DISABLED - use only for testing/migration")
    
    def is_governance_enforced(self) -> bool:
        """Check if governance enforcement is active"""
        return self._enforce_governance
    
    # ========================================================================
    # Governance Status and Diagnostics
    # ========================================================================
    
    def get_governance_status(self) -> Dict[str, Any]:
        """Get governance status for the orchestrator"""
        return {
            "governance_enforced": self._enforce_governance,
            "attestation_enabled": self._enable_attestation,
            "active_governed_workflows": len(self._workflow_governance),
            "governance_workflow_ids": list(self._workflow_governance.keys()),
        }
    
    def validate_governance_compliance(self) -> Dict[str, Any]:
        """
        Validate governance compliance for the orchestrator.
        
        Returns:
            Compliance report with any violations found
        """
        violations = []
        
        # Check if governance enforcement is active
        if not self._enforce_governance:
            violations.append({
                "severity": "WARNING",
                "message": "Governance enforcement is disabled",
                "recommendation": "Enable governance enforcement for production use",
            })
        
        # Validate base orchestrator compliance
        try:
            base_status = self._base_orchestrator.get_all_agent_status()
            # Additional compliance checks can be added here
        except Exception as e:
            violations.append({
                "severity": "ERROR",
                "message": f"Failed to get base orchestrator status: {e}",
                "recommendation": "Check base orchestrator health",
            })
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "governance_status": self.get_governance_status(),
            "timestamp": governance_ctx.timestamp if (governance_ctx := GovernanceContextManager.get_current_context()) else None,
        }