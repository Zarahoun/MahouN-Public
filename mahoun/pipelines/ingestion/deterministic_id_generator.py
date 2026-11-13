"""
Deterministic Entity ID Generator
=================================

Provides collision-resistant, deterministic IDs for legal entities
designed for cross-document consistency and legal auditability.
"""

import hashlib
import json
import re
from typing import Any, Dict, Optional


class DeterministicEntityIDGenerator:
    """
    Generates deterministic IDs for legal entities using SHA-256
    with canonicalization for cross-document consistency.
    
    Design Principles:
    - Collision resistant for legal-scale deployments
    - Deterministic: same input → same output across runs
    - Context-aware: includes disambiguating context when needed
    - Audit trail friendly: includes generation metadata
    """
    
    def __init__(self, namespace: str = "mahoun-legal-v1"):
        """
        Initialize the ID generator.
        
        Args:
            namespace: Versioned namespace to prevent cross-system collisions
        """
        self.namespace = namespace
        self.hash_algorithm = hashlib.sha256  # Stronger than MD5
        
    def generate_entity_id(
        self, 
        entity_type: str,
        entity_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a deterministic ID for a legal entity.
        
        Args:
            entity_type: Type of entity (Person, Organization, etc.)
            entity_data: Dictionary of entity attributes
            context: Optional context (case_id, date, etc.) for disambiguation
            
        Returns:
            Collision-resistant entity ID string with format: {entity_type}_{hash}
        """
        # Create canonical representation for deterministic hashing
        canonical_data = {
            "namespace": self.namespace,
            "entity_type": entity_type,
            "entity_data": self._canonicalize_entity_data(entity_data),
            "context": context or {},
            # Timestamp for audit, but NOT part of hash to maintain determinism
            "_audit_timestamp": "placeholder_for_determinism"
        }
        
        # Remove audit field before hashing to keep it deterministic
        canonical_data.pop("_audit_timestamp", None)
        
        # JSON serialize with sorted keys for deterministic output
        json_data = json.dumps(canonical_data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        
        # Generate hash
        hash_bytes = self.hash_algorithm(json_data.encode('utf-8')).digest()
        
        # Use first 24 bytes (192 bits) for ID - extremely collision resistant
        # 192 bits gives ~6.2e57 possibilities, negligible collision risk for legal systems
        entity_hash = hash_bytes[:24].hex()
        
        return f"{entity_type.lower()}_{entity_hash}"
    
    def _canonicalize_entity_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert entity data to canonical form for consistent hashing.
        Handles normalization, sorting, and type consistency.
        """
        canonical = {}
        
        for key, value in sorted(data.items()):
            if value is None:
                canonical[key] = None
            elif isinstance(value, str):
                # Apply consistent text normalization for ID generation
                canonical[key] = self._normalize_text_for_id(value)
            elif isinstance(value, (int, float, bool)):
                canonical[key] = value
            elif isinstance(value, list):
                # Sort lists for deterministic ordering, recursively canonicalize
                canonical[key] = [
                    self._canonicalize_entity_data(item) if isinstance(item, dict) else item
                    for item in sorted(value) if not isinstance(item, dict)
                ] + [
                    self._canonicalize_entity_data(item) if isinstance(item, dict) else item
                    for item in value if isinstance(item, dict)
                ]
                # Re-sort mixed lists by converting to string for comparison
                canonical[key].sort(key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x))
            elif isinstance(value, dict):
                canonical[key] = self._canonicalize_entity_data(value)
            else:
                # Fallback to string representation for other types
                canonical[key] = str(value)
                
        return canonical
    
    def _normalize_text_for_id(self, text: str) -> str:
        """
        Normalize text for ID generation - conservative approach.
        Only normalize what won't change semantic meaning or create false collisions.
        """
        if not text:
            return ""
            
        # Normalize digits only (preserves linguistic variations but ensures digit consistency)
        # Persian/Arabic digits → English digits
        digit_translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", 
            "01234567890123456789"
        )
        normalized = text.translate(digit_translation)
        
        # Normalize whitespace to single space, trim
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        
        # Convert to lowercase for case-insensitive matching
        # Note: This assumes case doesn't matter for entity identity in legal context
        # For case-sensitive entities, remove this line
        normalized = normalized.lower()
        
        return normalized
    
    def get_audit_info(
        self, 
        entity_type: str,
        entity_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get audit information for the ID generation process.
        Useful for debugging and compliance.
        """
        canonical_data = {
            "namespace": self.namespace,
            "entity_type": entity_type,
            "entity_data": self._canonicalize_entity_data(entity_data),
            "context": context or {},
            "algorithm": "SHA-256",
            "hash_truncation_bytes": 24
        }
        
        json_data = json.dumps(canonical_data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        hash_bytes = self.hash_algorithm(json_data.encode('utf-8')).digest()
        entity_hash = hash_bytes[:24].hex()
        
        return {
            "entity_id": f"{entity_type.lower()}_{entity_hash}",
            "input_data": canonical_data,
            "hash_input": json_data,
            "hash_output": entity_hash,
            "collision_resistance_bits": 192
        }


# Convenience function for backward compatibility
def generate_deterministic_entity_id(
    entity_type: str,
    entity_data: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    namespace: str = "mahoun-legal-v1"
) -> str:
    """
    Convenience function to generate deterministic entity ID.
    
    Args:
        entity_type: Type of entity
        entity_data: Entity attributes dictionary
        context: Optional disambiguating context
        namespace: Versioned namespace
        
    Returns:
        Deterministic entity ID
    """
    generator = DeterministicEntityIDGenerator(namespace=namespace)
    return generator.generate_entity_id(entity_type, entity_data, context)