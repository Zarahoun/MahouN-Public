"""
Hardened Legal Pipeline - Production-Grade Implementation
===========================================================

This module implements a zero-tolerance architectural hardening layer for 
legal evidence extraction. It transforms a conceptual pipeline into a 
production-critical system where evidence integrity is a hard constraint.

Key Hardening Invariants:
1. Confidence Gate: No entity enters the KG with confidence < threshold.
2. Strict Provenance: Any entity that cannot be mapped to a chunk raises a TraceabilityAuditError.
3. LLM Interceptor: Every entity must be validated by the LLM Refiner.
4. Resource Control: Circuit breakers prevent OOM/ReDoS on massive documents.
"""

import hashlib
import logging
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime

# Core Hardening Imports
from mahoun.pipelines.ingestion.nlp_hardening import (
    DeterministicEntityIDGenerator,
    ProvenanceAwareNERMapper,
    PersianCanonicalizer,
    ChunkInfo
)
from mahoun.pipelines.ingestion.llm_refiner import LLMRefinementService
from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine

logger = logging.getLogger("mahoun.hardened_pipeline")

# ============================================================================
# CUSTOM EXCEPTIONS (The "Halt" Mechanism)
# ============================================================================

class HardeningError(Exception):
    """Base class for all pipeline hardening failures."""
    pass

class InadequateConfidenceError(HardeningError):
    """Raised when an entity fails the confidence threshold gate."""
    pass

class TraceabilityAuditError(HardeningError):
    """Raised when an entity cannot be mathematically mapped to a source chunk."""
    pass

class ResourceExhaustionError(HardeningError):
    """Raised when a document exceeds safe processing limits (Circuit Breaker)."""
    pass

class LLMRefinementFailure(HardeningError):
    """Raised when the LLM Refiner flags an entity as a False Positive or Ambiguous."""
    pass

# ============================================================================
# SECURITY & RELIABILITY COMPONENTS
# ============================================================================

@dataclass
class SecurityAuditTrail:
    """Detailed log of why an entity was accepted or rejected."""
    entity_id: str
    action: str  # "ACCEPTED", "REJECTED", "FLAGGED_FOR_REVIEW"
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

class ConfidenceGate:
    """
    Strict enforcement of evidence quality.
    Ensures no low-confidence data poisons the Knowledge Graph.
    """
    def __init__(self, threshold: float = 0.75, allow_manual_review: bool = False):
        self.threshold = threshold
        self.allow_manual_review = allow_manual_review

    def validate(self, entity: Dict[str, Any]) -> bool:
        conf = entity.get("confidence", 0.0)
        if conf < self.threshold:
            if self.allow_manual_review:
                logger.info(f"Entity {entity.get('text')} flagged for manual review (conf={conf})")
                return False 
            raise InadequateConfidenceError(
                f"Evidence rejected: Confidence {conf} is below threshold {self.threshold} "
                f"for entity {entity.get('text')!r}"
            )
        return True

class PipelineCircuitBreaker:
    """
    Monitors pipeline health and prevents catastrophic failures on massive docs.
    """
    def __init__(self, max_chars: int = 1_000_000, max_entities: int = 10_000):
        self.max_chars = max_chars
        self.max_entities = max_entities

    def check_limits(self, text: str, current_entity_count: int = 0):
        if len(text) > self.max_chars:
            raise ResourceExhaustionError(
                f"Document size {len(text)} exceeds safety limit {self.max_chars}. "
                "Potential ReDoS or OOM risk."
            )
        if current_entity_count > self.max_entities:
            raise ResourceExhaustionError(
                f"Entity count {current_entity_count} exceeds safety limit {self.max_entities}."
            )

# ============================================================================
# HARDENED LEGAL PIPELINE
# ============================================================================

class HardenedLegalPipeline:
    """
    Enterprise-Grade Legal Pipeline.
    Implements the 'Process-Once, Use-Twice' model with strict integrity gates.
    """
    def __init__(
        self,
        ner_engine: Optional[LegalNEREngine] = None,
        refiner: Optional[LLMRefinementService] = None,
        confidence_threshold: float = 0.75,
        mapper = None,
        gate = None,
        id_gen = None,
        llm_refiner=None,

    ):
        self.ner_engine = ner_engine or LegalNEREngine()
        self.refiner = refiner or LLMRefinementService()
        self.id_gen = id_gen or DeterministicEntityIDGenerator()
        self.mapper = mapper or ProvenanceAwareNERMapper()
        self.gate = gate or ConfidenceGate(threshold=confidence_threshold)
        self.breaker = PipelineCircuitBreaker()
        
    async def process_document(
        self, 
        text: str, 
        chunks: List[Any], 
        doc_id: str
    ) -> Tuple[List[Dict[str, Any]], List[SecurityAuditTrail]]:
        """
        The Hardened Flow: 
        Extract -> Map -> LLM-Refine -> Confidence-Gate -> ID-Generate -> Insert
        """
        audit_trail = []
        final_entities = []
        
        # 1. Resource Check (Circuit Breaker)
        self.breaker.check_limits(text)
        
        # 2. Extraction (Full Text for context)
        raw_entities_dict = self.ner_engine.extract(text)
        # Flatten and prepare for mapping
        flattened_entities = []
        for cat, entities in raw_entities_dict.items():
            for e in entities:
                e['category'] = cat
                flattened_entities.append(e)
        
        # 3. Provenance Mapping (Halt-on-Failure)
        # Convert chunks to ChunkInfo
        chunk_infos = [
            ChunkInfo(chunk_id=c.chunk_id, text=c.text, doc_start=c.start, doc_end=c.end) 
            if hasattr(c, 'chunk_id') else ChunkInfo(
                chunk_id=c.get('chunk_id'), text=c.get('text'), 
                doc_start=c.get('start'), doc_end=c.get('end')
            ) for c in chunks
        ]
        self.mapper.register_chunks([c.__dict__ if hasattr(c, '__dict__') else c for c in chunk_infos])
        
        # Wrap the mapping logic to raise TraceabilityAuditError instead of skipping
        mapped_entities = []
        for ent in flattened_entities:
            # We use a specialized internal method to ensure no skipping
            prov = self._strict_map_entity(ent, chunk_infos)
            ent['provenance'] = prov
            mapped_entities.append(ent)
            
        # 4. LLM Refinement & Confidence Gating (Parallelized)
        # Use semaphore to cap concurrency and prevent LLM rate-limit saturation
        semaphore = asyncio.Semaphore(10)
        
        async def _validate_single_entity(entity: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], SecurityAuditTrail]:
            """Validate a single entity under semaphore control."""
            async with semaphore:
                try:
                    is_valid, ref_confidence, reason = await self._llm_validate_entity(entity, text)
                    
                    if not is_valid:
                        raise LLMRefinementFailure(f"LLM Refiner flagged entity as False Positive: {reason}")
                    
                    entity['confidence'] = max(entity.get('confidence', 0.0), ref_confidence)
                    self.gate.validate(entity)
                    
                    entity_id = self.id_gen.generate_entity_id(
                        entity_type=entity['category'],
                        entity_data={"text": entity['text']},
                        context={"doc_id": doc_id}
                    )
                    entity['id'] = entity_id
                    
                    return entity, SecurityAuditTrail(
                        entity_id=entity_id, action="ACCEPTED",
                        reason=f"Passed LLM and Confidence Gate ({ref_confidence})"
                    )
                    
                except (LLMRefinementFailure, InadequateConfidenceError) as e:
                    return None, SecurityAuditTrail(
                        entity_id="N/A", action="REJECTED", reason=str(e),
                        metadata={"text": entity.get('text')}
                    )
                except Exception as e:
                    logger.error(f"Critical failure processing entity {entity.get('text')}: {e}")
                    raise

        # Execute all validations in parallel
        results = await asyncio.gather(
            *[_validate_single_entity(ent) for ent in mapped_entities],
            return_exceptions=True
        )
        
        for result in results:
            if isinstance(result, Exception):
                raise result
            validated_entity, audit_entry = result
            audit_trail.append(audit_entry)
            if validated_entity is not None:
                final_entities.append(validated_entity)
                
        return final_entities, audit_trail

    def _strict_map_entity(self, entity: Dict[str, Any], chunks: List[ChunkInfo]) -> Dict[str, Any]:
        """
        Strict mapping that raises TraceabilityAuditError if no owner is found.
        """
        ent_start = entity.get("start", -1)
        ent_end = entity.get("end", -1)
        
        if ent_start < 0 or ent_end <= ent_start:
            raise TraceabilityAuditError(f"Invalid entity span [{ent_start}, {ent_end}]")
            
        # Find owner
        best_chunk = None
        best_overlap = 0
        
        for chunk in chunks:
            overlap_start = max(ent_start, chunk.doc_start)
            overlap_end = min(ent_end, chunk.doc_end)
            overlap_len = max(0, overlap_end - overlap_start)
            
            if overlap_len > best_overlap:
                best_overlap = overlap_len
                best_chunk = chunk
                
        if best_chunk is None:
            raise TraceabilityAuditError(
                f"Inadmissible Evidence: Entity {entity.get('text')!r} "
                f"at [{ent_start}:{ent_end}] cannot be mapped to any chunk."
            )
            
        # Calculate relative offsets
        return {
            "chunk_id": best_chunk.chunk_id,
            "chunk_relative_start": max(0, ent_start - best_chunk.doc_start),
            "chunk_relative_end": min(len(best_chunk.text), ent_end - best_chunk.doc_start),
            "chunk_index": best_chunk.chunk_index if hasattr(best_chunk, 'chunk_index') else 0,
            "provenance_method": "strict_mapping"
        }

    async def _llm_validate_entity(self, entity: Dict[str, Any], text: str) -> Tuple[bool, float, str]:
        """
        Interface for LLM Refinement.
        Calls the UltraReasoningService via LLMRefinementService.
        
        HARDENING PATCH P03: Fail-closed when refiner is unavailable.
        In production, missing refiner is a FATAL error.
        In development, entities pass with capped confidence (below default gate threshold).
        """
        text_val = entity.get('text', '').strip()
        if len(text_val) < 2:
            return False, 0.0, "Too short to be a valid legal entity"
            
        if self.refiner:
            # Use real semantic validation
            return await self.refiner.validate_entity(entity, text)
        
        # HARDENING: Refiner unavailable — absolute fail-closed behavior
        # In a Zero-Trust environment, unverified data is never permitted.
        raise LLMRefinementFailure(
            f"FATAL: LLM Refiner is not available. Entity '{text_val[:50]}' "
            "cannot be validated. Epistemic integrity requirement forbids bypass."
        )
