"""
Ontology Gate Adapter
======================

Wraps existing OntologyEnforcer to satisfy OntologyGateProtocol.

This adapter:
- Extends runtime validation with schema-level checks
- Adds batch validation capabilities
- Provides schema version tracking
- Maintains backward compatibility with existing OntologyEnforcer

Classification: INTEGRATION ADAPTER
"""

import logging
from typing import Any, Dict, List

from mahoun.core.governance.ontology_enforcer import OntologyEnforcer
from mahoun.core.governance.violations import GovernanceViolationError
from mahoun.core.protocols import OntologyValidationResult

logger = logging.getLogger(__name__)


class OntologyGateAdapter:
    """
    Adapter wrapping OntologyEnforcer to satisfy OntologyGateProtocol.
    
    Adds schema-level validation on top of runtime validation.
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(self, enforcer: OntologyEnforcer):
        """
        Initialize adapter with OntologyEnforcer instance.
        
        Args:
            enforcer: OntologyEnforcer to wrap
        """
        self.enforcer = enforcer
        logger.info(f"OntologyGateAdapter initialized (schema v{self.SCHEMA_VERSION})")
    
    def validate_schema(
        self,
        nodes: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        *,
        strict: bool = True
    ) -> OntologyValidationResult:
        """
        Validate graph structure against ontology schema.
        
        Args:
            nodes: List of node dicts with 'type' key
            relationships: List of relationship dicts with 'type', 'source_type', 'target_type'
            strict: If True, fail on first violation; if False, collect all violations
        
        Returns:
            OntologyValidationResult with validation status
        
        Raises:
            ValueError: If nodes/relationships have invalid structure
        """
        violations = []
        validated_count = 0
        
        # Validate structure
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"Node at index {idx} must be dict, got {type(node)}")
            if 'type' not in node:
                raise ValueError(f"Node at index {idx} missing 'type' field")
        
        for idx, rel in enumerate(relationships):
            if not isinstance(rel, dict):
                raise ValueError(f"Relationship at index {idx} must be dict, got {type(rel)}")
            
            required_keys = {'type', 'source_type', 'target_type'}
            missing_keys = required_keys - set(rel.keys())
            if missing_keys:
                raise ValueError(
                    f"Relationship at index {idx} missing required keys: {missing_keys}"
                )
        
        # Validate relationships against ontology
        for idx, rel in enumerate(relationships):
            source_type = rel['source_type']
            rel_type = rel['type']
            target_type = rel['target_type']
            validated_count += 1
            
            try:
                self.enforcer.validate_relationship(
                    source_type=source_type,
                    relationship_type=rel_type,
                    target_type=target_type,
                    correlation_id=f"schema_validation_{idx}"
                )
            except GovernanceViolationError as e:
                violation_msg = (
                    f"Relationship {idx}: {source_type} -[{rel_type}]-> {target_type} "
                    f"violates ontology: {e}"
                )
                violations.append(violation_msg)
                
                if strict:
                    # Fail immediately in strict mode
                    return OntologyValidationResult(
                        is_valid=False,
                        violations=violations,
                        validated_relationships=validated_count,
                        schema_version=self.SCHEMA_VERSION,
                        metadata={
                            "strict_mode": True,
                            "total_relationships": len(relationships),
                            "failed_at_index": idx,
                        }
                    )
        
        # All validations passed
        is_valid = len(violations) == 0
        
        return OntologyValidationResult(
            is_valid=is_valid,
            violations=violations,
            validated_relationships=validated_count,
            schema_version=self.SCHEMA_VERSION,
            metadata={
                "strict_mode": strict,
                "total_relationships": len(relationships),
                "total_nodes": len(nodes),
            }
        )
    
    def validate_relationship(
        self,
        source_type: str,
        relationship_type: str,
        target_type: str,
        *,
        correlation_id: str | None = None
    ) -> None:
        """
        Validate single relationship (runtime check).
        
        Delegates to underlying OntologyEnforcer.
        
        Args:
            source_type: Source node type
            relationship_type: Relationship type
            target_type: Target node type
            correlation_id: Optional correlation ID for tracing
        
        Raises:
            GovernanceViolationError: If relationship violates ontology
        """
        self.enforcer.validate_relationship(
            source_type=source_type,
            relationship_type=relationship_type,
            target_type=target_type,
            correlation_id=correlation_id
        )
    
    def get_schema_version(self) -> str:
        """Get ontology schema version."""
        return self.SCHEMA_VERSION
    
    def get_valid_relationships(self, source_type: str):
        """Get valid relationship types for a source type (passthrough)."""
        return self.enforcer.get_valid_relationships(source_type)
    
    def get_valid_targets(self, source_type: str, relationship_type: str):
        """Get valid target types (passthrough)."""
        return self.enforcer.get_valid_targets(source_type, relationship_type)
    
    @property
    def rule_count(self) -> int:
        """Total number of ontology rules."""
        return self.enforcer.rule_count
