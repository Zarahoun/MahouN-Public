"""
MAHOUN Bootstrap Module
=======================

Core bootstrapping infrastructure for MAHOUN platform initialization.

Components:
- Manager: Main bootstrap orchestration
- Executors: Phase-specific bootstrap executors  
- Runtime: Runtime configuration and profiles
- Golden Master: Behavioral testing infrastructure

Phase Sequence:
1. RUNTIME_INTEGRITY - System integrity validation
2. CONFIGURATION - Config loading and validation
3. GOVERNANCE_KERNEL - Core governance setup
4. IMMUTABLE_LEDGER - Audit ledger initialization
5. NEO4J - Database setup
6. POLICY_ENGINE - Policy engine initialization
7. EMBEDDING_MODELS - AI model loading
8. LLM_LOADER - Large language model setup
9. AGENT_REGISTRY - Agent registration
10. SERVICES - Service layer setup
11. API - API layer initialization
12. READINESS_GATE - Final readiness validation

ARCHITECTURAL NOTE:
This module contains TIER-1 refactorable components per P0_REFACTORING_SCOPE.md.
The manager and context are TIER-0 locked and must not be modified without
constitutional review.
"""

__version__ = "2.0.0"

# Public exports for bootstrap functionality
from .manager import (
    BootstrapManager, 
    BootstrapContext, 
    BootstrapPhase, 
    PhaseResult,
    BootstrapException,
    get_bootstrap_manager,
    unified_bootstrap
)

__all__ = [
    "BootstrapManager",
    "BootstrapContext", 
    "BootstrapPhase",
    "PhaseResult", 
    "BootstrapException",
    "get_bootstrap_manager",
    "unified_bootstrap",
]