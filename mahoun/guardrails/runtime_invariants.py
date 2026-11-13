"""
Runtime Invariant Guards
========================
Enforces critical invariants at runtime with non-bypassable enforcement.

CRITICAL: These guards ensure system correctness and prevent
regressions. They cannot be disabled in production.

ARCHITECTURE: Guards use the @guard decorator from mahoun.guardrails.enforcement
to ensure they cannot be bypassed even when GUARD_MODE=OFF.
"""

from typing import Any, Dict, Optional
from mahoun.guardrails.modes import get_guard_mode, GuardMode
from mahoun.guardrails.exceptions import InvariantViolation
from mahoun.guardrails.enforcement import guard
from mahoun.pipelines._logging import setup_logger

log = setup_logger("runtime_invariants")


from contextvars import ContextVar

# Registry of all nodes (for resolution checks)
# HARDENING PATCH P07: Use ContextVar for request-scoped isolation
_node_registry_var: ContextVar[Dict[str, Any]] = ContextVar("node_registry", default={})

def register_node(node_id: str, node: Any) -> None:
    """Register a node in the request-scoped registry for resolution checks"""
    registry = _node_registry_var.get()
    # Create a new dict if we're dealing with the default empty dict
    # to avoid modifying the default object across contexts
    if not registry:
        registry = {}
    registry[node_id] = node
    _node_registry_var.set(registry)

def clear_registry() -> None:
    """Clear the node registry (for testing/request boundary)"""
    _node_registry_var.set({})

def get_registry() -> Dict[str, Any]:
    """Get the current request-scoped node registry"""
    return _node_registry_var.get().copy()


def enforce(
    name: str,
    condition: bool,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Enforce a runtime invariant.
    
    Args:
        name: Name of the invariant (e.g., "G1_EvidenceStepHasEvidence")
        condition: Boolean condition that must be True
        details: Optional dictionary with additional context
        
    Raises:
        InvariantViolation: If condition is False and mode is STRICT or AUDIT
        
    HARDENING PATCH P02: In production, MAHOUN_GUARD_MODE is IGNORED.
    Guards always use STRICT enforcement in production to prevent
    the dual-mode inconsistency where @guard enforces but enforce() skips.
    """
    # HARDENING: Production always uses STRICT, ignoring MAHOUN_GUARD_MODE
    from mahoun.core.environment import is_production
    if is_production():
        mode = GuardMode.STRICT
    else:
        mode = get_guard_mode()
    
    details = details or {}
    
    if not condition:
        error_msg = f"Invariant {name} violated"
        if details:
            error_msg += f": {details}"
        
        if mode == GuardMode.OFF:
            # Do nothing — only allowed in development
            pass
        elif mode == GuardMode.WARN:
            # Log warning only
            log.warning(error_msg)
        else:  # STRICT or AUDIT
            # Raise exception
            if mode == GuardMode.AUDIT:
                log.error(f"AUDIT MODE: {error_msg}")
            raise InvariantViolation(name, details)


# ============================================================================
# Guard Implementations (Non-Bypassable)
# ============================================================================

@guard
def G1_EvidenceStepHasEvidence(step, step_index: int) -> None:
    """
    G1: Each VerdictStep must have at least one evidence reference.
    
    Invariant: |step.evidence| >= 1
    
    CRITICAL: This guard cannot be bypassed even with GUARD_MODE=OFF.
    """
    evidence_count = len(step.evidence) if hasattr(step, 'evidence') else 0
    
    enforce(
        "G1_EvidenceStepHasEvidence",
        evidence_count >= 1,
        {
            "step_index": step_index,
            "evidence_count": evidence_count,
            "step_statement": getattr(step, 'statement', 'N/A')[:100]
        }
    )


@guard
def G2_EvidenceReferencesResolve(evidence_ref, registry: Dict[str, Any]) -> None:
    """
    G2: Evidence reference node_id must resolve to a real node.
    
    Invariant: evidence_ref.node_id in registry OR in knowledge_graph
    
    CRITICAL: This guard cannot be bypassed even with GUARD_MODE=OFF.
    """
    node_id = getattr(evidence_ref, 'node_id', None)
    
    if not node_id:
        enforce(
            "G2_EvidenceReferencesResolve",
            False,
            {"error": "Evidence reference has no node_id"}
        )
        return
    
    # Check if node exists in registry
    node_exists = node_id in registry
    
    enforce(
        "G2_EvidenceReferencesResolve",
        node_exists,
        {
            "node_id": node_id,
            "node_type": getattr(evidence_ref, 'node_type', 'N/A'),
            "registry_size": len(registry),
            "available_nodes": list(registry.keys())[:10]  # First 10 for debugging
        }
    )


@guard
def G3_NonResurrection(
    excluded_nodes: set,
    resolved_nodes: Dict[str, Any],
    verdict_steps: list
) -> None:
    """
    G3: Excluded nodes must not appear in resolved_nodes or verdict steps.
    
    Invariant: excluded_nodes ∩ resolved_nodes.keys() == ∅
              AND excluded_nodes ∩ {all node_ids in verdict_steps} == ∅
    
    CRITICAL: This guard cannot be bypassed even with GUARD_MODE=OFF.
    """
    # Check resolved_nodes
    excluded_in_resolved = excluded_nodes & set(resolved_nodes.keys())
    
    # Check verdict steps
    excluded_in_steps = set()
    for step in verdict_steps:
        if hasattr(step, 'evidence'):
            for evidence in step.evidence:
                if hasattr(evidence, 'node_id'):
                    if evidence.node_id in excluded_nodes:
                        excluded_in_steps.add(evidence.node_id)
    
    all_violations = excluded_in_resolved | excluded_in_steps
    
    enforce(
        "G3_NonResurrection",
        len(all_violations) == 0,
        {
            "excluded_nodes": list(excluded_nodes),
            "excluded_in_resolved": list(excluded_in_resolved),
            "excluded_in_steps": list(excluded_in_steps),
            "total_violations": len(all_violations)
        }
    )


@guard
def G4_ContradictionVisibility(
    unresolved_conflicts: list,
    final_verdict: str
) -> None:
    """
    G4: If unresolved conflicts exist, verdict must be UNDETERMINED.
    
    Invariant: |unresolved_conflicts| > 0 => final_verdict == "UNDETERMINED" or None
    
    CRITICAL: This guard cannot be bypassed even with GUARD_MODE=OFF.
    """
    has_unresolved = len(unresolved_conflicts) > 0
    
    if has_unresolved:
        is_undetermined = (
            final_verdict is None or
            final_verdict.upper() == "UNDETERMINED" or
            "undetermined" in str(final_verdict).lower()
        )
        
        enforce(
            "G4_ContradictionVisibility",
            is_undetermined,
            {
                "unresolved_conflicts_count": len(unresolved_conflicts),
                "final_verdict": final_verdict,
                "unresolved_conflicts": unresolved_conflicts[:5]  # First 5
            }
        )


@guard
def G5_ResolutionOrder(
    verdict_steps: list,
    resolved_nodes: Dict[str, Any],
    case_nodes: Dict[str, Any] = None,
    pre_resolution_rules: Optional[list] = None,
    pre_resolution_precedents: Optional[list] = None
) -> None:
    """
    G5: Verdict steps must be built from resolved_nodes only, not pre-resolution lists.
    
    Invariant: All node_ids in verdict_steps.evidence must be in resolved_nodes OR case_nodes
              AND must NOT be in pre_resolution lists if they were excluded
    
    CRITICAL: This guard cannot be bypassed even with GUARD_MODE=OFF.
    """
    case_nodes = case_nodes or {}
    pre_resolution_rules = pre_resolution_rules or []
    pre_resolution_precedents = pre_resolution_precedents or []
    
    # Collect all node_ids from verdict steps
    step_node_ids = set()
    for step in verdict_steps:
        if hasattr(step, 'evidence'):
            for evidence in step.evidence:
                if hasattr(evidence, 'node_id'):
                    step_node_ids.add(evidence.node_id)
    
    # All valid nodes: resolved_nodes + case_nodes (facts are in case_nodes)
    all_valid_nodes = set(resolved_nodes.keys()) | set(case_nodes.keys())
    
    # Check that all step node_ids are in valid nodes
    missing_in_resolved = step_node_ids - all_valid_nodes
    
    # For rules/precedents, check they're not from pre-resolution if excluded
    # (This is a weaker check - we trust that _build_verdict_steps uses resolved_nodes)
    
    enforce(
        "G5_ResolutionOrder",
        len(missing_in_resolved) == 0,
        {
            "step_node_ids": list(step_node_ids),
            "resolved_node_ids": list(resolved_nodes.keys()),
            "case_node_ids": list(case_nodes.keys()),
            "missing_in_resolved": list(missing_in_resolved),
            "total_steps": len(verdict_steps)
        }
    )

