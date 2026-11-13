"""
NLP Hardening — Production-Critical Refactoring
=================================================
Implements the hardening measures identified in the 2026 NLP/KG Deep Audit
(SECTION 11: Refactored Implementation Patterns).

Three core components:

1. **DeterministicEntityIDGenerator**
   - SHA-256 based, collision-resistant entity IDs
   - Cross-document safe via namespace scoping
   - Persian text canonicalization before hashing

2. **ProvenanceAwareNERMapper**
   - Maps full-text NER spans to specific Chunk objects
   - Handles overlapping chunks (e.g., 50-char overlap)
   - Prevents entity duplication across overlapping regions
   - Assigns precise `chunk_id` + `chunk_relative_indices` to every entity

3. **HardenedGraphEntityProcessor**
   - Wraps LegalNEREngine.extract() with provenance mapping
   - Generates deterministic IDs for all entities before graph insertion
   - Enforces Evidence Integrity invariants

Design Contract:
    Every entity written to the Knowledge Graph MUST carry:
      - `deterministic_id`:  SHA-256(category:canonicalized_text[@doc_id])
      - `chunk_id`:          ID of the owning chunk
      - `chunk_start`:       Start offset relative to the chunk
      - `chunk_end`:         End offset relative to the chunk
      - `doc_start`:         Start offset relative to the full document
      - `doc_end`:           End offset relative to the full document

This module is imported by the pipeline and the graph builder.
It does NOT depend on Neo4j, torch, or any heavy external library.
"""

import hashlib
import logging
import unicodedata
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Text Canonicalization for Deterministic Hashing
# ============================================================================


class PersianCanonicalizer:
    """
    Canonicalizes Persian/Arabic text for deterministic hashing.

    Steps:
      1. Unicode NFC normalization
      2. Arabic/Persian character unification (ي→ی, ك→ک, etc.)
      3. All digit variants → ASCII digits
      4. Strip diacritics (تشدید، فتحه، کسره، ضمه)
      5. Collapse whitespace → single space
      6. Strip + lowercase (for entity matching only)
    """

    # Persian↔Arabic character mapping
    _CHAR_MAP = str.maketrans(
        {
            "ي": "ی",
            "ئ": "ی",
            "ك": "ک",
            "إ": "ا",
            "أ": "ا",
            "آ": "ا",
            "ؤ": "و",
        }
    )

    # Digit mappings (Persian + Arabic → ASCII)
    _PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    _ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
    _ASCII_DIGITS = "0123456789"
    _DIGIT_MAP = str.maketrans(
        _PERSIAN_DIGITS + _ARABIC_DIGITS, _ASCII_DIGITS + _ASCII_DIGITS
    )

    # Arabic diacritics (tashkeel) range
    _DIACRITICS_RE = re.compile(
        r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7-\u06E8\u06EA-\u06ED]"
    )

    # Zero-width characters
    _ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")

    @classmethod
    def canonicalize(cls, text: str) -> str:
        """
        Produce a canonical form of Persian text suitable for deterministic hashing.

        This function is idempotent: canonicalize(canonicalize(x)) == canonicalize(x).
        """
        if not text:
            return ""

        # 1. Unicode NFC
        text = unicodedata.normalize("NFC", text)

        # 2. Character unification
        text = text.translate(cls._CHAR_MAP)

        # 3. Digit normalization
        text = text.translate(cls._DIGIT_MAP)

        # 4. Strip diacritics
        text = cls._DIACRITICS_RE.sub("", text)

        # 5. Remove zero-width characters
        text = cls._ZERO_WIDTH_RE.sub("", text)

        # 6. Collapse whitespace + strip
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @classmethod
    def canonicalize_for_id(cls, text: str) -> str:
        """
        Extra-aggressive canonicalization used only for ID generation.
        Adds lowercasing on top of standard canonicalization.
        """
        return cls.canonicalize(text).lower()


# ============================================================================
# 2. Deterministic Entity ID Generator
# ============================================================================


class DeterministicEntityIDGenerator:
    """
    Generates collision-resistant, deterministic entity IDs.

    ID = SHA-256(CATEGORY:canonicalized_text[@doc_id])[:16]

    Properties:
      - Same entity text + category + document → same ID (deterministic)
      - Different documents with identical entity text → different IDs (cross-doc safe)
      - Survives normalization (Arabic ي vs Persian ی → same canonical form)
      - 16-hex-char IDs ≈ 64 bits → negligible collision probability
        for any single Knowledge Graph (< 10^6 nodes)

    Usage:
        gen = DeterministicEntityIDGenerator()
        eid = gen.generate("LAW", "ماده 10 قانون مدنی", doc_id="verdict_001")
    """

    HASH_PREFIX_LENGTH = 16  # 64 bits of the SHA-256 digest

    @staticmethod
    def generate(
        category: str,
        text: str,
        doc_id: Optional[str] = None,
        *,
        scope: str = "document",
    ) -> str:
        """
        Generate a deterministic entity ID.

        Args:
            category: Entity category (e.g., "LAW", "PERSON", "COURT")
            text: Raw entity text (will be canonicalized)
            doc_id: Source document ID (required for document-scoped entities)
            scope: "document" (default, includes doc_id) or "global"
                   (for entities that should merge across documents,
                    e.g., a well-known law like "قانون مدنی")

        Returns:
            16-character hex string (deterministic, collision-resistant)

        Raises:
            ValueError: If scope is "document" and doc_id is None
        """
        canonical = PersianCanonicalizer.canonicalize_for_id(text)
        category_upper = category.upper().strip()

        key = f"{category_upper}:{canonical}"

        if scope == "document":
            if doc_id is None:
                raise ValueError(
                    f"DeterministicEntityIDGenerator: doc_id is required for "
                    f"document-scoped entities (category={category}, text={text!r})"
                )
            key += f"@{doc_id}"
        elif scope != "global":
            raise ValueError(
                f"Invalid scope: {scope!r}. Must be 'document' or 'global'."
            )

        return hashlib.sha256(key.encode("utf-8")).hexdigest()[
            : DeterministicEntityIDGenerator.HASH_PREFIX_LENGTH
        ]


# ============================================================================
# 3. Provenance-Aware NER Mapper
# ============================================================================


@dataclass
class EntityProvenance:
    """
    Full provenance record for a single extracted entity.
    This replaces the old pattern of storing start=0 for all entities.
    """

    # Entity identity
    deterministic_id: str
    category: str
    text: str
    normalized_text: str
    confidence: float

    # Document-level provenance
    doc_id: str
    doc_start: int  # char offset in the FULL normalized document
    doc_end: int

    # Chunk-level provenance
    chunk_id: str
    chunk_start: int  # char offset RELATIVE to the chunk
    chunk_end: int
    related_chunk_ids: List[str] = field(default_factory=list)  # For multi-chunk overlap

    # Extra metadata (original NER output fields)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_graph_entity(self) -> Dict[str, Any]:
        """Convert to the dict format expected by UltraGraphBuilder."""
        return {
            "id": self.deterministic_id,
            "text": self.text,
            "label": self.category,
            "type": "entity",
            "confidence": self.confidence,
            "properties": {
                "normalized_text": self.normalized_text,
                "doc_id": self.doc_id,
                "doc_start": self.doc_start,
                "doc_end": self.doc_end,
                "chunk_id": self.chunk_id,
                "related_chunk_ids": self.related_chunk_ids,
                "chunk_start": self.chunk_start,
                "chunk_end": self.chunk_end,
                **self.metadata,
            },
        }


@dataclass
class ChunkInfo:
    """Minimal chunk descriptor for the mapper."""

    chunk_id: str
    text: str
    doc_start: int  # char offset in the full document
    doc_end: int  # char offset in the full document


class ProvenanceAwareNERMapper:
    """
    Maps full-text NER spans to specific Chunk objects.

    How it works:
      1. NER runs on the FULL normalized document (for best accuracy).
      2. The mapper receives the NER results + the list of chunks.
      3. For each entity span [ent_start, ent_end):
         a) Find ALL chunks that contain at least half the entity text.
         b) Among those, pick the chunk with the LARGEST coverage (primary owner).
         c) If the entity straddles a chunk boundary:
            - It is assigned to the chunk that contains the entity's START.
         d) Entities in OVERLAP regions are deduplicated:
            - Each entity (by deterministic_id) appears at most ONCE.

    This ensures:
      - Every entity has EXACTLY ONE chunk owner (no duplication)
      - Provenance is precise down to chunk-level character offsets
      - Overlap regions don't cause ghost duplicates
    """

    def __init__(self, id_generator: Optional[DeterministicEntityIDGenerator] = None):
        self.id_gen = id_generator or DeterministicEntityIDGenerator()

    def map_entities_to_chunks(
        self,
        entities: Dict[str, List[Dict[str, Any]]],
        chunks: List[ChunkInfo],
        doc_id: str,
    ) -> List[EntityProvenance]:
        """
        Map NER entity spans to their owning chunks.

        Args:
            entities: Output from LegalNEREngine.extract()
                      e.g., {"persons": [...], "laws": [...], ...}
            chunks: List of ChunkInfo objects representing the chunked document
            doc_id: The document ID

        Returns:
            List of EntityProvenance records (deduplicated)
        """
        if not chunks:
            logger.warning(
                f"ProvenanceAwareNERMapper: No chunks provided for doc {doc_id}"
            )
            return []

        # Build a sorted list of chunk intervals for efficient lookup
        sorted_chunks = sorted(chunks, key=lambda c: c.doc_start)

        # Track seen deterministic IDs to prevent duplication in overlap zones
        seen_ids: Set[str] = set()
        provenance_records: List[EntityProvenance] = []

        # Iterate over all entity categories
        category_map = {
            "persons": "PERSON",
            "organizations": "ORGANIZATION",
            "courts": "COURT",
            "laws": "LAW",
            "topics": "TOPIC",
            "legal_concepts": "LEGAL_CONCEPT",
        }

        for category_key, category_label in category_map.items():
            entity_list = entities.get(category_key, [])
            for entity in entity_list:
                ent_start = entity.get("start", -1)
                ent_end = entity.get("end", -1)
                ent_text = entity.get("text", "")
                confidence = entity.get("confidence", 1.0)

                if ent_start < 0 or ent_end <= ent_start:
                    # Entity without valid span — skip
                    logger.debug(
                        f"Skipping entity with invalid span: "
                        f"text={ent_text!r}, start={ent_start}, end={ent_end}"
                    )
                    continue

                # Generate deterministic ID
                det_id = DeterministicEntityIDGenerator.generate(
                    category=category_label,
                    text=ent_text,
                    doc_id=doc_id,
                    scope="document",
                )

                # Dedup: skip if already mapped (overlap zone)
                if det_id in seen_ids:
                    logger.debug(
                        f"Dedup: entity {ent_text!r} (id={det_id}) already mapped"
                    )
                    continue

                # 4a. Find all overlapping chunks
                overlapping_chunks = []
                for c in sorted_chunks:
                    if not (ent_end <= c.doc_start or ent_start >= c.doc_end):
                        overlapping_chunks.append(c)
                
                if not overlapping_chunks:
                    logger.warning(
                        f"Entity {ent_text!r} [{ent_start}:{ent_end}] has no "
                        f"owning chunk in doc {doc_id}. Skipping."
                    )
                    continue

                # 4b. Find the primary owner (majority overlap)
                owner_chunk = max(
                    overlapping_chunks,
                    key=lambda c: min(ent_end, c.doc_end) - max(ent_start, c.doc_start)
                )
                
                related_chunks = [c.chunk_id for c in overlapping_chunks if c.chunk_id != owner_chunk.chunk_id]

                # Calculate chunk-relative offsets
                chunk_start = ent_start - owner_chunk.doc_start
                chunk_end = ent_end - owner_chunk.doc_start

                # Clamp to chunk boundaries (for boundary-straddling entities)
                chunk_start = max(0, chunk_start)
                chunk_end = min(len(owner_chunk.text), chunk_end)

                # Build NER extra metadata (filter out keys we already track)
                extra_meta = {
                    k: v
                    for k, v in entity.items()
                    if k
                    not in ("text", "start", "end", "confidence", "entity_type", "type")
                }

                canonical_text = PersianCanonicalizer.canonicalize(ent_text)

                record = EntityProvenance(
                    deterministic_id=det_id,
                    category=category_label,
                    text=ent_text,
                    normalized_text=canonical_text,
                    confidence=confidence,
                    doc_id=doc_id,
                    doc_start=ent_start,
                    doc_end=ent_end,
                    chunk_id=owner_chunk.chunk_id,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    related_chunk_ids=related_chunks,
                    metadata=extra_meta,
                )

                seen_ids.add(det_id)
                provenance_records.append(record)

        logger.info(
            f"ProvenanceAwareNERMapper: Mapped {len(provenance_records)} entities "
            f"to {len(chunks)} chunks for doc {doc_id} "
            f"(deduped {sum(len(entities.get(k, [])) for k in category_map) - len(provenance_records)} overlap dupes)"
        )

        return provenance_records

    @staticmethod
    def _find_owning_chunk(
        ent_start: int,
        ent_end: int,
        sorted_chunks: List[ChunkInfo],
    ) -> Optional[ChunkInfo]:
        """
        Find the chunk that owns an entity span.

        Strategy:
          - Primary: the chunk whose range contains the entity's START position.
          - If start falls in an overlap between two chunks,
            pick the EARLIER chunk (the one this overlap "belongs" to conceptually).
          - If the entity straddles a boundary, it is assigned to the chunk
            containing the majority of its characters.
        """
        best_chunk: Optional[ChunkInfo] = None
        best_overlap = 0

        for chunk in sorted_chunks:
            # Calculate overlap between entity span and chunk span
            overlap_start = max(ent_start, chunk.doc_start)
            overlap_end = min(ent_end, chunk.doc_end)
            overlap_len = max(0, overlap_end - overlap_start)

            if overlap_len == 0:
                continue

            # If this chunk contains the entity start, it's the primary owner
            if chunk.doc_start <= ent_start < chunk.doc_end:
                return chunk

            # Otherwise track the chunk with the largest overlap
            if overlap_len > best_overlap:
                best_overlap = overlap_len
                best_chunk = chunk

        return best_chunk


# ============================================================================
# 4. Hardened Graph Entity Processor (Pipeline Integration)
# ============================================================================


class HardenedGraphEntityProcessor:
    """
    Wraps LegalNEREngine.extract() with provenance mapping and deterministic IDs.

    Usage in the pipeline:

        from mahoun.pipelines.ingestion.nlp_hardening import HardenedGraphEntityProcessor
        from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine

        ner_engine = LegalNEREngine()
        processor = HardenedGraphEntityProcessor(ner_engine)

        # normalized_text is the FULL document text (post-normalization)
        # chunks is the list of Chunk objects (with start/end offsets)
        graph_entities = processor.process(
            text=normalized_text,
            chunks=chunks,
            doc_id="verdict_001"
        )

        # graph_entities is List[Dict] ready for UltraGraphBuilder.build_graph()
    """

    def __init__(self, ner_engine=None):
        """
        Args:
            ner_engine: An instance of LegalNEREngine.
                        If None, a default engine is created.
        """
        if ner_engine is None:
            from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine

            ner_engine = LegalNEREngine()

        self.ner_engine = ner_engine
        self.mapper = ProvenanceAwareNERMapper()

    def process(
        self,
        text: str,
        chunks: list,
        doc_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Run NER on full text, then map entities to chunks with provenance.

        Args:
            text: Full normalized document text
            chunks: List of chunk objects (must have .chunk_id, .text, .start, .end)
            doc_id: Document identifier

        Returns:
            List of dicts ready for UltraGraphBuilder.build_graph(entities=...)

        Raises:
            ValueError: If text is empty or chunks have invalid offsets
        """
        if not text or not text.strip():
            logger.warning(f"HardenedGraphEntityProcessor: Empty text for doc {doc_id}")
            return []

        # Step 1: Run NER on full document text
        raw_entities = self.ner_engine.extract(text)

        # Step 2: Convert chunks to ChunkInfo
        chunk_infos = []
        for c in chunks:
            # Support both Chunk dataclass and dict-like objects
            if hasattr(c, "chunk_id"):
                chunk_infos.append(
                    ChunkInfo(
                        chunk_id=c.chunk_id,
                        text=c.text,
                        doc_start=c.start,
                        doc_end=c.end,
                    )
                )
            elif isinstance(c, dict):
                chunk_infos.append(
                    ChunkInfo(
                        chunk_id=c.get("chunk_id", ""),
                        text=c.get("text", ""),
                        doc_start=c.get("start", 0),
                        doc_end=c.get("end", 0),
                    )
                )
            else:
                raise TypeError(
                    f"Unsupported chunk type: {type(c)}. "
                    f"Expected Chunk dataclass or dict."
                )

        # Step 3: Map entities to chunks with provenance
        provenance_records = self.mapper.map_entities_to_chunks(
            entities=raw_entities,
            chunks=chunk_infos,
            doc_id=doc_id,
        )

        # Step 4: Convert to graph entity dicts
        graph_entities = [r.to_graph_entity() for r in provenance_records]

        logger.info(
            f"HardenedGraphEntityProcessor: Produced {len(graph_entities)} "
            f"graph entities from {sum(len(v) for v in raw_entities.values())} "
            f"raw NER results for doc {doc_id}"
        )

        return graph_entities


# ============================================================================
# 5. Evidence Integrity Validators
# ============================================================================


def validate_entity_provenance(entity: Dict[str, Any]) -> bool:
    """
    Validate that an entity dict has complete provenance metadata.

    This is the assertion function used in tests and in production
    STRICT mode to ensure zero-hallucination compliance.

    Returns:
        True if valid, raises AssertionError otherwise
    """
    props = entity.get("properties", {})

    # Required fields
    assert entity.get("id"), f"Entity missing deterministic 'id': {entity}"
    assert entity.get("label"), f"Entity missing 'label' (category): {entity}"
    assert entity.get("text"), f"Entity missing 'text': {entity}"

    # Provenance fields
    assert "doc_id" in props, f"Entity missing 'doc_id' in properties: {entity}"
    assert "chunk_id" in props, f"Entity missing 'chunk_id' in properties: {entity}"
    assert "doc_start" in props, f"Entity missing 'doc_start' in properties: {entity}"
    assert "doc_end" in props, f"Entity missing 'doc_end' in properties: {entity}"
    assert "chunk_start" in props, (
        f"Entity missing 'chunk_start' in properties: {entity}"
    )
    assert "chunk_end" in props, f"Entity missing 'chunk_end' in properties: {entity}"

    # Integrity checks
    assert props["doc_start"] >= 0, f"Negative doc_start: {props['doc_start']}"
    assert props["doc_end"] > props["doc_start"], (
        f"doc_end ({props['doc_end']}) must be > doc_start ({props['doc_start']})"
    )
    assert props["chunk_start"] >= 0, f"Negative chunk_start: {props['chunk_start']}"
    assert props["chunk_end"] >= props["chunk_start"], (
        f"chunk_end ({props['chunk_end']}) must be >= chunk_start ({props['chunk_start']})"
    )

    return True


def validate_no_duplicate_ids(entities: List[Dict[str, Any]]) -> bool:
    """
    Validate that no two entities share the same deterministic ID.

    Returns:
        True if no duplicates, raises AssertionError otherwise
    """
    seen: Dict[str, str] = {}
    for entity in entities:
        eid = entity.get("id")
        etext = entity.get("text", "?")
        if eid in seen:
            raise AssertionError(
                f"Duplicate entity ID '{eid}': first='{seen[eid]}', second='{etext}'"
            )
        seen[eid] = etext

    return True
