"""
MAHOUN Policy Loader
====================

Classification: INFRASTRUCTURE ADAPTER
Purpose: Loads RedLines.yaml and instantiates PolicyRegistry.

This adapter abstracts the filesystem and YAML parsing away from the
Constitutional Kernel.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from mahoun.core.governance.policies import GovernancePolicy, PolicyRegistry


def load_redlines_policies(
    config_path: Optional[Path] = None,
) -> PolicyRegistry:
    """Load governance policies from RedLines.yaml.

    Args:
        config_path: Path to RedLines.yaml. Defaults to
            constitution/RedLines.yaml relative to project root.

    Returns:
        Immutable PolicyRegistry.

    Raises:
        FileNotFoundError: If RedLines.yaml does not exist.
        ValueError: If configuration is invalid.
    """
    if config_path is None:
        config_path = (
            Path(__file__).parent.parent.parent.parent
            / "constitution"
            / "RedLines.yaml"
        )

    if not config_path.exists():
        raise FileNotFoundError(
            f"RedLines configuration not found: {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f)

    policies: List[GovernancePolicy] = []

    # Threshold policies
    thresholds = raw.get("thresholds", {})
    policies.append(
        GovernancePolicy(
            name="min_agreement_score",
            description="Minimum agreement score between symbolic and neural reasoning",
            threshold=float(thresholds.get("min_agreement_score", 0.85)),
        )
    )
    policies.append(
        GovernancePolicy(
            name="min_confidence_score",
            description="Minimum confidence score for reasoning verdicts",
            threshold=float(thresholds.get("min_confidence_score", 0.70)),
        )
    )

    # Proof requirements
    proof_reqs = raw.get("proof_requirements", {})
    policies.append(
        GovernancePolicy(
            name="proof_tree_required",
            description="Every reasoning response must contain a proof_tree",
            enabled=bool(proof_reqs.get("proof_tree_required", True)),
            required_fields=frozenset({"proof_tree"}),
        )
    )
    policies.append(
        GovernancePolicy(
            name="evidence_linkage_required",
            description="Proof tree must contain evidence linkage",
            enabled=bool(proof_reqs.get("evidence_linkage_required", True)),
            required_fields=frozenset({"derived_facts"}),
        )
    )
    policies.append(
        GovernancePolicy(
            name="audit_trail_required",
            description="Audit trail must be complete",
            enabled=bool(proof_reqs.get("audit_trail_required", True)),
            required_fields=frozenset({"reasoning_mode", "execution_time_ms"}),
        )
    )

    # Hallucination prevention
    hallu = raw.get("hallucination_prevention", {})
    policies.append(
        GovernancePolicy(
            name="require_graph_evidence",
            description="Reject responses without graph evidence",
            enabled=bool(hallu.get("require_graph_evidence", True)),
        )
    )
    policies.append(
        GovernancePolicy(
            name="require_determinism",
            description="Require deterministic execution",
            enabled=bool(hallu.get("require_determinism", True)),
        )
    )
    policies.append(
        GovernancePolicy(
            name="reject_contradictions",
            description="Reject responses with contradictions",
            enabled=bool(hallu.get("reject_contradictions", True)),
        )
    )

    # Exceptions policy
    exceptions = raw.get("exceptions", {})
    policies.append(
        GovernancePolicy(
            name="no_silent_failures",
            description="Silent exception swallowing is forbidden",
            enabled=not bool(exceptions.get("allow_silent_failures", False)),
        )
    )

    # CI enforcement
    ci = raw.get("ci_enforcement", {})
    policies.append(
        GovernancePolicy(
            name="ci_fail_on_violation",
            description="CI must fail on RedLine violations",
            enabled=bool(ci.get("fail_ci_on_violation", True)),
        )
    )
    policies.append(
        GovernancePolicy(
            name="ci_block_merge_on_failure",
            description="Block merge on governance failures",
            enabled=bool(ci.get("block_merge_on_failure", True)),
        )
    )

    # Provenance policy (derived from audit requirements)
    audit = raw.get("audit", {})
    policies.append(
        GovernancePolicy(
            name="require_provenance",
            description="Every graph node/relationship must carry provenance metadata",
            enabled=bool(audit.get("require_correlation_id", True)),
            required_fields=frozenset(
                {"source", "timestamp", "correlation_id", "author"}
            ),
        )
    )

    return PolicyRegistry(policies)
