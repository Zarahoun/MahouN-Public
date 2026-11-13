"""
Canonical Batch Converter
=========================

Converts legacy legal IR (CanonicalLaw, CanonicalArticle, etc.) to
CanonicalIngestionBatch for submission to the canonical API.

This converter:
1. Transforms legacy data structures to canonical format
2. Preserves semantic information (AMENDS/REPEALS/REGULATES)
3. Maintains provenance and source spans
4. Integrates with quality validation
5. Submits through authenticated canonical API
"""

import hashlib
import json
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import requests

from scripts.cli_auth_helper import get_cli_auth_header, get_api_url
from mahoun.graph.ontology.law_registry import (
    CANONICAL_INTER_LAW_LINKS,
    get_law_metadata,
    resolve_cross_law_target,
)
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS

# Quality validation is implemented with custom checks to avoid numpy dependency

logger = logging.getLogger(__name__)


# ============================================================================
# Legacy IR Models (from build_legal_kg.py)
# ============================================================================

@dataclass
class ProvenanceSpan:
    """Provenance span for legal text"""
    source_file: str
    source_line_start: int
    source_line_end: int
    source_char_start: int
    source_char_end: int
    text_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalLaw:
    id: str
    name: str
    raw_text: str
    normalized_text: str
    provenance: ProvenanceSpan


@dataclass
class CanonicalChapter:
    id: str
    law_id: str
    number_or_slug: str
    title: str
    raw_text: str
    normalized_text: str
    order: int
    provenance: ProvenanceSpan


@dataclass
class CanonicalArticle:
    id: str
    law_id: str
    number: str
    raw_text: str
    normalized_text: str
    order: int
    provenance: ProvenanceSpan


@dataclass
class CanonicalClause:
    id: str
    article_id: str
    law_id: str
    clause_type: str
    number: str
    raw_text: str
    normalized_text: str
    order: int
    provenance: ProvenanceSpan


@dataclass
class CanonicalCitation:
    id: str
    source_article_id: str
    target_article_id: str
    citation_type: str  # REFERENCES, AMENDS, REPEALS
    raw_text: str
    provenance: ProvenanceSpan


# ============================================================================
# Canonical API Models
# ============================================================================

@dataclass
class CanonicalSourceSpan:
    source_uri: str
    start: int
    end: int
    text_hash: str


@dataclass
class CanonicalBatchDocument:
    document_id: str
    source_uri: str
    text: str
    provenance: Dict[str, Any]
    metadata: Dict[str, Any]
    parser_version: str
    source_spans: List[CanonicalSourceSpan]
    warnings: List[str]


@dataclass
class CanonicalBatchFact:
    fact_id: str
    subject_id: str
    predicate: str
    object_id: str
    evidence_text: str
    provenance: Dict[str, Any]
    source_spans: List[CanonicalSourceSpan]
    object_type: str


@dataclass
class CanonicalBatchRelationship:
    relationship_id: str
    source_id: str
    relationship_type: str
    target_id: str
    properties: Dict[str, Any]
    provenance: Dict[str, Any]
    source_spans: List[CanonicalSourceSpan]


@dataclass
class CanonicalBatchRequest:
    contract_version: str
    adapter_name: str
    correlation_id: str
    idempotency_key: Optional[str]
    author_id: str
    parser_version: str
    documents: List[CanonicalBatchDocument]
    facts: List[CanonicalBatchFact]
    relationships: List[CanonicalBatchRelationship]
    warnings: List[str]


# ============================================================================
# Converter Implementation
# ============================================================================

class CanonicalBatchConverter:
    """
    Converts legacy legal IR to CanonicalIngestionBatch.

    This converter:
    - Transforms legacy structures to canonical format
    - Preserves semantic types (AMENDS/REPEALS/REGULATES)
    - Maintains provenance and source spans
    - Integrates with quality validation
    """

    def __init__(self, parser_version: str = "1.0", enable_quality_checks: bool = True):
        self.parser_version = parser_version
        self.adapter_name = "IranianLawAdapter"  # Use existing adapter
        self.enable_quality_checks = enable_quality_checks

        if self.enable_quality_checks:
            logger.info("Quality validation enabled")
        else:
            logger.warning("Quality validation disabled")

    def convert_legal_corpus(
        self,
        laws: List[CanonicalLaw],
        chapters: List[CanonicalChapter],
        articles: List[CanonicalArticle],
        clauses: List[CanonicalClause],
        citations: List[CanonicalCitation],
        source_file: str,
        correlation_id: str,
        author_id: str,
        include_semantic_enrichment: bool = False,
    ) -> CanonicalBatchRequest:
        """
        Convert entire legal corpus to canonical governed batch.

        Emits Law Documents plus paired Chapter/Article/Clause/Reference and
        (when enabled) 4-fold Semantic/Deontic/Concept/Inter-Law facts & edges
        compliant with ``GovernedIngestionRuntime.ingest_batch_atomic``.
        """
        logger.info(
            "Converting legal corpus with %d laws, %d articles (semantic=%s)",
            len(laws),
            len(articles),
            include_semantic_enrichment,
        )

        source_uri = f"file://{source_file}"
        documents: List[CanonicalBatchDocument] = []
        facts: List[CanonicalBatchFact] = []
        relationships: List[CanonicalBatchRelationship] = []
        warnings: List[str] = []
        seen_object_ids: set[str] = set()
        law_doc_hashes: Dict[str, str] = {}

        def _bind_provenance(
            raw_prov: Any,
            *,
            source_hash: str,
        ) -> Dict[str, Any]:
            base = self._provenance_to_dict(raw_prov)
            base["source"] = source_uri
            base["source_hash"] = source_hash
            base["correlation_id"] = correlation_id
            base.setdefault("source_file", source_file)
            return base

        # Convert laws to top-level Documents (articles attach via LawArticle facts)
        for law in laws:
            doc = self._convert_law_to_document(law, source_file)
            doc_hash = doc.source_spans[0].text_hash
            doc.provenance = _bind_provenance(law.provenance, source_hash=doc_hash)
            law_doc_hashes[law.id] = doc_hash
            documents.append(doc)

        if not documents:
            for article in articles:
                doc = self._convert_article_to_document(article, source_file)
                doc_hash = doc.source_spans[0].text_hash
                doc.provenance = _bind_provenance(article.provenance, source_hash=doc_hash)
                law_doc_hashes.setdefault(article.law_id, doc_hash)
                documents.append(doc)

        default_doc_hash = (
            documents[0].provenance["source_hash"]
            if documents
            else hashlib.sha256(source_file.encode("utf-8")).hexdigest()
        )

        def _emit_fact_and_rel(
            *,
            object_id: str,
            object_type: str,
            subject_id: str,
            predicate: str,
            evidence_text: str,
            span: CanonicalSourceSpan,
            law_id: str,
            properties: Optional[Dict[str, Any]] = None,
            raw_prov: Any = None,
        ) -> None:
            if object_id in seen_object_ids:
                return
            seen_object_ids.add(object_id)
            clean_evidence = (evidence_text or "").strip() or object_id
            bound_hash = law_doc_hashes.get(law_id, default_doc_hash)
            prov = _bind_provenance(raw_prov, source_hash=bound_hash)
            facts.append(
                CanonicalBatchFact(
                    fact_id=f"fact_{object_id}",
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    evidence_text=clean_evidence,
                    provenance=prov,
                    source_spans=[span],
                    object_type=object_type,
                )
            )
            relationships.append(
                CanonicalBatchRelationship(
                    relationship_id=f"rel_{subject_id}:{object_id}:{predicate}",
                    source_id=subject_id,
                    relationship_type=predicate,
                    target_id=object_id,
                    properties=dict(properties or {}),
                    provenance=prov,
                    source_spans=[span],
                )
            )

        chapter_ids = {ch.id for ch in chapters}
        for chapter in chapters:
            fact = self._convert_chapter_to_fact(chapter, source_file)
            _emit_fact_and_rel(
                object_id=chapter.id,
                object_type="LawChapter",
                subject_id=chapter.law_id,
                predicate="CONTAINS",
                evidence_text=fact.evidence_text,
                span=fact.source_spans[0],
                law_id=chapter.law_id,
                properties={"number_or_slug": chapter.number_or_slug, "title": chapter.title},
                raw_prov=chapter.provenance,
            )

        article_law_map: Dict[str, str] = {}
        doc_ids_set = {doc.document_id for doc in documents}
        for article in articles:
            article_law_map[article.id] = article.law_id
            if article.id in doc_ids_set:
                continue
            art_text = article.normalized_text or article.raw_text
            art_span = self._create_source_span(article.provenance, source_file, art_text)
            ch_id = getattr(article, "chapter_id", None)
            parent_id = ch_id if (ch_id and ch_id in chapter_ids) else article.law_id
            _emit_fact_and_rel(
                object_id=article.id,
                object_type="LawArticle",
                subject_id=parent_id,
                predicate="CONTAINS",
                evidence_text=art_text,
                span=art_span,
                law_id=article.law_id,
                properties={
                    "article_number": article.number,
                    "law_id": article.law_id,
                },
                raw_prov=article.provenance,
            )

        for clause in clauses:
            cf = self._convert_clause_to_fact(clause, source_file)
            _emit_fact_and_rel(
                object_id=clause.id,
                object_type="LawClause",
                subject_id=clause.article_id,
                predicate="CONTAINS",
                evidence_text=cf.evidence_text,
                span=cf.source_spans[0],
                law_id=clause.law_id,
                properties={
                    "clause_type": clause.clause_type,
                    "number": clause.number,
                },
                raw_prov=clause.provenance,
            )

        # Convert citations to paired LawReference facts + Relationships (preserve semantic types)
        for cit_idx, citation in enumerate(citations, start=1):
            rel = self._convert_citation_to_relationship(citation, source_file)
            cit_hash = self._citation_id(citation)
            ref_id = f"{citation.source_article_id}:ref:{cit_hash}:{cit_idx}"
            cit_law_id = article_law_map.get(citation.source_article_id, laws[0].id if laws else "")
            evidence = (
                getattr(citation, "raw_text", None)
                or getattr(citation, "citation_text", None)
                or rel.properties.get("citation_text", "")
                or citation.target_article_id
            )
            props = {
                **rel.properties,
                "target_article_id": rel.target_id,
                "target_clause_id": getattr(citation, "target_clause_id", None),
                "target_clause_ref": getattr(citation, "target_clause_ref", None),
                "status": getattr(citation, "status", "RESOLVED"),
            }
            _emit_fact_and_rel(
                object_id=ref_id,
                object_type="LawReference",
                subject_id=citation.source_article_id,
                predicate=rel.relationship_type,
                evidence_text=evidence,
                span=rel.source_spans[0],
                law_id=cit_law_id,
                properties=props,
                raw_prov=getattr(citation, "provenance", None),
            )

        if include_semantic_enrichment:
            self._append_4fold_enrichment(
                laws=laws,
                articles=articles,
                source_file=source_file,
                emit_fn=_emit_fact_and_rel,
            )

        self._bind_canonical_document_spans(
            documents=documents,
            chapters=chapters,
            articles=articles,
            clauses=clauses,
            facts=facts,
            relationships=relationships,
            source_uri=source_uri,
            source_file=source_file,
        )

        batch_request = CanonicalBatchRequest(
            contract_version="1",
            adapter_name=self.adapter_name,
            correlation_id=correlation_id,
            idempotency_key=f"{source_file}_{correlation_id}",
            author_id=author_id,
            parser_version=self.parser_version,
            documents=documents,
            facts=facts,
            relationships=relationships,
            warnings=warnings,
        )

        logger.info(
            "Converted to %d documents, %d facts, %d relationships",
            len(documents),
            len(facts),
            len(relationships),
        )

        if self.enable_quality_checks:
            self._validate_batch_quality(batch_request)

        return batch_request

    def _append_4fold_enrichment(
        self,
        *,
        laws: List[CanonicalLaw],
        articles: List[CanonicalArticle],
        source_file: str,
        emit_fn: Any,
    ) -> None:
        """Append deterministic Semantic/Deontic/Concept & Inter-Law facts to batch."""
        from mahoun.graph.extraction.batched_semantic_materializer import (
            BatchedSemanticMaterializer,
        )
        from mahoun.graph.extraction.semantic_extractor import SemanticExtractor

        extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)
        materializer = BatchedSemanticMaterializer(ontology=CANONICAL_LEGAL_CONCEPTS)
        decompositions = []
        raw_assertions = []
        unit_law_map: Dict[str, str] = {}
        unit_prov_map: Dict[str, Any] = {}

        for art in articles:
            art_text = art.normalized_text or art.raw_text or ""
            unit_law_map[art.id] = art.law_id
            unit_prov_map[art.id] = art.provenance
            if art_text.strip():
                decompositions.append(
                    extractor.decompose_article(
                        article_id=art.id,
                        law_id=art.law_id,
                        raw_text=art_text,
                    )
                )
                raw_assertions.extend(
                    extractor.extract_concept_assertions(
                        article_id=art.id,
                        raw_text=art_text,
                    )
                )
            for clause in getattr(art, "clauses", []) or []:
                clause_text = clause.normalized_text or clause.raw_text or ""
                if not clause_text.strip():
                    continue
                unit_law_map[clause.id] = art.law_id
                unit_prov_map[clause.id] = clause.provenance
                decompositions.append(
                    extractor.decompose_article(
                        article_id=clause.id,
                        law_id=art.law_id,
                        raw_text=clause_text,
                    )
                )
                raw_assertions.extend(
                    extractor.extract_concept_assertions(
                        article_id=clause.id,
                        raw_text=clause_text,
                    )
                )

        for decomp in decompositions:
            unit_id = decomp.article_id
            unit_law_id = unit_law_map.get(unit_id, decomp.law_id)
            unit_prov = unit_prov_map.get(unit_id)

            for idx, cond in enumerate(decomp.conditions, start=1):
                c_text = cond.condition_text
                span = self._create_source_span(unit_prov, source_file, c_text)
                emit_fn(
                    object_id=f"{unit_id}:condition:{idx}",
                    object_type="LegalCondition",
                    subject_id=unit_id,
                    predicate="HAS_CONDITION",
                    evidence_text=c_text,
                    span=span,
                    law_id=unit_law_id,
                    properties={"condition_id": cond.id, "trigger_keyword": cond.trigger_keyword},
                    raw_prov=unit_prov,
                )

            for idx, exc in enumerate(decomp.exceptions, start=1):
                e_text = exc.exception_text
                span = self._create_source_span(unit_prov, source_file, e_text)
                emit_fn(
                    object_id=f"{unit_id}:exception:{idx}",
                    object_type="LegalException",
                    subject_id=unit_id,
                    predicate="HAS_EXCEPTION",
                    evidence_text=e_text,
                    span=span,
                    law_id=unit_law_id,
                    properties={"exception_id": exc.id, "trigger_keyword": exc.trigger_keyword},
                    raw_prov=unit_prov,
                )

            for idx, sanc in enumerate(decomp.sanctions, start=1):
                s_text = sanc.sanction_text
                span = self._create_source_span(unit_prov, source_file, s_text)
                emit_fn(
                    object_id=f"{unit_id}:sanction:{idx}",
                    object_type="LegalSanction",
                    subject_id=unit_id,
                    predicate="HAS_SANCTION",
                    evidence_text=s_text,
                    span=span,
                    law_id=unit_law_id,
                    properties={"sanction_id": sanc.id, "sanction_type": sanc.sanction_type},
                    raw_prov=unit_prov,
                )

            deontic_map = {
                "OBLIGATION": ("LegalObligation", "HAS_OBLIGATION"),
                "PROHIBITION": ("LegalProhibition", "HAS_PROHIBITION"),
                "PERMISSION": ("LegalPermission", "HAS_PERMISSION"),
                "RIGHT": ("LegalRight", "HAS_RIGHT"),
            }
            for idx, norm in enumerate(getattr(decomp, "deontic_norms", []) or [], start=1):
                d_key = getattr(norm.norm_type, "value", str(norm.norm_type)).upper()
                if d_key not in deontic_map:
                    continue
                obj_type, pred = deontic_map[d_key]
                n_text = norm.norm_text
                span = self._create_source_span(unit_prov, source_file, n_text)
                emit_fn(
                    object_id=f"{unit_id}:{d_key.lower()}:{idx}",
                    object_type=obj_type,
                    subject_id=unit_id,
                    predicate=pred,
                    evidence_text=n_text,
                    span=span,
                    law_id=unit_law_id,
                    properties={"deontic_operator": d_key, "trigger_keyword": norm.trigger_keyword},
                    raw_prov=unit_prov,
                )

        accepted = materializer.accept_extracted_assertions(
            raw_assertions,
            decompositions=decompositions,
            extractor=extractor,
        )
        for idx, assertion in enumerate(accepted, start=1):
            unit_id = assertion.source_entity_id
            unit_law_id = unit_law_map.get(unit_id, "")
            unit_prov = unit_prov_map.get(unit_id)
            ev = assertion.evidence_text_span or assertion.target_entity_id
            span = self._create_source_span(unit_prov, source_file, ev)
            slug = assertion.target_entity_id.replace(":", "_")
            emit_fn(
                object_id=f"{unit_id}:concept:{slug}:{idx}",
                object_type="LegalConcept",
                subject_id=unit_id,
                predicate="REGULATES",
                evidence_text=ev,
                span=span,
                law_id=unit_law_id,
                properties={
                    "citation_type": "REGULATES",
                    "concept_id": assertion.target_entity_id,
                    "confidence": float(getattr(assertion, "confidence_score", 1.0) or 1.0),
                    "verification_method": assertion.verification_method,
                },
                raw_prov=unit_prov,
            )

        law_map = {law.id: law for law in laws}
        for idx, link in enumerate(CANONICAL_INTER_LAW_LINKS, start=1):
            if link.source_law_id not in law_map:
                continue
            src_law = law_map[link.source_law_id]
            ev = f"{link.source_law_id} {link.relationship_type} {link.target_law_id}"
            span = self._create_source_span(src_law.provenance, source_file, ev)
            emit_fn(
                object_id=f"{link.source_law_id}:interlaw:{link.target_law_id}:{link.relationship_type}:{idx}",
                object_type="LawReference",
                subject_id=link.source_law_id,
                predicate=link.relationship_type,
                evidence_text=ev,
                span=span,
                law_id=link.source_law_id,
                properties={
                    **dict(link.properties),
                    "target_law_id": link.target_law_id,
                    "citation_type": link.relationship_type,
                },
                raw_prov=src_law.provenance,
            )

    @staticmethod
    def _bind_canonical_document_spans(
        *,
        documents: List[CanonicalBatchDocument],
        chapters: List[CanonicalChapter],
        articles: List[CanonicalArticle],
        clauses: List[CanonicalClause],
        facts: List[CanonicalBatchFact],
        relationships: List[CanonicalBatchRelationship],
        source_uri: str,
        source_file: str,
    ) -> None:
        """Align every fact/relationship SourceSpan with the canonical document text."""
        if not documents:
            return

        chunks: List[str] = []
        total_len = 0
        unit_scopes: Dict[str, tuple[int, str]] = {}
        placed_text: Dict[str, tuple[int, int, str]] = {}

        def _append_chunk(text: str) -> tuple[int, str]:
            nonlocal total_len
            sep = 1 if chunks else 0
            start = total_len + sep
            chunks.append(text)
            total_len = start + len(text)
            if text not in placed_text:
                placed_text[text] = (
                    start,
                    start + len(text),
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )
            return start, text

        for doc in documents:
            t = (doc.text or "").strip()
            if t and t not in placed_text:
                _append_chunk(t)

        for chapter in chapters:
            t = (chapter.title or "").strip()
            if not t:
                continue
            if t in placed_text:
                s, _, _ = placed_text[t]
                unit_scopes[chapter.id] = (s, t)
            else:
                unit_scopes[chapter.id] = _append_chunk(t)

        for article in articles:
            t = (article.normalized_text or article.raw_text or "").strip()
            if not t:
                continue
            if t in placed_text:
                s, _, _ = placed_text[t]
                unit_scopes[article.id] = (s, t)
            else:
                unit_scopes[article.id] = _append_chunk(t)

        for clause in clauses:
            t = (clause.normalized_text or clause.raw_text or "").strip()
            if not t:
                continue
            parent_scope = unit_scopes.get(clause.article_id)
            if parent_scope is not None:
                p_start, p_text = parent_scope
                local_idx = p_text.find(t)
                if local_idx >= 0:
                    unit_scopes[clause.id] = (p_start + local_idx, t)
                    continue
            if t in placed_text:
                s, _, _ = placed_text[t]
                unit_scopes[clause.id] = (s, t)
            else:
                unit_scopes[clause.id] = _append_chunk(t)

        for idx, fact in enumerate(facts):
            needle = (fact.evidence_text or "").strip() or fact.object_id
            fact.evidence_text = needle
            scope = unit_scopes.get(fact.subject_id)
            span_coords: Optional[tuple[int, int, str]] = None
            if scope is not None:
                s_offset, s_text = scope
                local_idx = s_text.find(needle)
                if local_idx >= 0:
                    span_start = s_offset + local_idx
                    span_end = span_start + len(needle)
                    span_coords = (
                        span_start,
                        span_end,
                        hashlib.sha256(needle.encode("utf-8")).hexdigest(),
                    )
            if span_coords is None:
                span_coords = placed_text.get(needle)
            if span_coords is None:
                chunk_start, _ = _append_chunk(needle)
                span_coords = placed_text[needle]
            span = CanonicalSourceSpan(
                source_uri=source_uri,
                start=span_coords[0],
                end=span_coords[1],
                text_hash=span_coords[2],
            )
            fact.source_spans = [span]
            if idx < len(relationships):
                relationships[idx].source_spans = [span]

        if not chunks:
            _append_chunk(source_file or "legal-corpus")

        full_doc_text = "\n".join(chunks)
        doc_hash = hashlib.sha256(full_doc_text.encode("utf-8")).hexdigest()
        full_span = CanonicalSourceSpan(
            source_uri=source_uri,
            start=0,
            end=len(full_doc_text),
            text_hash=doc_hash,
        )
        for doc in documents:
            doc.text = full_doc_text
            doc.provenance["source_hash"] = doc_hash
            doc.source_spans = [full_span]
        for fact in facts:
            fact.provenance["source_hash"] = doc_hash
        for rel in relationships:
            rel.provenance["source_hash"] = doc_hash

    def _convert_law_to_document(self, law: CanonicalLaw, source_file: str) -> CanonicalBatchDocument:
        """Convert CanonicalLaw to CanonicalBatchDocument."""
        source_span = self._create_source_span(law.provenance, source_file, law.normalized_text)
        law_meta = get_law_metadata(law.id) or {}
        metadata = {
            "law_id": law.id,
            "law_name": law.name,
            "document_type": "Law",
        }
        for key in ("title", "enactment_date", "hierarchy_level", "specificity_level"):
            if key in law_meta and law_meta[key] is not None:
                metadata[key] = law_meta[key]

        return CanonicalBatchDocument(
            document_id=law.id,
            source_uri=f"file://{source_file}",
            text=law.normalized_text,
            provenance=self._provenance_to_dict(law.provenance),
            metadata=metadata,
            parser_version=self.parser_version,
            source_spans=[source_span],
            warnings=[]
        )

    def _convert_article_to_document(self, article: CanonicalArticle, source_file: str) -> CanonicalBatchDocument:
        """Convert CanonicalArticle to CanonicalBatchDocument."""
        source_span = self._create_source_span(article.provenance, source_file, article.normalized_text)

        return CanonicalBatchDocument(
            document_id=article.id,
            source_uri=f"file://{source_file}",
            text=article.normalized_text,
            provenance=self._provenance_to_dict(article.provenance),
            metadata={
                "article_id": article.id,
                "law_id": article.law_id,
                "article_number": article.number,
                "document_type": "Article"
            },
            parser_version=self.parser_version,
            source_spans=[source_span],
            warnings=[]
        )

    def _convert_chapter_to_fact(self, chapter: CanonicalChapter, source_file: str) -> CanonicalBatchFact:
        """Convert CanonicalChapter to CanonicalBatchFact (Law → HAS_CHAPTER → Chapter)."""
        source_span = self._create_source_span(chapter.provenance, source_file, chapter.title)

        return CanonicalBatchFact(
            fact_id=f"fact_{chapter.id}",
            subject_id=chapter.law_id,
            predicate="HAS_CHAPTER",
            object_id=chapter.id,
            evidence_text=chapter.title,
            provenance=self._provenance_to_dict(chapter.provenance),
            source_spans=[source_span],
            object_type="LawChapter"
        )

    def _convert_clause_to_fact(self, clause: CanonicalClause, source_file: str) -> CanonicalBatchFact:
        """Convert CanonicalClause to CanonicalBatchFact (Article → HAS_CLAUSE → Clause)."""
        source_span = self._create_source_span(clause.provenance, source_file, clause.normalized_text)

        return CanonicalBatchFact(
            fact_id=f"fact_{clause.id}",
            subject_id=clause.article_id,
            predicate="HAS_CLAUSE",
            object_id=clause.id,
            evidence_text=clause.normalized_text,
            provenance=self._provenance_to_dict(clause.provenance),
            source_spans=[source_span],
            object_type="LawClause"
        )

    def _convert_citation_to_relationship(self, citation: CanonicalCitation, source_file: str) -> CanonicalBatchRelationship:
        """
        Convert CanonicalCitation to CanonicalBatchRelationship.

        CRITICAL: Preserve semantic types (AMENDS/REPEALS/REGULATES).
        Do NOT convert everything to REFERENCES.
        """
        citation_text = getattr(citation, "raw_text", None) or getattr(citation, "citation_text", "")
        source_span = self._create_source_span(
            getattr(citation, "provenance", None),
            source_file,
            citation_text,
        )

        # Map citation types to relationship types
        # Preserve original semantic types
        relationship_type_mapping = {
            "REFERENCES": "REFERENCES",
            "AMENDS": "AMENDS",
            "REPEALS": "REPEALS",
            "REGULATES": "REGULATES"
        }

        relationship_type = relationship_type_mapping.get(
            citation.citation_type,
            "REFERENCES"  # Default to REFERENCES if unknown
        )

        resolved_target = resolve_cross_law_target(citation.target_article_id)
        rel_props = {
            "citation_text": citation_text,
            "citation_type": citation.citation_type,
        }
        if resolved_target != citation.target_article_id:
            rel_props["redirected_from"] = citation.target_article_id

        return CanonicalBatchRelationship(
            relationship_id=f"rel_{self._citation_id(citation)}",
            source_id=citation.source_article_id,
            relationship_type=relationship_type,
            target_id=resolved_target,
            properties=rel_props,
            provenance=self._provenance_to_dict(getattr(citation, "provenance", None)),
            source_spans=[source_span]
        )

    @staticmethod
    def _provenance_to_dict(provenance: Any) -> Dict[str, Any]:
        """Normalize provenance objects from both canonical and legacy IR models."""
        if provenance is None:
            return {}
        to_dict = getattr(provenance, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return dict(result)
            raise TypeError(f"Provenance to_dict() returned {type(result).__name__}")
        if hasattr(provenance, "__dataclass_fields__"):
            return asdict(provenance)
        if isinstance(provenance, dict):
            return dict(provenance)
        raise TypeError(f"Unsupported provenance type: {type(provenance).__name__}")

    @staticmethod
    def _citation_id(citation: Any) -> str:
        """Return a stable ID for canonical and legacy citation models."""
        explicit_id = getattr(citation, "id", None)
        if explicit_id:
            return explicit_id
        citation_text = getattr(citation, "raw_text", None) or getattr(citation, "citation_text", "")
        payload = "|".join(
            (
                citation.source_article_id,
                citation.target_article_id,
                citation.citation_type,
                citation_text,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _create_source_span(
        self,
        provenance: Any,
        source_file: str,
        fallback_text: str = "",
    ) -> CanonicalSourceSpan:
        """Create CanonicalSourceSpan from ProvenanceSpan."""
        if provenance is None:
            return CanonicalSourceSpan(
                source_uri=f"file://{source_file}",
                start=0,
                end=len(fallback_text),
                text_hash=hashlib.sha256(fallback_text.encode("utf-8")).hexdigest(),
            )
        return CanonicalSourceSpan(
            source_uri=f"file://{source_file}",
            start=provenance.source_char_start,
            end=provenance.source_char_end,
            text_hash=provenance.text_hash
        )

    def _validate_batch_quality(self, batch_request: CanonicalBatchRequest) -> None:
        """
        Validate batch quality using custom checks.

        This performs:
        - Completeness checks (missing required fields)
        - Consistency checks (duplicate IDs)
        - Provenance validation (hash consistency)
        - Semantic type validation (AMENDS/REPEALS/REGULATES preservation)

        Raises:
            RuntimeError: If critical quality validation fails
        """
        logger.info("🔍 Running quality validation...")

        issues = []
        warnings = []

        # Check 1: Document completeness
        for doc in batch_request.documents:
            if not doc.document_id or not doc.text or not doc.source_uri:
                issues.append(f"Document missing required fields: {doc.document_id}")

        # Check 2: Fact completeness
        for fact in batch_request.facts:
            if not fact.fact_id or not fact.subject_id or not fact.object_id:
                issues.append(f"Fact missing required fields: {fact.fact_id}")

        # Check 3: Relationship completeness
        for rel in batch_request.relationships:
            if not rel.relationship_id or not rel.source_id or not rel.target_id:
                issues.append(f"Relationship missing required fields: {rel.relationship_id}")

        # Check 4: Duplicate IDs
        all_ids = []
        all_ids.extend([doc.document_id for doc in batch_request.documents])
        all_ids.extend([fact.fact_id for fact in batch_request.facts])
        all_ids.extend([rel.relationship_id for rel in batch_request.relationships])

        duplicate_ids = [id for id in all_ids if all_ids.count(id) > 1]
        if duplicate_ids:
            warnings.append(f"Found {len(set(duplicate_ids))} duplicate IDs")

        # Check 5: Semantic type preservation (CRITICAL)
        citation_types = [rel.properties.get("citation_type") for rel in batch_request.relationships]
        semantic_types = [ct for ct in citation_types if ct in ["AMENDS", "REPEALS", "REGULATES"]]
        if semantic_types:
            logger.info(f"✅ Preserved {len(semantic_types)} semantic relationship types: {set(semantic_types)}")
        else:
            warnings.append("No AMENDS/REPEALS/REGULATES relationships found")

        # Check 6: Provenance hash consistency
        for doc in batch_request.documents:
            for span in doc.source_spans:
                if len(span.text_hash) != 64:  # SHA-256 should be 64 chars
                    issues.append(f"Invalid hash length in document {doc.document_id}")

        # Report results
        if issues:
            logger.error(f"❌ Quality validation failed with {len(issues)} critical issues:")
            for issue in issues[:10]:  # Show first 10 issues
                logger.error(f"  - {issue}")
            raise RuntimeError(f"Quality validation failed: {len(issues)} critical issues")

        if warnings:
            logger.warning(f"⚠️ Quality validation completed with {len(warnings)} warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")

        logger.info("✅ Quality validation passed")

    def submit_to_api(self, batch_request: CanonicalBatchRequest) -> Dict[str, Any]:
        """
        Submit canonical batch to the API.

        Args:
            batch_request: CanonicalBatchRequest to submit

        Returns:
            API response data

        Raises:
            RuntimeError: If submission fails
        """
        api_url = get_api_url()
        endpoint = f"{api_url}/api/v1/ingest/canonical-batch"

        # Get authentication header
        auth_header = get_cli_auth_header()
        if not auth_header:
            raise RuntimeError("Cannot authenticate with API. Ensure CLI token is available.")

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "X-Correlation-ID": batch_request.correlation_id,
        }

        # Convert to JSON
        batch_data = {
            "contract_version": batch_request.contract_version,
            "adapter_name": batch_request.adapter_name,
            "correlation_id": batch_request.correlation_id,
            "idempotency_key": batch_request.idempotency_key,
            "author_id": batch_request.author_id,
            "parser_version": batch_request.parser_version,
            "documents": [asdict(doc) for doc in batch_request.documents],
            "facts": [asdict(fact) for fact in batch_request.facts],
            "relationships": [asdict(rel) for rel in batch_request.relationships],
            "warnings": batch_request.warnings
        }

        try:
            response = requests.post(endpoint, json=batch_data, headers=headers, timeout=120)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Canonical batch submitted successfully: {result}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to submit canonical batch: {e}")
            raise RuntimeError(f"API submission failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during API submission: {e}")
            raise