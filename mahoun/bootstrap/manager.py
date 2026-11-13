"""
MAHOUN Unified Bootstrap Manager
==============================

Enterprise-grade system initialization with proper dependency ordering,
fail-closed compliance, and comprehensive observability.

This replaces the scattered startup logic across api/main.py and 
mahoun/bootstrap/runtime.py with a single, authoritative entry point.

Architecture Principles:
1. GOVERNANCE FIRST - No service creation before governance validation
2. FAIL-CLOSED - Any failure stops the entire startup process
3. SINGLE ENTRY POINT - All initialization goes through BootstrapManager
4. OBSERVABLE - Full metrics, timing, and dependency tracking
5. ROLLBACK-READY - Phase-by-phase cleanup on failure

NOTE: This is distinct from scripts/execute_phase.py which handles 
migration/deployment phases. This module handles runtime system startup.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class BootstrapPhase(Enum):
    """
    12-phase bootstrap sequence with proper dependency ordering.
    Each phase MUST complete successfully before the next can begin.
    
    Order is critical - DO NOT reorder without architectural review.
    """
    
    # Phase 1: Foundation - GOVERNANCE FIRST (Critical)
    RUNTIME_INTEGRITY = "runtime_integrity"
    CONFIGURATION = "configuration" 
    GOVERNANCE_KERNEL = "governance_kernel"
    IMMUTABLE_LEDGER = "immutable_ledger"
    
    # Phase 2: Infrastructure (Critical)
    NEO4J = "neo4j"
    POLICY_ENGINE = "policy_engine"
    
    # Phase 3: AI/ML Components (High Priority)
    EMBEDDING_MODELS = "embedding_models"
    LLM_LOADER = "llm_loader"
    AGENT_REGISTRY = "agent_registry"
    
    # Phase 4: Application Layer (Standard Priority)
    SERVICES = "services"
    API = "api"
    
    # Phase 5: Final Validation (Required)
    READINESS_GATE = "readiness_gate"


@dataclass
class PhaseResult:
    """Result of a bootstrap phase execution"""
    phase: BootstrapPhase
    success: bool
    duration_ms: float
    error: Optional[Exception] = None
    components: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class BootstrapContext:
    """
    Shared context passed between phases.
    
    This carries state forward through the bootstrap sequence,
    allowing later phases to access components initialized by earlier ones.
    """
    start_time: float
    governance_validated: bool = False
    audit_sink_configured: bool = False
    switchboard_initialized: bool = False
    neo4j_connection: Any = None
    service_registry: Dict[str, Any] = field(default_factory=dict)
    phase_results: List[PhaseResult] = field(default_factory=list)


class BootstrapPhaseExecutor:
    """
    Base class for bootstrap phase executors.
    
    Each phase of the bootstrap process has a corresponding executor
    that implements the specific initialization logic for that phase.
    
    NOTE: This is distinct from scripts/execute_phase.py's PhaseExecutor
    which handles migration/deployment phases.
    """
    
    def __init__(self, phase: Optional[BootstrapPhase] = None, 
                 phase_name: Optional[str] = None, 
                 description: Optional[str] = None):
        """
        Initialize executor
        
        Args:
            phase: BootstrapPhase enum (preferred)
            phase_name: Phase name string (alternative)
            description: Human-readable description (optional)
        """
        self.phase = phase
        self.phase_name = phase_name or (phase.value if phase else "unknown")
        self.description = description or f"Bootstrap phase: {self.phase_name}"
        self.logger = logging.getLogger(f"{__name__}.{self.phase_name}")
        
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        """
        Execute the phase initialization logic.
        
        Must be overridden by subclasses to implement phase-specific logic.
        
        Args:
            context: Shared bootstrap context
            
        Returns:
            PhaseResult indicating success/failure with metrics
        """
        raise NotImplementedError(
            f"Phase {self.phase.value} executor must implement execute()"
        )
        
    async def rollback(self, context: BootstrapContext) -> None:
        """
        Clean up phase resources on failure.
        
        Override if phase creates resources that need cleanup.
        Default implementation does nothing (stateless phases).
        
        Args:
            context: Shared bootstrap context
        """
        self.logger.debug(f"No rollback needed for phase: {self.phase.value}")


class BootstrapException(Exception):
    """
    Exception raised when bootstrap fails.
    
    Carries phase information for precise error reporting.
    """
    
    def __init__(
        self, 
        message: str, 
        phase: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.phase = phase
        self.cause = cause
        
    def __str__(self):
        base = super().__str__()
        if self.phase:
            base = f"[Phase: {self.phase}] {base}"
        if self.cause:
            base = f"{base} (Caused by: {self.cause})"
        return base


class BootstrapManager:
    """
    Unified Bootstrap Manager - Single Entry Point for System Initialization
    
    Enforces proper dependency ordering with governance-first approach:
    1. Runtime Integrity Check
    2. Configuration Validation  
    3. Governance Kernel Validation (BEFORE any service creation) ← CRITICAL
    4. Immutable Ledger Setup
    5. Neo4j Database Layer
    6. Policy Engine
    7. Embedding Models
    8. LLM Loader
    9. Agent Registry
    10. Services Construction & Wiring
    11. API Layer
    12. Readiness Gate & Health Check
    
    Key Features:
    - Fail-closed compliance: Any phase failure stops entire startup
    - Full observability: Timing, metrics, dependency tracking
    - Rollback capability: Clean phase-by-phase cleanup on failure
    - Single point of truth: Replaces scattered initialization logic
    
    Design Principles:
    - GOVERNANCE FIRST: Validation before any service creation
    - FAIL-CLOSED: No partial startups - all or nothing
    - OBSERVABLE: Full metrics and timing for every phase
    - ROLLBACK-READY: Clean cleanup on any failure
    """
    
    def __init__(self):
        self.phase_executors: Dict[BootstrapPhase, BootstrapPhaseExecutor] = {}
        self._register_default_executors()
        
    def _register_default_executors(self):
        """
        Register default phase executors and coordinators.
        
        NEW: Phases 7-9 now use thin coordinators with service injection!
        """
        from mahoun.bootstrap.executors import (
            RuntimeIntegrityExecutor,
            ConfigurationExecutor,
            GovernanceKernelExecutor,
            ImmutableLedgerExecutor,
            Neo4jExecutor,
            PolicyRuleLoaderExecutor,
            ServicesExecutor,
            APIExecutor,
            ReadinessGateExecutor,
        )
        
        # Phase 1-4: Critical Infrastructure (unchanged)
        self.phase_executors[BootstrapPhase.RUNTIME_INTEGRITY] = RuntimeIntegrityExecutor()
        self.phase_executors[BootstrapPhase.CONFIGURATION] = ConfigurationExecutor()
        self.phase_executors[BootstrapPhase.GOVERNANCE_KERNEL] = GovernanceKernelExecutor()
        self.phase_executors[BootstrapPhase.IMMUTABLE_LEDGER] = ImmutableLedgerExecutor()
        
        # Phase 5-6: Database & Storage (unchanged)
        self.phase_executors[BootstrapPhase.NEO4J] = Neo4jExecutor()
        self.phase_executors[BootstrapPhase.POLICY_ENGINE] = PolicyRuleLoaderExecutor()
        
        # Phase 7-9: AI/ML Components (NEW: Will be set up with coordinators!)
        # NOTE: These will be dynamically created with service container
        self._service_container = None  # Lazy initialization
        
        # Phase 10: Services (unchanged)
        self.phase_executors[BootstrapPhase.SERVICES] = ServicesExecutor()
        
        # Phase 11-12: API & Readiness (unchanged)
        self.phase_executors[BootstrapPhase.API] = APIExecutor()
        self.phase_executors[BootstrapPhase.READINESS_GATE] = ReadinessGateExecutor()
        
    async def _setup_coordinators(self, context: BootstrapContext):
        """
        Setup service-based coordinators (Phases 7-9)
        
        This creates the service container and injects it into coordinators.
        Must be called after infrastructure phases are complete.
        """
        logger.info("🔧 Setting up service-based coordinators...")
        
        # Import coordinators
        from mahoun.bootstrap.coordinators import (
            EmbeddingModelsCoordinator,
            LLMLoaderCoordinator, 
            AgentRegistryCoordinator,
        )
        from mahoun.bootstrap.services import create_service_container
        
        # Create service container
        self._service_container = await create_service_container()
        
        # Register coordinators with service injection
        self.phase_executors[BootstrapPhase.EMBEDDING_MODELS] = EmbeddingModelsCoordinator(
            service_container=self._service_container
        )
        self.phase_executors[BootstrapPhase.LLM_LOADER] = LLMLoaderCoordinator(
            service_container=self._service_container
        )
        self.phase_executors[BootstrapPhase.AGENT_REGISTRY] = AgentRegistryCoordinator(
            service_container=self._service_container
        )
        
        # Store container in context for later use
        context.service_registry["service_container"] = self._service_container
        
        logger.info("✅ Service-based coordinators registered")
        
    def register_executor(
        self, 
        phase: BootstrapPhase, 
        executor: BootstrapPhaseExecutor
    ):
        """
        Register a custom executor for a phase.
        
        Allows for customization of phase execution logic.
        
        Args:
            phase: The phase to register executor for
            executor: The executor instance
        """
        self.phase_executors[phase] = executor
        logger.info(f"Registered executor for phase: {phase.value}")
        
    async def bootstrap(self) -> BootstrapContext:
        """
        Execute the complete bootstrap sequence.
        
        This is the main entry point for system initialization.
        Runs all 12 phases in strict order, enforcing fail-closed
        semantics - any failure stops the entire process.
        
        Returns:
            BootstrapContext with all initialized components
            
        Raises:
            BootstrapException: If any phase fails (fail-closed principle)
        """
        context = BootstrapContext(start_time=time.time())
        
        logger.info("=" * 80)
        logger.info("🚀 MAHOUN Unified Bootstrap Manager")
        logger.info("=" * 80)
        logger.info(f"📋 Bootstrap sequence: {len(BootstrapPhase)} phases")
        logger.info(f"🔒 Fail-closed mode: ENABLED")
        logger.info(f"⚡ Governance-first ordering: ENFORCED")
        logger.info("=" * 80)
        
        executed_phases = []
        
        try:
            for phase in BootstrapPhase:
                phase_num = len(executed_phases) + 1
                logger.info(
                    f"\n🔄 Phase {phase_num}/12: {phase.value.upper()}"
                )
                
                phase_start = time.time()
                
                # Get executor for this phase
                executor = self.phase_executors.get(phase)
                
                # NEW: Setup coordinators before Phase 7 (EMBEDDING_MODELS)
                if phase == BootstrapPhase.EMBEDDING_MODELS and executor is None:
                    await self._setup_coordinators(context)
                    executor = self.phase_executors.get(phase)
                
                if executor is None:
                    raise BootstrapException(
                        f"No executor registered for phase: {phase.value}",
                        phase=phase.value
                    )
                
                # Execute phase
                try:
                    result = await executor.execute(context)
                    result.duration_ms = (time.time() - phase_start) * 1000
                    
                    if not result.success:
                        raise BootstrapException(
                            f"Phase {phase.value} failed: {result.error}",
                            phase=phase.value,
                            cause=result.error
                        )
                        
                    context.phase_results.append(result)
                    executed_phases.append(phase)
                    
                    logger.info(
                        f"✅ Phase {phase.value} completed "
                        f"({result.duration_ms:.1f}ms)"
                    )
                    
                    if result.components:
                        logger.debug(
                            f"   📦 Components: {', '.join(result.components)}"
                        )
                    if result.metrics:
                        logger.debug(f"   📊 Metrics: {result.metrics}")
                        
                except Exception as e:
                    # Create failure result
                    failure_result = PhaseResult(
                        phase=phase,
                        success=False,
                        duration_ms=(time.time() - phase_start) * 1000,
                        error=e
                    )
                    context.phase_results.append(failure_result)
                    
                    logger.error(
                        f"❌ Phase {phase.value} FAILED after "
                        f"{failure_result.duration_ms:.1f}ms: {e}"
                    )
                    
                    raise BootstrapException(
                        f"Bootstrap failed at phase: {phase.value}",
                        phase=phase.value,
                        cause=e
                    )
                    
        except Exception as e:
            # Rollback all executed phases in reverse order
            logger.error("\n" + "=" * 80)
            logger.error("🔄 Bootstrap failed - initiating rollback sequence")
            logger.error("=" * 80)
            await self._rollback_phases(executed_phases, context)
            
            total_duration = (time.time() - context.start_time) * 1000
            logger.error("=" * 80)
            logger.error(
                f"💥 MAHOUN Bootstrap FAILED after {total_duration:.1f}ms"
            )
            logger.error(
                f"   Failed at phase: "
                f"{e.phase if hasattr(e, 'phase') else 'unknown'}"
            )
            logger.error("=" * 80)
            raise
            
        # Success!
        total_duration = (time.time() - context.start_time) * 1000
        logger.info("\n" + "=" * 80)
        logger.info(
            f"🎉 MAHOUN Bootstrap COMPLETED successfully in {total_duration:.1f}ms"
        )
        logger.info(f"📊 Services registered: {len(context.service_registry)}")
        logger.info(f"✅ All {len(BootstrapPhase)} phases completed")
        logger.info("=" * 80)
        
        return context
        
    async def _rollback_phases(
        self, 
        phases: List[BootstrapPhase], 
        context: BootstrapContext
    ):
        """
        Rollback executed phases in reverse order.
        
        Ensures clean cleanup when bootstrap fails.
        Continues even if individual rollbacks fail to clean up
        as much as possible.
        
        Args:
            phases: List of phases that were successfully executed
            context: Shared bootstrap context
        """
        rollback_phases = list(reversed(phases))
        
        logger.info(f"🔄 Rolling back {len(rollback_phases)} phases...")
        
        for phase in rollback_phases:
            try:
                executor = self.phase_executors.get(phase)
                if executor:
                    await executor.rollback(context)
                    logger.info(f"  ✅ Rolled back: {phase.value}")
            except Exception as rollback_error:
                logger.error(
                    f"  ❌ Rollback failed for {phase.value}: {rollback_error}"
                )
                # Continue with other rollbacks even if one fails
                
        logger.info("🔄 Rollback sequence completed")
        
    def get_bootstrap_metrics(self, context: BootstrapContext) -> Dict[str, Any]:
        """
        Get detailed bootstrap metrics and timing.
        
        Provides comprehensive performance and status information
        for observability and debugging.
        
        Args:
            context: Bootstrap context with phase results
            
        Returns:
            Dictionary with detailed metrics
        """
        total_duration = sum(r.duration_ms for r in context.phase_results)
        successful = [r for r in context.phase_results if r.success]
        failed = [r for r in context.phase_results if not r.success]
        
        return {
            "total_duration_ms": total_duration,
            "phases_completed": len(successful),
            "phases_failed": len(failed),
            "phase_timings": {
                r.phase.value: r.duration_ms 
                for r in context.phase_results
            },
            "services_registered": len(context.service_registry),
            "governance_validated": context.governance_validated,
            "audit_sink_configured": context.audit_sink_configured,
            "switchboard_initialized": context.switchboard_initialized,
            "success_rate": len(successful) / len(context.phase_results) 
                if context.phase_results else 0.0,
        }


# Singleton instance for global access
_bootstrap_manager: Optional[BootstrapManager] = None


def get_bootstrap_manager() -> BootstrapManager:
    """
    Get the global bootstrap manager instance.
    
    Uses singleton pattern to ensure single manager across application.
    
    Returns:
        The global BootstrapManager instance
    """
    global _bootstrap_manager
    if _bootstrap_manager is None:
        _bootstrap_manager = BootstrapManager()
    return _bootstrap_manager


async def unified_bootstrap() -> BootstrapContext:
    """
    Main entry point for unified system bootstrap.
    
    This is the ONLY function that should be called to initialize MAHOUN.
    Replaces all scattered initialization logic across api/main.py and
    mahoun/bootstrap/runtime.py.
    
    Usage:
        ```python
        from mahoun.bootstrap.manager import unified_bootstrap
        
        # In api/main.py lifespan:
        context = await unified_bootstrap()
        app.state.bootstrap_context = context
        ```
    
    Returns:
        BootstrapContext with all initialized components
        
    Raises:
        BootstrapException: If bootstrap fails (fail-closed principle)
    """
    manager = get_bootstrap_manager()
    return await manager.bootstrap()

