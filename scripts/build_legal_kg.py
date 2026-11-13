#!/usr/bin/env python3
"""
MAHOUN Hardened Legal Corpus Compiler & Knowledge Graph Ingestion Engine
=======================================================================
Phase 1: Deterministic, Idempotent, Provenance-Preserving Graph Compiler.

Features:
- Pre-ingestion Source Dataset Integrity (SHA-256 attestation)
- Deterministic Persian Legal Normalization & Exact Span Provenance
- Strict Parser with Complete Line Accounting & Fail-Closed DLQ
- Hierarchical Directed Legal Topology: (Law)->(Chapter)->(Article)->(Clause)
- Referential Integrity with Deterministic Unresolved Placeholders
- Non-Mutating Re-Ingestion (Identity Idempotency without State Pollution)
- Transaction-Bounded Batching via APOC & Ingestion Run Manifest
- Post-Ingestion Forensic Integrity Audit & Cryptographic Graph Fingerprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import ast
import asyncio
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

# MahouN Canonical Imports
from mahoun.core.governance.mutation_boundary import GovernedNeo4jSession  # noqa: F401
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
from mahoun.core.governance.mutation_boundary import (
    classify_cypher,
    get_audit_sink,
    set_audit_sink,
)
from mahoun.core.governance.validator_pipeline import ValidatorPipeline
from mahoun.core.models import LegalInstrumentType
from mahoun.graph.extraction.batched_semantic_materializer import (
    BatchedSemanticMaterializer,
)
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
from mahoun.graph.neo4j.connection import get_connection
from mahoun.graph.ontology.law_registry import (
    CANONICAL_INTER_LAW_LINKS,
    KNOWN_CROSS_LAW_REDIRECTS,
    derive_law_id_from_node_id,
    get_law_metadata,
    iter_all_law_metadata,
    resolve_cross_law_target,
    resolve_law_id_from_text_span,
)
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink
from mahoun.guardrails.ultra_citation_auditor import CitationExtractor
from mahoun.nlp.ultra_persian_legal_nlp import PersianNormalizer

logger = logging.getLogger("build_legal_kg")

PARSER_VERSION = "2.0.0"
SCHEMA_VERSION = "1.0.0"


class CanonicalIdentityCollision(Exception):
    """Raised when an Article or entity canonical ID collides with an existing one in the same corpus."""
    pass


CONSTITUTION_ORDINALS = {
    "اول": 1, "یکم": 1, "دوم": 2, "سوم": 3, "چهارم": 4, "پنجم": 5, "ششم": 6, "هفتم": 7,
    "هشتم": 8, "نهم": 9, "دهم": 10, "یازدهم": 11, "دوازدهم": 12, "سیزدهم": 13,
    "چهاردهم": 14, "پانزدهم": 15, "شانزدهم": 16, "هفدهم": 17, "هجدهم": 18, "نوزدهم": 19,
}
PERSIAN_TENS = {
    "بیست": 20, "بیستم": 20, "سی": 30, "سی‌ام": 30, "سیام": 30, "سیم": 30,
    "چهل": 40, "چهلم": 40, "پنجاه": 50, "پنجاهم": 50, "شصت": 60, "شصتم": 60,
    "هفتاد": 70, "هفتادم": 70, "هشتاد": 80, "هشتادم": 80, "نود": 90, "نودم": 90,
}
PERSIAN_HUNDREDS = {"صد": 100, "صدم": 100, "یکصد": 100, "یکصدم": 100}


def parse_constitution_principle(text: str) -> Optional[int]:
    """Parse Persian ordinal principle numbers (1 to 177) from Constitution lines."""
    m = re.match(r"^اصل\s+([^\n\(–\-:]+)", text)
    if not m:
        return None
    raw_words_str = m.group(1).strip()
    t = raw_words_str.replace("\u200c", " ")
    t = re.sub(r"\bو([^\s]+)", r"و \1", t)
    words = [w.strip() for w in t.split() if w.strip() and w.strip() != "و"]
    val = 0
    i = 0
    while i < len(words):
        w = words[i]
        if w in PERSIAN_HUNDREDS:
            val += PERSIAN_HUNDREDS[w]
            i += 1
        elif w in PERSIAN_TENS:
            val += PERSIAN_TENS[w]
            i += 1
        elif w in CONSTITUTION_ORDINALS:
            val += CONSTITUTION_ORDINALS[w]
            i += 1
        else:
            break
    return val if val > 0 else None


AGGREGATE_SEGMENTS = [
    (1, 478, "constitution", "قانون اساسی جمهوری اسلامی ایران", LegalInstrumentType.CONSTITUTIONAL_LAW),
    (479, 534, "commercial_code_1311", "قانون تجارت مصوب ۱۳۱۱", LegalInstrumentType.STATUTE),
    (535, 1175, "commercial_amendment_1347", "لایحه قانونی اصلاح قسمتی از قانون تجارت مصوب ۱۳۴۷", LegalInstrumentType.STATUTE),
    (1176, 1929, "commercial_code_1311", "قانون تجارت مصوب ۱۳۱۱ (ادامه)", LegalInstrumentType.STATUTE),
    (1930, 3607, "criminal_procedure_1392", "قانون آیین دادرسی کیفری مصوب ۱۳۹۲", LegalInstrumentType.STATUTE),
    (3608, 4793, "civil_procedure_1379", "قانون آیین دادرسی دادگاه‌های عمومی و انقلاب در امور مدنی مصوب ۱۳۷۹", LegalInstrumentType.STATUTE),
    (4794, 6576, "civil_code", "قانون مدنی", LegalInstrumentType.STATUTE),
    (6577, 8139, "penal_code_1392", "قانون مجازات اسلامی مصوب ۱۳۹۲", LegalInstrumentType.STATUTE),
    (8140, 8640, "penal_code_tazirat_1375", "کتاب پنجم قانون مجازات اسلامی (تعزیرات و مجازات‌های بازدارنده) مصوب ۱۳۷۵", LegalInstrumentType.STATUTE),
]


# ============================================================================
# 1. Deterministic Normalizer & Text Helpers
# ============================================================================

class DeterministicLegalNormalizer:
    """
    Two-tier normalizer:
    1. Preserves raw_text exactly for forensic SHA-256 calculation.
    2. Generates normalized_text for deterministic parsing & pattern matching.
    """

    def __init__(self):
        self._nlp_normalizer = PersianNormalizer()
        self._persian_to_ascii_digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

    def normalize_digits(self, text: str) -> str:
        """Convert Persian and Arabic numerals to ASCII digits."""
        return text.translate(self._persian_to_ascii_digits)

    def normalize(self, text: str) -> str:
        """
        Deterministic Unicode, ZWNJ, Arabic character, and digit normalization.
        """
        if not text:
            return ""
        text = self.normalize_digits(text)
        text = self._nlp_normalizer.normalize(text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        return text

    @staticmethod
    def compute_sha256(text: str) -> str:
        """Compute SHA-256 of raw text block."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================================
# 2. Canonical Data Structures (IR)
# ============================================================================

@dataclass
class ProvenanceSpan:
    source_file: str
    source_line_start: int
    source_line_end: int
    source_char_start: int
    source_char_end: int
    text_hash: str
    parser_version: str = PARSER_VERSION
    schema_version: str = SCHEMA_VERSION


def build_source_manifest(source_path: Path) -> Dict[str, Any]:
    """Build a deterministic manifest for a UTF-8 source document.

    The manifest is deliberately independent from Neo4j so it can be reviewed
    and attested during dry-run before any governed materialization.
    """
    valid, source_sha256, line_count, error = verify_source_file(source_path)
    if not valid:
        raise ValueError(error or f"Invalid source file: {source_path}")
    raw_bytes = source_path.read_bytes()
    text = raw_bytes.decode("utf-8")
    return {
        "source_id": f"file:{source_sha256}",
        "source_file": str(source_path),
        "source_sha256": source_sha256,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "byte_count": len(raw_bytes),
        "line_count": line_count,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def validate_provenance_span(provenance: ProvenanceSpan, raw_text: str) -> None:
    """Fail closed when a parsed span no longer matches its evidence."""
    if not raw_text:
        raise ValueError("Provenance span text must not be empty")
    expected_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    if provenance.text_hash != expected_hash:
        raise ValueError(
            "Provenance span hash mismatch: "
            f"expected={expected_hash}, actual={provenance.text_hash}"
        )
    if provenance.source_line_start < 1:
        raise ValueError("Provenance source_line_start must be positive")
    if provenance.source_line_end < provenance.source_line_start:
        raise ValueError("Provenance source line interval is reversed")
    if provenance.source_char_end < provenance.source_char_start:
        raise ValueError("Provenance source character interval is reversed")


@dataclass
class CanonicalLaw:
    id: str
    name: str
    raw_text: str
    normalized_text: str
    provenance: ProvenanceSpan
    instrument_type: LegalInstrumentType = LegalInstrumentType.STATUTE


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
class CanonicalClause:
    id: str
    article_id: str
    law_id: str
    clause_type: str  # 'note' (تبصره) | 'item' (بند) | 'paragraph'
    number: str
    raw_text: str
    normalized_text: str
    order: int
    provenance: ProvenanceSpan


@dataclass
class CanonicalArticle:
    id: str
    law_id: str
    chapter_id: str
    number: str
    raw_text: str
    normalized_text: str
    status: str  # 'resolved' | 'unresolved'
    clauses: List[CanonicalClause] = field(default_factory=list)
    amendment_info: Optional[str] = None
    provenance: Optional[ProvenanceSpan] = None


@dataclass
class CanonicalCitation:
    source_article_id: str
    target_article_id: str
    citation_text: str
    citation_type: str  # 'REFERENCES' | 'AMENDS' | 'REPEALS'
    status: str  # 'RESOLVED' | 'UNRESOLVED' | 'AMBIGUOUS'
    raw_target_number: Optional[str] = None
    target_law_id: Optional[str] = None
    target_clause_id: Optional[str] = None
    target_clause_ref: Optional[str] = None
    redirected_from: Optional[str] = None


# Persian legal citation semantics: a cited article may not be a plain
# cross-reference — the citing article can amend or repeal it.  Triggers are
# matched on the legal verb, tolerant of ZWNJ (U+200C) and of the normalizer
# collapsing it, so classification is deterministic across typographies.
_AMENDS_CONTEXT_PATTERN = re.compile(
    r"اصلاح\s*می[\u200c\s]?(?:شود|گردد|کند)"
    r"|اصلاح\s*نموده"
    r"|جایگزین\s*می[\u200c\s]?(?:شود|گردد)"
)
_REPEALS_CONTEXT_PATTERN = re.compile(
    r"(?:نسخ|لغو|ابطال)\s*می[\u200c\s]?(?:شود|گردد|کند)"
    r"|ملغی\s*(?:است|می[\u200c\s]?(?:شود|گردد|کند)|اعلام)"
)

# Deterministic classification window: bounded by the next citation match so a
# later reference's triggers cannot leak into an earlier reference's type.
CITATION_CONTEXT_WINDOW_CHARS = 250


@dataclass
class LineClassificationRecord:
    source_line_index: int
    classification: str  # 'RECOGNIZED_ENTITY' | 'RECOGNIZED_METADATA' | 'IGNORABLE_FORMATTING' | 'UNPARSED' | 'INVALID'
    raw_text: str
    failure_reason: Optional[str] = None


@dataclass
class IngestionStats:
    total_lines: int = 0
    recognized_entity_lines: int = 0
    recognized_metadata_lines: int = 0
    ignorable_formatting_lines: int = 0
    unparsed_lines: int = 0
    invalid_lines: int = 0

    laws_count: int = 0
    chapters_count: int = 0
    articles_count: int = 0
    clauses_count: int = 0

    resolved_citations: int = 0
    unresolved_citations: int = 0
    ambiguous_citations: int = 0
    amended_citations: int = 0
    repealed_citations: int = 0
    unresolved_placeholders_created: int = 0

    @property
    def dlq_count(self) -> int:
        return self.unparsed_lines + self.invalid_lines

    def verify_line_accounting_invariant(self) -> bool:
        accounted = (
            self.recognized_entity_lines
            + self.recognized_metadata_lines
            + self.ignorable_formatting_lines
            + self.unparsed_lines
            + self.invalid_lines
        )
        return accounted == self.total_lines


# ============================================================================
# 3. Deterministic Corpus Parser & Line Accounting
# ============================================================================

class LegalCorpusParser:
    """
    Deterministic Legal Corpus Parser with exact line accounting and DLQ emission.
    """

    def __init__(
        self,
        source_path: Path,
        default_law_id: Optional[str] = None,
        default_law_name: Optional[str] = None,
        source_only: bool = False,
        instrument_type: LegalInstrumentType = LegalInstrumentType.STATUTE,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ):
        self.source_path = source_path
        self.normalizer = DeterministicLegalNormalizer()
        self.citation_extractor = CitationExtractor()
        self._explicit_default_law_id = default_law_id is not None
        self.source_only = source_only
        if isinstance(instrument_type, LegalInstrumentType):
            self.instrument_type = instrument_type
        elif isinstance(instrument_type, str):
            self.instrument_type = LegalInstrumentType(instrument_type.strip().lower())
        else:
            raise ValueError(f"Unsupported instrument_type: {instrument_type!r}")
        self.start_line = start_line
        self.end_line = end_line
        self.is_aggregate = "all_legal_sentences" in source_path.name.lower()

        fname = source_path.name.lower()
        if default_law_id:
            self.default_law_id = default_law_id
            self.default_law_name = default_law_name or default_law_id
        elif "commercial_bill_1403" in fname or "لایحه" in fname:
            self.default_law_id = "law:commercial_bill_1403"
            self.default_law_name = "لایحه تجارت جمهوری اسلامی ایران مصوب ۱۴۰۳/۰۱/۲۸"
        elif "commercial_code_full" in fname or "commercial code" in fname:
            self.default_law_id = "law:commercial_code_full"
            self.default_law_name = "قانون تجارت کامل (مصوب ۱۳۱۱ با اصلاحات ۱۳۴۷)"
        else:
            self.default_law_id = "law:constitution"
            self.default_law_name = "قانون اساسی جمهوری اسلامی ایران"

        # Regex Patterns
        self.p_law_start = re.compile(
            r"^(قانون\s+اساسی|قانون\s+تجارت|قانون\s+آیین\s+دادرسی\s+مدنی|قانون\s+مجازات\s+اسلامی|قانون\s+[^\n]+)",
            re.IGNORECASE,
        )
        self.p_chapter = re.compile(
            r"^(?:[□■▪▫•\-\*\s]*)(فصل|بخش|باب|مبحث|گفتار|کتاب)\s+([^\n\-–:]+)(.*)",
            re.IGNORECASE,
        )
        self.p_mokarrar = re.compile(
            r"^(?:[□■▪▫•\-\*\s]*)(?:ماده|اصل)(?:\s+[\-–—:]?\s*|\s*[\-–—]\s*)([۰-۹\d]+)(?:\s*[\-–:]\s*|\s+)مکرر",
            re.IGNORECASE,
        )
        self.p_article = re.compile(
            r"^(?:[□■▪▫•\-\*\s]*)(اصل|ماده)(?:\s+[\-–—:]?\s*|\s*[\-–—]\s*)([۰-۹\d]+|اول|دوم|سوم|چهارم|پنجم|واحده)(.*)",
            re.IGNORECASE,
        )
        self.p_clause = re.compile(
            r"^(تبصره\s*\d*|بند\s*[الف-ی\d]+|[۰-۹\d]+\s*[\-\.]|[الف-ی]\s*[\-\)\.]|\([الف-ی\d]+\))(.*)",
            re.IGNORECASE,
        )
        self.p_metadata = re.compile(
            r"^(بسم‌?الله|رئیس\s+مجلس|قانون\s+فوق\s+مشتمل|مصوب|لازم\s+به\s+ذکر|رئیس\s+جمهور)",
            re.IGNORECASE,
        )
        self.p_relocation = re.compile(
            r"^ماده\s+[۰-۹\d]+\s+به\s+ماده\s+.*(?:انتقال\s+یافت|منتقل\s+شد)",
            re.IGNORECASE,
        )

    def parse(self) -> Tuple[List[CanonicalLaw], List[CanonicalChapter], List[CanonicalArticle], List[CanonicalCitation], List[LineClassificationRecord], IngestionStats]:
        stats = IngestionStats()
        records: List[LineClassificationRecord] = []

        with open(self.source_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        start_idx = (self.start_line - 1) if self.start_line else 0
        end_idx = self.end_line if self.end_line else len(raw_lines)
        stats.total_lines = max(0, end_idx - start_idx)

        laws: Dict[str, CanonicalLaw] = {}
        chapters: Dict[str, CanonicalChapter] = {}
        articles: Dict[str, CanonicalArticle] = {}
        citations: List[CanonicalCitation] = []

        current_law_id = self.default_law_id
        law_slug = current_law_id.split(":", 1)[1]
        current_chapter_id = f"chapter:{law_slug}:general"

        if current_law_id not in laws:
            laws[current_law_id] = CanonicalLaw(
                id=current_law_id,
                name=self.default_law_name,
                raw_text=self.default_law_name,
                normalized_text=self.normalizer.normalize(self.default_law_name),
                provenance=ProvenanceSpan(
                    source_file=str(self.source_path.name),
                    source_line_start=1,
                    source_line_end=1,
                    source_char_start=0,
                    source_char_end=len(self.default_law_name),
                    text_hash=self.normalizer.compute_sha256(self.default_law_name),
                ),
                instrument_type=self.instrument_type,
            )
            chapters[current_chapter_id] = CanonicalChapter(
                id=current_chapter_id,
                law_id=current_law_id,
                number_or_slug="general",
                title="کلیات",
                raw_text="کلیات",
                normalized_text="کلیات",
                order=1,
                provenance=ProvenanceSpan(
                    source_file=str(self.source_path.name),
                    source_line_start=1,
                    source_line_end=1,
                    source_char_start=0,
                    source_char_end=5,
                    text_hash=self.normalizer.compute_sha256("کلیات"),
                ),
            )

        current_article: Optional[CanonicalArticle] = None
        current_clause: Optional[CanonicalClause] = None
        in_commercial_1347_block = False
        prev_nonempty_clean = ""

        chapter_counter = 1
        clause_counter = 1

        for line_idx, raw_line in enumerate(raw_lines, 1):
            if self.start_line is not None and line_idx < self.start_line:
                continue
            if self.end_line is not None and line_idx > self.end_line:
                break

            line_str = raw_line.strip()

            # Skip corrupted OCR fragment in free zones tax circular
            if current_law_id == "circular:free_zones_tax_declaration_1396" and line_idx == 66:
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="IGNORABLE_FORMATTING",
                    raw_text=raw_line,
                ))
                stats.ignorable_formatting_lines += 1
                continue

            # Boundary transitions for aggregate corpus
            if self.is_aggregate:
                for start_l, end_l, seg_slug, seg_name, seg_type in AGGREGATE_SEGMENTS:
                    if line_idx == start_l:
                        law_slug = seg_slug
                        current_law_id = f"law:{seg_slug}"
                        if current_law_id not in laws:
                            laws[current_law_id] = CanonicalLaw(
                                id=current_law_id,
                                name=seg_name,
                                raw_text=seg_name,
                                normalized_text=self.normalizer.normalize(seg_name),
                                provenance=ProvenanceSpan(
                                    source_file=str(self.source_path.name),
                                    source_line_start=line_idx,
                                    source_line_end=line_idx,
                                    source_char_start=0,
                                    source_char_end=len(seg_name),
                                    text_hash=self.normalizer.compute_sha256(seg_name),
                                ),
                                instrument_type=seg_type,
                            )
                        chapter_counter += 1
                        if seg_slug == "civil_code" and line_idx == 4794:
                            current_chapter_id = "chapter:civil_code:intro"
                            intro_title = "مقدمه - در انتشار و آثار و اجراء قوانین بطور عموم"
                            chapters[current_chapter_id] = CanonicalChapter(
                                id=current_chapter_id,
                                law_id=current_law_id,
                                number_or_slug="intro",
                                title=intro_title,
                                raw_text=intro_title,
                                normalized_text=self.normalizer.normalize(intro_title),
                                order=chapter_counter,
                                provenance=ProvenanceSpan(
                                    source_file=str(self.source_path.name),
                                    source_line_start=line_idx,
                                    source_line_end=line_idx,
                                    source_char_start=0,
                                    source_char_end=len(intro_title),
                                    text_hash=self.normalizer.compute_sha256(intro_title),
                                ),
                            )
                        else:
                            current_chapter_id = f"chapter:{law_slug}:general"
                            if current_chapter_id not in chapters:
                                chapters[current_chapter_id] = CanonicalChapter(
                                    id=current_chapter_id,
                                    law_id=current_law_id,
                                    number_or_slug="general",
                                    title="کلیات",
                                    raw_text=line_str or "کلیات",
                                    normalized_text=self.normalizer.normalize(line_str or "کلیات"),
                                    order=chapter_counter,
                                    provenance=ProvenanceSpan(
                                        source_file=str(self.source_path.name),
                                        source_line_start=line_idx,
                                        source_line_end=line_idx,
                                        source_char_start=0,
                                        source_char_end=len(line_str or "کلیات"),
                                        text_hash=self.normalizer.compute_sha256(line_str or "کلیات"),
                                    ),
                                )
                        current_article = None
                        current_clause = None
                        break

            # 1. Ignorable Empty / Formatting
            if not line_str:
                stats.ignorable_formatting_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="IGNORABLE_FORMATTING",
                    raw_text=raw_line,
                ))
                continue

            normalized_line = self.normalizer.normalize(line_str)
            header_probe = line_str.replace("\u0640", "")
            prev_line_clean = prev_nonempty_clean
            prev_nonempty_clean = header_probe.rstrip()

            if current_law_id == "law:commercial_code_full":
                if "مبحث اول" in header_probe and (
                    "شرکتهای سهامی" in header_probe or "شرکت های سهامی" in header_probe
                ):
                    in_commercial_1347_block = True
                elif (
                    "لایحه قانونی فوق مشتمل برسیصد ماده" in header_probe
                    or ("مبحث دوم" in header_probe and "محدود" in header_probe)
                ):
                    in_commercial_1347_block = False
            else:
                in_commercial_1347_block = False

            # 2. Editorial relocation notes
            if self.p_relocation.match(line_str):
                stats.recognized_metadata_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_METADATA",
                    raw_text=raw_line,
                    failure_reason="Editorial relocation note",
                ))
                continue

            # 3. Metadata / Signature lines
            if self.p_metadata.match(line_str):
                stats.recognized_metadata_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_METADATA",
                    raw_text=raw_line,
                ))
                continue

            # 4. New Law Header Detection (for non-aggregate inputs)
            is_new_law_header = bool(
                not self.is_aggregate
                and not self._explicit_default_law_id
                and self.p_law_start.match(line_str)
                and len(line_str) <= 180
                and (
                    "مصوب" in line_str
                    or "قانون تجارت" in line_str
                    or "قانون آیین دادرسی" in line_str
                    or "قانون مجازات" in line_str
                    or "قانون اساسی" in line_str
                    or (line_idx == 1 and not self._explicit_default_law_id)
                )
            )
            law_slug = ""
            if is_new_law_header:
                law_slug = self._determine_law_slug(normalized_line)
                candidate_law_id = f"law:{law_slug}"
                # Never treat an embedded repealed/cited statute title inside an active law as a new header
                if articles and candidate_law_id == current_law_id:
                    is_new_law_header = False

            if is_new_law_header:
                current_law_id = f"law:{law_slug}"
                if current_law_id not in laws:
                    laws[current_law_id] = CanonicalLaw(
                        id=current_law_id,
                        name=line_str[:120],
                        raw_text=line_str,
                        normalized_text=normalized_line,
                        provenance=ProvenanceSpan(
                            source_file=str(self.source_path.name),
                            source_line_start=line_idx,
                            source_line_end=line_idx,
                            source_char_start=0,
                            source_char_end=len(line_str),
                            text_hash=self.normalizer.compute_sha256(line_str),
                        ),
                        instrument_type=self.instrument_type,
                    )
                chapter_counter += 1
                current_chapter_id = f"chapter:{law_slug}:general"
                if current_chapter_id not in chapters:
                    chapters[current_chapter_id] = CanonicalChapter(
                        id=current_chapter_id,
                        law_id=current_law_id,
                        number_or_slug="general",
                        title="کلیات",
                        raw_text=line_str,
                        normalized_text=normalized_line,
                        order=chapter_counter,
                        provenance=ProvenanceSpan(
                            source_file=str(self.source_path.name),
                            source_line_start=line_idx,
                            source_line_end=line_idx,
                            source_char_start=0,
                            source_char_end=len(line_str),
                            text_hash=self.normalizer.compute_sha256(line_str),
                        ),
                    )
                current_article = None
                current_clause = None

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
                continue

            # 5. Chapter / Section Header Detection
            chapter_match = self.p_chapter.match(line_str)
            if chapter_match and len(line_str) < 150:
                chapter_counter += 1
                ch_num_raw = chapter_match.group(2).strip()
                ch_slug = f"ch_{chapter_counter}"
                law_slug = current_law_id.split(":", 1)[1]
                current_chapter_id = f"chapter:{law_slug}:{ch_slug}"
                chapters[current_chapter_id] = CanonicalChapter(
                    id=current_chapter_id,
                    law_id=current_law_id,
                    number_or_slug=ch_num_raw,
                    title=line_str,
                    raw_text=line_str,
                    normalized_text=normalized_line,
                    order=chapter_counter,
                    provenance=ProvenanceSpan(
                        source_file=str(self.source_path.name),
                        source_line_start=line_idx,
                        source_line_end=line_idx,
                        source_char_start=0,
                        source_char_end=len(line_str),
                        text_hash=self.normalizer.compute_sha256(line_str),
                    ),
                )
                current_article = None
                current_clause = None

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
                continue

            # 6. Constitution Principle Header Detection
            if current_law_id == "law:constitution":
                p_num = parse_constitution_principle(line_str)
                if p_num is not None:
                    art_id = f"article:constitution:article:{p_num}"
                    if art_id in articles:
                        # Historical superseded or duplicate line in Constitution aggregate
                        stats.recognized_metadata_lines += 1
                        records.append(LineClassificationRecord(
                            source_line_index=line_idx,
                            classification="RECOGNIZED_METADATA",
                            raw_text=raw_line,
                            failure_reason=f"Superseded historical duplicate of Constitution Principle {p_num}",
                        ))
                        continue

                    amendment = "اصلاحی" if "اصلاحی" in line_str else ("الحاقی" if "الحاقی" in line_str else None)
                    current_article = CanonicalArticle(
                        id=art_id,
                        law_id=current_law_id,
                        chapter_id=current_chapter_id,
                        number=str(p_num),
                        raw_text=line_str,
                        normalized_text=normalized_line,
                        status="resolved",
                        amendment_info=amendment,
                        provenance=ProvenanceSpan(
                            source_file=str(self.source_path.name),
                            source_line_start=line_idx,
                            source_line_end=line_idx,
                            source_char_start=0,
                            source_char_end=len(line_str),
                            text_hash=self.normalizer.compute_sha256(line_str),
                        ),
                    )
                    articles[art_id] = current_article
                    current_clause = None

                    stats.recognized_entity_lines += 1
                    records.append(LineClassificationRecord(
                        source_line_index=line_idx,
                        classification="RECOGNIZED_ENTITY",
                        raw_text=raw_line,
                    ))
                    continue

            # 7. Statutory Article Detection (with Mokarrar and Collision Prevention)
            mokarrar_match = self.p_mokarrar.match(header_probe)
            article_match = self.p_article.match(header_probe) if not mokarrar_match else None

            # Skip wrapped in-sentence citation lines in engineering system booklet
            if current_law_id.startswith("regulation:engineering_system") and not line_str.startswith("□") and not line_str.startswith("فصل"):
                mokarrar_match = None
                article_match = None

            if mokarrar_match or article_match:
                if mokarrar_match:
                    art_num_raw = mokarrar_match.group(1).strip()
                    art_num_norm = f"{self.normalizer.normalize_digits(art_num_raw)}_mokarrar"
                else:
                    art_num_raw = article_match.group(2).strip()
                    art_num_norm = self.normalizer.normalize_digits(art_num_raw)

                law_slug = current_law_id.split(":", 1)[1]

                # Specific clerical anomaly resolution grounded in legal sources
                if current_law_id == "law:anti_money_laundering" and art_num_norm == "11" and f"article:{law_slug}:article:11" in articles:
                    art_num_norm = "11_2"
                elif current_law_id == "law:permanent_development_provisions":
                    tens_typos = {76: "10", 228: "20", 276: "30", 429: "40", 476: "50", 525: "60", 564: "70"}
                    if line_idx in tens_typos:
                        art_num_norm = tens_typos[line_idx]
                elif current_law_id == "regulation:country_contracts_database_1392" and art_num_norm == "4" and f"article:{law_slug}:article:4" in articles:
                    art_num_norm = "4_2"

                block_amendment_tag: Optional[str] = None
                if current_law_id == "law:commercial_code_full" and in_commercial_1347_block:
                    block_amendment_tag = "اصلاحی ۱۳۴۷"
                    base_digits = art_num_norm.split("_", 1)[0]
                    if base_digits.isdigit() and not (21 <= int(base_digits) <= 93):
                        art_num_norm = f"{art_num_norm}_1347"

                article_canonical_id = f"article:{law_slug}:article:{art_num_norm}"

                if (
                    current_article is not None
                    and self._is_wrapped_mid_sentence_citation(prev_line_clean)
                ):
                    mokarrar_match = None
                    article_match = None

            if mokarrar_match or article_match:
                if article_canonical_id in articles:
                    prev = articles[article_canonical_id]
                    raise CanonicalIdentityCollision(
                        f"Duplicate canonical ID detected: {article_canonical_id} at line {line_idx} "
                        f"collides with existing definition from line {prev.provenance.source_line_start}"
                    )

                amendment = None
                if "اصلاحی" in line_str:
                    amendment = "اصلاحی"
                elif "الحاقی" in line_str:
                    amendment = "الحاقی"
                if block_amendment_tag and amendment is None:
                    amendment = block_amendment_tag

                current_article = CanonicalArticle(
                    id=article_canonical_id,
                    law_id=current_law_id,
                    chapter_id=current_chapter_id,
                    number=art_num_norm,
                    raw_text=line_str,
                    normalized_text=normalized_line,
                    status="resolved",
                    amendment_info=amendment,
                    provenance=ProvenanceSpan(
                        source_file=str(self.source_path.name),
                        source_line_start=line_idx,
                        source_line_end=line_idx,
                        source_char_start=0,
                        source_char_end=len(line_str),
                        text_hash=self.normalizer.compute_sha256(line_str),
                    ),
                )
                articles[article_canonical_id] = current_article
                current_clause = None

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
                continue

            # 8. Clause / Note Detection
            clause_match = self.p_clause.match(line_str)
            if clause_match and current_article is not None:
                clause_counter += 1
                c_prefix = clause_match.group(1).strip()
                c_type = "note" if "تبصره" in c_prefix else "item"
                law_slug = current_law_id.split(":", 1)[1]
                clause_id = f"clause:{law_slug}:article:{current_article.number}:clause:{clause_counter}"

                current_clause = CanonicalClause(
                    id=clause_id,
                    article_id=current_article.id,
                    law_id=current_law_id,
                    clause_type=c_type,
                    number=c_prefix,
                    raw_text=line_str,
                    normalized_text=normalized_line,
                    order=len(current_article.clauses) + 1,
                    provenance=ProvenanceSpan(
                        source_file=str(self.source_path.name),
                        source_line_start=line_idx,
                        source_line_end=line_idx,
                        source_char_start=0,
                        source_char_end=len(line_str),
                        text_hash=self.normalizer.compute_sha256(line_str),
                    ),
                )
                current_article.clauses.append(current_clause)

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
                continue

            # 9. Body / Paragraph Continuation
            if current_clause is not None:
                current_clause.raw_text += "\n" + line_str
                current_clause.normalized_text += " " + normalized_line
                current_clause.provenance.source_line_end = line_idx
                current_clause.provenance.text_hash = self.normalizer.compute_sha256(current_clause.raw_text)

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
            elif current_article is not None:
                current_article.raw_text += "\n" + line_str
                current_article.normalized_text += " " + normalized_line
                current_article.provenance.source_line_end = line_idx
                current_article.provenance.text_hash = self.normalizer.compute_sha256(current_article.raw_text)

                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))
            else:
                stats.recognized_entity_lines += 1
                records.append(LineClassificationRecord(
                    source_line_index=line_idx,
                    classification="RECOGNIZED_ENTITY",
                    raw_text=raw_line,
                ))

        # 10. Cross-Reference Resolution Pass
        citations = self._resolve_citations(articles, laws)

        stats.laws_count = len(laws)
        stats.chapters_count = len(chapters)
        stats.articles_count = len(articles)
        stats.clauses_count = sum(len(a.clauses) for a in articles.values())

        stats.resolved_citations = sum(1 for c in citations if c.status == "RESOLVED")
        stats.unresolved_citations = sum(1 for c in citations if c.status == "UNRESOLVED")
        stats.ambiguous_citations = sum(1 for c in citations if c.status == "AMBIGUOUS")
        stats.amended_citations = sum(1 for c in citations if c.citation_type == "AMENDS")
        stats.repealed_citations = sum(1 for c in citations if c.citation_type == "REPEALS")

        if not articles and self.source_only:
            raw_text = "".join(raw_lines).rstrip("\n")
            normalized_text = self.normalizer.normalize(raw_text)
            source_line_end = max(1, len(raw_lines))
            source_char_end = len(raw_text)
            for law in laws.values():
                law.raw_text = raw_text
                law.normalized_text = normalized_text
                law.provenance.source_line_start = 1
                law.provenance.source_line_end = source_line_end
                law.provenance.source_char_start = 0
                law.provenance.source_char_end = source_char_end
                law.provenance.text_hash = self.normalizer.compute_sha256(raw_text)

        for law in laws.values():
            validate_provenance_span(law.provenance, law.raw_text)
        for chapter in chapters.values():
            validate_provenance_span(chapter.provenance, chapter.raw_text)
        for article in articles.values():
            if article.provenance is None:
                raise ValueError(f"Article {article.id} has no provenance")
            validate_provenance_span(article.provenance, article.raw_text)
            for clause in article.clauses:
                validate_provenance_span(clause.provenance, clause.raw_text)

        return list(laws.values()), list(chapters.values()), list(articles.values()), citations, records, stats

    _WRAPPED_CITATION_LINKERS = (
        "برخلاف",
        "خلاف",
        "موافق",
        "مقررات",
        "رعایت",
        "مطابق",
        "موضوع",
        "بموجب",
        "به موجب",
        "موجب",
        "طبق",
        "مستند",
        "مستفاد",
        "مندرج در",
        "مذکور در",
        "مذکوردر",
        "از حیث",
        "به استناد",
        "باستناد",
        "که",
    )

    @classmethod
    def _is_wrapped_mid_sentence_citation(cls, prev_line_clean: str) -> bool:
        """Detect a mid-sentence line wrap ending right before an inline 'ماده N' reference."""
        s = prev_line_clean.rstrip()
        if not s or s.endswith((".", "؟", "!", "؛", ":", ")")):
            return False
        s_clean = s.rstrip("،,ـ ").strip()
        s_norm = s_clean.replace("،", " ").replace("؛", " ").replace(",", " ")
        for linker in cls._WRAPPED_CITATION_LINKERS:
            if s_norm == linker or s_norm.endswith(" " + linker) or s_norm.endswith("\u200c" + linker):
                return True
        return False

    def _determine_law_slug(self, text: str) -> str:
        if self.default_law_id and self.default_law_id in (
            "law:commercial_code_full",
            "law:commercial_bill_1403",
            "law:engineering_system",
            "law:conditions_of_contract_4311",
            "law:commercial_code_1311",
            "law:commercial_amendment_1347",
            "law:criminal_procedure_1392",
            "law:civil_procedure_1379",
            "law:civil_code",
            "law:penal_code_1392",
            "law:penal_code_tazirat_1375",
        ):
            return self.default_law_id.split(":", 1)[1]
        if "سهامی" in text or "۱۳۴۷" in text or "1347" in text:
            return "commercial_amendment_1347"
        elif "لایحه تجارت" in text or "لایحه" in text:
            return "commercial_bill_1403"
        elif "نظام مهندسی" in text:
            return "engineering_system"
        elif "پیمان" in text or "۴۳۱۱" in text or "4311" in text:
            return "conditions_of_contract_4311"
        elif "تعزیرات" in text:
            return "penal_code_tazirat_1375"
        elif "مجازات" in text:
            return "penal_code_1392"
        elif "کیفری" in text:
            return "criminal_procedure_1392"
        elif "آیین دادرسی" in text or "ایین دادرسی" in text or "امور مدنی" in text:
            return "civil_procedure_1379"
        elif "تجارت" in text:
            return "commercial_code_1311"
        elif "اساسی" in text:
            return "constitution"
        elif "مدنی" in text:
            return "civil_code"
        else:
            slug = re.sub(r"[^\w]", "_", text[:30])
            return slug or "general_law"

    _RE_CITE_NOTE = re.compile(
        r"تبصره\s+([۰-۹\d]+)\s+(?:ذیل\s+|از\s+)?(?:ماده|اصل)\s+([۰-۹\d]+)",
        re.IGNORECASE,
    )
    _RE_CITE_CLAUSE_ITEM = re.compile(
        r"بند\s+(الف|[آ-ی]|[۰-۹\d]+)\s+(?:ذیل\s+|از\s+)?(?:ماده|اصل)\s+([۰-۹\d]+)",
        re.IGNORECASE,
    )
    _RE_CITE_RANGE = re.compile(
        r"مواد\s+([۰-۹\d]+)\s*(?:تا|الی|لغایت)\s*([۰-۹\d]+)",
        re.IGNORECASE,
    )
    _RE_CITE_BASE = re.compile(
        r"(?:ماده|مواد|اصل)\s+([۰-۹\d]+(?:\s*(?:و|تا|الی|,|،)\s*[۰-۹\d]+)*)",
        re.IGNORECASE,
    )
    _SELF_LAW_TOKENS = (
        "این قانون",
        "همین قانون",
        "این آیین نامه",
        "این آیین‌نامه",
        "این لایحه",
        "این تصویب نامه",
        "این تصویب‌نامه",
    )

    def _resolve_target_clause(
        self,
        target_article: CanonicalArticle,
        clause_kind: Optional[str],
        clause_token: Optional[str],
    ) -> Optional[str]:
        """Match a cited note ('تبصره N') or item ('بند الف/N') to a CanonicalClause.id."""
        if not clause_kind or not clause_token or not target_article.clauses:
            return None
        token_norm = self.normalizer.normalize_digits(clause_token).strip()
        notes = [c for c in target_article.clauses if c.clause_type == "note"]
        for idx, clause in enumerate(target_article.clauses, start=1):
            if clause.clause_type != clause_kind:
                continue
            num_norm = self.normalizer.normalize_digits(clause.number or "")
            if clause_kind == "note":
                digits_in_num = re.findall(r"\d+", num_norm)
                if digits_in_num and digits_in_num[0] == token_norm:
                    return clause.id
                if len(notes) == 1 and token_norm == "1":
                    return clause.id
            elif clause_kind == "item":
                cleaned_num = re.sub(r"^(?:بند|جزء|قسمت)\s*", "", num_norm).strip()
                if cleaned_num == token_norm or str(idx) == token_norm:
                    return clause.id
        return None

    def _resolve_citations(
        self,
        articles: Dict[str, CanonicalArticle],
        laws: Dict[str, CanonicalLaw],
    ) -> List[CanonicalCitation]:
        citations: List[CanonicalCitation] = []

        for _art_id, article in articles.items():
            text = article.normalized_text
            raw_spans: List[Tuple[int, int, str, List[str], Optional[str], Optional[str], Optional[str]]] = []

            for m in self._RE_CITE_NOTE.finditer(text):
                c_num = self.normalizer.normalize_digits(m.group(1))
                a_num = self.normalizer.normalize_digits(m.group(2))
                raw_spans.append((m.start(), m.end(), m.group(0), [a_num], "note", c_num, f"تبصره {c_num}"))

            for m in self._RE_CITE_CLAUSE_ITEM.finditer(text):
                c_tok = self.normalizer.normalize_digits(m.group(1)).strip()
                a_num = self.normalizer.normalize_digits(m.group(2))
                raw_spans.append((m.start(), m.end(), m.group(0), [a_num], "item", c_tok, f"بند {c_tok}"))

            for m in self._RE_CITE_RANGE.finditer(text):
                n_start = int(self.normalizer.normalize_digits(m.group(1)))
                n_end = int(self.normalizer.normalize_digits(m.group(2)))
                if 1 <= n_end - n_start <= 50:
                    expanded = [str(n) for n in range(n_start, n_end + 1)]
                else:
                    expanded = [str(n_start), str(n_end)]
                raw_spans.append((m.start(), m.end(), m.group(0), expanded, None, None, None))

            for m in self._RE_CITE_BASE.finditer(text):
                nums = re.findall(r"\d+", self.normalizer.normalize_digits(m.group(1)))
                raw_spans.append((m.start(), m.end(), m.group(0), nums, None, None, None))

            # Prioritize specific longer patterns when spans overlap
            raw_spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
            matches = []
            occupied: List[Tuple[int, int]] = []
            for span in raw_spans:
                s, e = span[0], span[1]
                if any(max(s, os_) < min(e, oe_) for os_, oe_ in occupied):
                    continue
                occupied.append((s, e))
                matches.append(span)

            matches.sort(key=lambda item: item[0])

            source_in_1347_block = (
                article.law_id == "law:commercial_code_full"
                and (
                    article.number.endswith("_1347")
                    or article.amendment_info == "اصلاحی ۱۳۴۷"
                    or (article.number.isdigit() and 21 <= int(article.number) <= 93)
                )
            )

            seen_cit_keys: Set[Tuple[str, str, str, str]] = set()
            for idx, (m_start, m_end, ref_span, nums, clause_kind, clause_token, clause_ref) in enumerate(matches):
                next_match_start = matches[idx + 1][0] if idx + 1 < len(matches) else len(text)
                context_window = text[m_end : min(next_match_start, m_end + CITATION_CONTEXT_WINDOW_CHARS)]
                citation_type = self._classify_citation_type(context_window)

                # Bound external law name lookup to the immediate clause/sentence
                law_window = context_window[:120]
                for sep in ("؛", "\n", "."):
                    sep_idx = law_window.find(sep)
                    if sep_idx != -1:
                        law_window = law_window[:sep_idx]

                explicit_law_id: Optional[str] = None
                self_pos = min(
                    (law_window.find(tok) for tok in self._SELF_LAW_TOKENS if tok in law_window),
                    default=-1,
                )
                ext_candidate = resolve_law_id_from_text_span(law_window)
                if ext_candidate and self_pos == -1:
                    if article.law_id == "law:commercial_code_full" and ext_candidate == "law:commercial_code_1311" and "1311" not in law_window:
                        explicit_law_id = None
                    else:
                        explicit_law_id = ext_candidate

                resolved_law_id = explicit_law_id or article.law_id
                law_slug = resolved_law_id.split(":", 1)[1] if ":" in resolved_law_id else resolved_law_id

                for num in nums:
                    raw_target_id = f"article:{law_slug}:article:{num}"
                    if resolved_law_id == article.law_id and source_in_1347_block:
                        candidate_1347 = f"article:{law_slug}:article:{num}_1347"
                        if candidate_1347 in articles:
                            raw_target_id = candidate_1347

                    target_art_id = resolve_cross_law_target(raw_target_id)
                    redirected_src = raw_target_id if target_art_id != raw_target_id else None
                    effective_law_id = (
                        derive_law_id_from_node_id(target_art_id)
                        if redirected_src is not None
                        else resolved_law_id
                    )

                    if target_art_id == article.id and not clause_ref:
                        continue

                    target_clause_id: Optional[str] = None
                    if target_art_id in articles:
                        target_clause_id = self._resolve_target_clause(
                            articles[target_art_id],
                            clause_kind,
                            clause_token,
                        )
                        status_val = "RESOLVED"
                    else:
                        status_val = "UNRESOLVED"

                    dedup_key = (target_art_id, target_clause_id or "", citation_type, ref_span)
                    if dedup_key in seen_cit_keys:
                        continue
                    seen_cit_keys.add(dedup_key)

                    citations.append(
                        CanonicalCitation(
                            source_article_id=article.id,
                            target_article_id=target_art_id,
                            citation_text=ref_span,
                            citation_type=citation_type,
                            status=status_val,
                            raw_target_number=num,
                            target_law_id=effective_law_id,
                            target_clause_id=target_clause_id,
                            target_clause_ref=clause_ref,
                            redirected_from=redirected_src,
                        )
                    )
        return citations

    @staticmethod
    def _classify_citation_type(context_window: str) -> str:
        """Deterministically classify the legal effect of a citation from the
        text immediately following the reference.

        The window is bounded by the next citation match so that triggers of a
        later reference cannot leak into an earlier reference's classification.
        """
        amends = _AMENDS_CONTEXT_PATTERN.search(context_window)
        repeals = _REPEALS_CONTEXT_PATTERN.search(context_window)
        if amends and repeals:
            return "AMENDS" if amends.start() <= repeals.start() else "REPEALS"
        if amends:
            return "AMENDS"
        if repeals:
            return "REPEALS"
        return "REFERENCES"


# ============================================================================
# 4. Resilient Cypher Executor Bridge
# ============================================================================

class CypherBridge:
    """
    Unified, fail-safe Cypher execution bridge supporting batched and governed writes.
    """

    def __init__(
        self,
        connection=None,
        password: Optional[str] = None,
        *,
        actor_id: str = "legal-kg-builder",
        correlation_id: Optional[str] = None,
        pipeline: Optional[ValidatorPipeline] = None,
    ):
        self.connection = connection or get_connection()
        self.actor_id = actor_id
        self.correlation_id = correlation_id or "legal-kg-build"
        self.pipeline = pipeline or ValidatorPipeline()

    @staticmethod
    def _ensure_audit_sink() -> None:
        if get_audit_sink() is None:
            set_audit_sink(compose_default_filesystem_sink())

    def execute(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute through the canonical read or governed mutation surface."""
        if not classify_cypher(cypher):
            return "\n".join(
                str(dict(r))
                for r in self.connection.execute_query(cypher, parameters)
            )

        self._ensure_audit_sink()
        statements = [part.strip() for part in cypher.split(";") if part.strip()]

        active_ctx = GovernanceContextManager.get_current_context()
        if active_ctx is not None:
            with self.connection.governed_session(
                pipeline=self.pipeline,
                correlation_id=active_ctx.correlation_id,
                actor_id=active_ctx.actor_id,
            ) as session:
                output = []
                for statement in statements:
                    output.extend(session.execute_cypher(statement, parameters))
                return "\n".join(str(dict(r)) for r in output)

        async def execute_mutation():
            async with GovernanceContextManager.active_context(
                correlation_id=self.correlation_id,
                execution_mode="STRICT",
                actor_id=self.actor_id,
            ) as ctx:
                with self.connection.governed_session(
                    pipeline=self.pipeline,
                    correlation_id=ctx.correlation_id,
                    actor_id=ctx.actor_id,
                ) as session:
                    output = []
                    for statement in statements:
                        output.extend(session.execute_cypher(statement, parameters))
                    return output

        return "\n".join(str(dict(r)) for r in asyncio.run(execute_mutation()))

    def execute_apoc_batch(self, query: str, data_list: List[Dict[str, Any]]) -> str:
        """Execute a batch without depending on optional APOC procedures."""
        if not data_list:
            return ""
        stmt = f"UNWIND $items AS item\n{query}\n"
        return self.execute(stmt, {"items": data_list})

    def execute_batched_materialization(
        self,
        materializer: BatchedSemanticMaterializer,
        statements: List[Tuple[str, Dict[str, Any]]],
        *,
        batch_size: int = 100,
    ) -> Any:
        """Execute BatchedSemanticMaterializer statements under active governance."""
        if not statements:
            return None

        def _materialize_in_scope(corr_id: str, actor_id: str) -> Any:
            with self.connection.governed_session(
                pipeline=self.pipeline,
                correlation_id=corr_id,
                actor_id=actor_id,
            ) as governed_session:
                return materializer.execute_governed_materialization(
                    governed_session=governed_session,
                    statements=statements,
                    job_id=corr_id,
                )

        self._ensure_audit_sink()
        active_ctx = GovernanceContextManager.get_current_context()
        if active_ctx is not None:
            return _materialize_in_scope(active_ctx.correlation_id, active_ctx.actor_id)

        async def _run_materialization():
            async with GovernanceContextManager.active_context(
                correlation_id=self.correlation_id,
                execution_mode="STRICT",
                actor_id=self.actor_id,
            ) as ctx:
                return _materialize_in_scope(ctx.correlation_id, ctx.actor_id)

        return asyncio.run(_run_materialization())


# ============================================================================
# 5. Neo4j Batch Transaction Ingestion & Fingerprinting
# ============================================================================

class HardenedKnowledgeGraphCompiler:
    """
    Compiles Canonical Legal IR into Neo4j with idempotency, constraints, and audit proofs.
    """

    def __init__(
        self,
        run_id: Optional[str] = None,
        connection=None,
        *,
        actor_id: str = "legal-kg-builder",
        pipeline: Optional[ValidatorPipeline] = None,
    ):
        self.run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.actor_id = actor_id
        self.validator_pipeline = pipeline or ValidatorPipeline()
        self.bridge = CypherBridge(
            connection=connection,
            actor_id=self.actor_id,
            correlation_id=self.run_id,
            pipeline=self.validator_pipeline,
        )

    def ensure_schema_and_constraints(self) -> None:
        """Create uniqueness constraints and query-critical indexes."""
        constraints_script = """
        CREATE CONSTRAINT law_id_unique IF NOT EXISTS FOR (l:Law) REQUIRE l.id IS UNIQUE;
        CREATE CONSTRAINT chapter_id_unique IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE;
        CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE;
        CREATE CONSTRAINT clause_id_unique IF NOT EXISTS FOR (c:Clause) REQUIRE c.id IS UNIQUE;
        CREATE CONSTRAINT run_id_unique IF NOT EXISTS FOR (r:IngestionRun) REQUIRE r.id IS UNIQUE;
        CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;
        CREATE INDEX article_number_idx IF NOT EXISTS FOR (a:Article) ON (a.number);
        CREATE INDEX article_status_idx IF NOT EXISTS FOR (a:Article) ON (a.status);
        CREATE INDEX article_law_idx IF NOT EXISTS FOR (a:Article) ON (a.law_id);
        CREATE INDEX condition_id_idx IF NOT EXISTS FOR (c:Condition) ON (c.id);
        CREATE INDEX sanction_id_idx IF NOT EXISTS FOR (s:Sanction) ON (s.id);
        CREATE INDEX exception_id_idx IF NOT EXISTS FOR (e:Exception) ON (e.id);
        """
        logger.info("Applying Neo4j uniqueness constraints and indexes...")
        self.bridge.execute(constraints_script)
        logger.info("✅ Uniqueness constraints & indexes verified.")

    @staticmethod
    def _validate_input_parent_uniqueness(
        articles: List[CanonicalArticle],
    ) -> None:
        """Reject one Article ID mapped to multiple chapters in one corpus."""
        chapter_by_article: Dict[str, str] = {}
        conflicts: List[str] = []
        for article in articles:
            previous_chapter = chapter_by_article.setdefault(article.id, article.chapter_id)
            if previous_chapter != article.chapter_id and article.id not in conflicts:
                conflicts.append(article.id)
        if conflicts:
            preview = ", ".join(conflicts[:5])
            suffix = "..." if len(conflicts) > 5 else ""
            raise ValueError(
                "Fail-closed preflight: Article IDs map to multiple chapters "
                f"in the input corpus ({preview}{suffix})"
            )

    def validate_existing_parent_uniqueness(
        self,
        articles: List[CanonicalArticle],
    ) -> None:
        """Reject incoming articles that would create an invalid parent topology."""
        if not articles:
            return
        result = self.bridge.execute(
            """
            UNWIND $items AS item
            MATCH (a:Article {id: item.id})
            OPTIONAL MATCH (c:Chapter)-[:CONTAINS]->(a)
            WITH item, collect(c.id) AS parents
            WHERE size(parents) > 1
               OR any(parent IN parents WHERE parent IS NOT NULL AND parent <> item.chapter_id)
            RETURN count(*) AS conflicts;
            """,
            {"items": [{"id": a.id, "chapter_id": a.chapter_id} for a in articles]},
        )
        lines = result.strip().splitlines()
        conflicts = int(ast.literal_eval(lines[-1])["conflicts"]) if lines else 0
        if conflicts:
            raise ValueError(
                "Fail-closed preflight: existing graph contains Article parent "
                f"conflicts for {conflicts} incoming article(s)"
            )

    def compile(
        self,
        laws: List[CanonicalLaw],
        chapters: List[CanonicalChapter],
        articles: List[CanonicalArticle],
        citations: List[CanonicalCitation],
        source_hash: str,
        source_file: str,
        batch_size: int = 500,
        has_dlq: bool = False,
        enable_semantic_enrichment: bool = True,
    ) -> Dict[str, Any]:
        self._validate_input_parent_uniqueness(articles)
        self.validate_existing_parent_uniqueness(articles)
        self.ensure_schema_and_constraints()
        start_time = time.time()

        # 1. Register IngestionRun Manifest
        run_init_cypher = """
        MERGE (r:IngestionRun {id: $run_id})
        SET r.source_file = $source_file,
            r.source_hash = $source_hash,
            r.parser_version = $parser_version,
            r.schema_version = $schema_version,
            r.started_at = datetime(),
            r.status = 'RUNNING';
        """
        self.bridge.execute(
            run_init_cypher,
            {
                "run_id": self.run_id,
                "source_file": source_file,
                "source_hash": source_hash,
                "parser_version": PARSER_VERSION,
                "schema_version": SCHEMA_VERSION,
            },
        )

        # 2. Ingest Laws (enriched with canonical metadata registry)
        logger.info(f"Ingesting {len(laws)} Laws...")
        laws_data = []
        for law in laws:
            law_meta = get_law_metadata(law.id) or {}
            canonical_title = law_meta.get("title") or getattr(law, "title", None) or law.name
            laws_data.append(
                {
                    "id": law.id,
                    "name": law.name,
                    "title": canonical_title,
                    "enactment_date": law_meta.get("enactment_date"),
                    "hierarchy_level": law_meta.get("hierarchy_level"),
                    "specificity_level": law_meta.get("specificity_level"),
                    "raw_text": law.raw_text,
                    "normalized_text": law.normalized_text,
                    "instrument_type": (
                        law.instrument_type.value
                        if isinstance(law.instrument_type, LegalInstrumentType)
                        else LegalInstrumentType(str(law.instrument_type).strip().lower()).value
                    ),
                    "source_file": law.provenance.source_file,
                    "source_line_start": law.provenance.source_line_start,
                    "source_line_end": law.provenance.source_line_end,
                    "source_char_start": law.provenance.source_char_start,
                    "source_char_end": law.provenance.source_char_end,
                    "text_hash": law.provenance.text_hash,
                    "parser_version": law.provenance.parser_version,
                    "schema_version": law.provenance.schema_version,
                    "ingestion_run_id": self.run_id,
                    "source_hash": source_hash,
                }
            )
        self.bridge.execute_apoc_batch(
            """
            MERGE (l:Law {id: item.id})
            ON CREATE SET
                l.name = item.name,
                l.title = item.title,
                l.enactment_date = item.enactment_date,
                l.hierarchy_level = item.hierarchy_level,
                l.specificity_level = item.specificity_level,
                l.raw_text = item.raw_text,
                l.normalized_text = item.normalized_text,
                l.instrument_type = item.instrument_type,
                l.source_file = item.source_file,
                l.source_line_start = item.source_line_start,
                l.source_line_end = item.source_line_end,
                l.source_char_start = item.source_char_start,
                l.source_char_end = item.source_char_end,
                l.text_hash = item.text_hash,
                l.parser_version = item.parser_version,
                l.schema_version = item.schema_version,
                l.ingestion_run_id = item.ingestion_run_id,
                l.source_hash = item.source_hash,
                l.created_at = datetime()
            ON MATCH SET
                l.title = coalesce(item.title, l.title, l.name),
                l.enactment_date = coalesce(item.enactment_date, l.enactment_date),
                l.hierarchy_level = coalesce(item.hierarchy_level, l.hierarchy_level),
                l.specificity_level = coalesce(item.specificity_level, l.specificity_level),
                l.updated_at = datetime()
            """,
            laws_data,
        )

        # 3. Ingest Chapters
        logger.info(f"Ingesting {len(chapters)} Chapters...")
        chapters_data = [
            {
                "id": c.id,
                "law_id": c.law_id,
                "number_or_slug": c.number_or_slug,
                "title": c.title,
                "raw_text": c.raw_text,
                "normalized_text": c.normalized_text,
                "order": c.order,
                "source_file": c.provenance.source_file,
                "source_line_start": c.provenance.source_line_start,
                "source_line_end": c.provenance.source_line_end,
                "source_char_start": c.provenance.source_char_start,
                "source_char_end": c.provenance.source_char_end,
                "text_hash": c.provenance.text_hash,
                "parser_version": c.provenance.parser_version,
                "schema_version": c.provenance.schema_version,
                "ingestion_run_id": self.run_id,
                "source_hash": source_hash,
            }
            for c in chapters
        ]
        self.bridge.execute_apoc_batch(
            """
            MERGE (c:Chapter {id: item.id})
            ON CREATE SET
                c.law_id = item.law_id,
                c.number_or_slug = item.number_or_slug,
                c.title = item.title,
                c.raw_text = item.raw_text,
                c.normalized_text = item.normalized_text,
                c.order = item.order,
                c.source_file = item.source_file,
                c.source_line_start = item.source_line_start,
                c.source_line_end = item.source_line_end,
                c.source_char_start = item.source_char_start,
                c.source_char_end = item.source_char_end,
                c.text_hash = item.text_hash,
                c.parser_version = item.parser_version,
                c.schema_version = item.schema_version,
                c.ingestion_run_id = item.ingestion_run_id,
                c.source_hash = item.source_hash,
                c.created_at = datetime()
            WITH c, item
            MATCH (l:Law {id: item.law_id})
            MERGE (l)-[r:CONTAINS]->(c)
            SET r.order = item.order,
                r.ingestion_run_id = item.ingestion_run_id,
                r.source_hash = item.source_hash
            """,
            chapters_data,
        )

        # 4. Ingest Articles (Batched)
        logger.info(f"Ingesting {len(articles)} Articles in batches of {batch_size}...")
        for i in range(0, len(articles), batch_size):
            art_batch = articles[i : i + batch_size]
            arts_data = [
                {
                    "id": a.id,
                    "law_id": a.law_id,
                    "chapter_id": a.chapter_id,
                    "number": a.number,
                    "raw_text": a.raw_text,
                    "normalized_text": a.normalized_text,
                    "amendment_info": a.amendment_info,
                    "source_file": a.provenance.source_file,
                    "source_line_start": a.provenance.source_line_start,
                    "source_line_end": a.provenance.source_line_end,
                    "source_char_start": a.provenance.source_char_start,
                    "source_char_end": a.provenance.source_char_end,
                    "text_hash": a.provenance.text_hash,
                    "parser_version": a.provenance.parser_version,
                    "schema_version": a.provenance.schema_version,
                    "ingestion_run_id": self.run_id,
                    "source_hash": source_hash,
                }
                for a in art_batch
            ]
            self.bridge.execute_apoc_batch(
                """
                MERGE (a:Article {id: item.id})
                ON CREATE SET
                    a.law_id = item.law_id,
                    a.chapter_id = item.chapter_id,
                    a.number = item.number,
                    a.raw_text = item.raw_text,
                    a.normalized_text = item.normalized_text,
                    a.status = 'resolved',
                    a.amendment_info = item.amendment_info,
                    a.source_file = item.source_file,
                    a.source_line_start = item.source_line_start,
                    a.source_line_end = item.source_line_end,
                    a.source_char_start = item.source_char_start,
                    a.source_char_end = item.source_char_end,
                    a.text_hash = item.text_hash,
                    a.parser_version = item.parser_version,
                    a.schema_version = item.schema_version,
                    a.ingestion_run_id = item.ingestion_run_id,
                    a.created_at = datetime()
                ON MATCH SET
                    a.law_id = coalesce(a.law_id, item.law_id),
                    a.chapter_id = coalesce(a.chapter_id, item.chapter_id),
                    a.number = coalesce(a.number, item.number),
                    a.raw_text = CASE WHEN a.status = 'unresolved' THEN item.raw_text ELSE a.raw_text END,
                    a.normalized_text = CASE WHEN a.status = 'unresolved' THEN item.normalized_text ELSE a.normalized_text END,
                    a.text_hash = CASE WHEN a.status = 'unresolved' THEN item.text_hash ELSE a.text_hash END,
                    a.amendment_info = coalesce(item.amendment_info, a.amendment_info),
                    a.status = 'resolved'
                WITH a, item
                MATCH (c:Chapter {id: item.chapter_id})
                MERGE (c)-[r:CONTAINS]->(a)
                SET r.ingestion_run_id = item.ingestion_run_id,
                    r.source_hash = item.source_hash
                """,
                arts_data,
            )

            # Ingest Clauses for this batch
            all_clauses = [cl for a in art_batch for cl in a.clauses]
            if all_clauses:
                cl_data = [
                    {
                        "id": cl.id,
                        "article_id": cl.article_id,
                        "law_id": cl.law_id,
                        "clause_type": cl.clause_type,
                        "number": cl.number,
                        "raw_text": cl.raw_text,
                        "normalized_text": cl.normalized_text,
                        "order": cl.order,
                        "source_file": cl.provenance.source_file,
                        "source_line_start": cl.provenance.source_line_start,
                        "source_line_end": cl.provenance.source_line_end,
                        "source_char_start": cl.provenance.source_char_start,
                        "source_char_end": cl.provenance.source_char_end,
                        "text_hash": cl.provenance.text_hash,
                        "parser_version": cl.provenance.parser_version,
                        "schema_version": cl.provenance.schema_version,
                        "ingestion_run_id": self.run_id,
                        "source_hash": source_hash,
                    }
                    for cl in all_clauses
                ]
                self.bridge.execute_apoc_batch(
                    """
                    MERGE (c:Clause {id: item.id})
                    ON CREATE SET
                        c.article_id = item.article_id,
                        c.law_id = item.law_id,
                        c.clause_type = item.clause_type,
                        c.number = item.number,
                        c.raw_text = item.raw_text,
                        c.normalized_text = item.normalized_text,
                        c.order = item.order,
                        c.source_file = item.source_file,
                        c.source_line_start = item.source_line_start,
                        c.source_line_end = item.source_line_end,
                        c.source_char_start = item.source_char_start,
                        c.source_char_end = item.source_char_end,
                        c.text_hash = item.text_hash,
                        c.parser_version = item.parser_version,
                        c.schema_version = item.schema_version,
                        c.ingestion_run_id = item.ingestion_run_id,
                        c.source_hash = item.source_hash,
                        c.created_at = datetime()
                    WITH c, item
                    MATCH (a:Article {id: item.article_id})
                    MERGE (a)-[r:CONTAINS]->(c)
                    SET r.order = item.order,
                        r.clause_type = item.clause_type,
                        r.ingestion_run_id = item.ingestion_run_id,
                        r.source_hash = item.source_hash
                    """,
                    cl_data,
                )

        # 5. Ingest Citations & Redirected Cross-Law Placeholders (Batched)
        # Unresolved targets are intentional, deterministic placeholders. Known
        # misdirected cross-law aliases are redirected via KNOWN_CROSS_LAW_REDIRECTS
        # prior to write so phantom stubs are never materialized.
        logger.info(f"Ingesting {len(citations)} Cross-References...")
        resolved_article_ids = {a.id for a in articles}
        valid_citations = [c for c in citations if c.status in ("RESOLVED", "UNRESOLVED")]
        citations_by_type = self._group_citations_by_relationship_type(valid_citations)
        for rel_type, typed_citations in citations_by_type.items():
            for i in range(0, len(typed_citations), batch_size):
                cit_batch = typed_citations[i : i + batch_size]
                cit_data = []
                for c in cit_batch:
                    effective_target_id = resolve_cross_law_target(c.target_article_id)
                    redirected_from = (
                        c.target_article_id
                        if effective_target_id != c.target_article_id
                        else getattr(c, "redirected_from", None)
                    )
                    effective_law_id = (
                        derive_law_id_from_node_id(effective_target_id)
                        if redirected_from is not None
                        else c.target_law_id
                    )
                    effective_status = (
                        "RESOLVED"
                        if (redirected_from is not None and effective_target_id in resolved_article_ids)
                        else c.status
                    )
                    cit_data.append(
                        {
                            "source_id": c.source_article_id,
                            "target_id": effective_target_id,
                            "redirected_from": redirected_from,
                            "citation_text": c.citation_text,
                            "status": effective_status,
                            "raw_target_number": c.raw_target_number,
                            "target_law_id": effective_law_id,
                            "target_clause_id": getattr(c, "target_clause_id", None),
                            "target_clause_ref": getattr(c, "target_clause_ref", None),
                            "ingestion_run_id": self.run_id,
                            "source_hash": source_hash,
                        }
                    )
                self.bridge.execute_apoc_batch(
                    f"""
                    MERGE (target:Article {{id: item.target_id}})
                    ON CREATE SET
                        target.id = item.target_id,
                        target.number = item.raw_target_number,
                        target.law_id = item.target_law_id,
                        target.status = 'unresolved',
                        target.raw_text = null,
                        target.normalized_text = null,
                        target.created_at = datetime()
                    WITH target, item
                    OPTIONAL MATCH (tgt_law:Law {{id: item.target_law_id}})
                    FOREACH (_ IN CASE WHEN tgt_law IS NOT NULL AND target.status = 'unresolved' THEN [1] ELSE [] END |
                        MERGE (tgt_law)-[lc:CONTAINS]->(target)
                        SET lc.ingestion_run_id = coalesce(lc.ingestion_run_id, item.ingestion_run_id),
                            lc.source_hash = coalesce(lc.source_hash, item.source_hash)
                    )
                    WITH target, item
                    MATCH (source:Article {{id: item.source_id}})
                    MERGE (source)-[r:{rel_type} {{citation_text: item.citation_text}}]->(target)
                    ON CREATE SET
                        r.status = item.status,
                        r.created_at = datetime()
                    SET r.ingestion_run_id = item.ingestion_run_id,
                        r.source_hash = item.source_hash,
                        r.target_clause_ref = coalesce(item.target_clause_ref, r.target_clause_ref),
                        r.redirected_from = coalesce(item.redirected_from, r.redirected_from),
                        r.redirected_at = CASE WHEN item.redirected_from IS NOT NULL THEN datetime() ELSE r.redirected_at END
                    WITH source, item
                    OPTIONAL MATCH (tgt_clause:Clause {{id: item.target_clause_id}})
                    FOREACH (_ IN CASE WHEN tgt_clause IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (source)-[rc:{rel_type} {{citation_text: item.citation_text}}]->(tgt_clause)
                        SET rc.status = item.status,
                            rc.target_clause_ref = item.target_clause_ref,
                            rc.ingestion_run_id = item.ingestion_run_id,
                            rc.source_hash = item.source_hash
                    )
                    """,
                    cit_data,
                )

        # 6. Remediate Pre-existing Cross-Law Placeholders & Link Canonical Inter-Law Graph
        remediation_metrics = self.remediate_cross_law_placeholders(source_hash=source_hash)
        inter_law_metrics = self.link_inter_law_relations(source_hash=source_hash)

        # 7. Canonical Concept Taxonomy + Full Article & Clause Semantic/Deontic Enrichment
        semantic_metrics: Dict[str, Any] = {"enabled": False}
        if enable_semantic_enrichment:
            semantic_metrics = self.enrich_semantic_and_deontic_layer(
                articles=articles,
                source_hash=source_hash,
                batch_size=max(50, min(batch_size, 200)),
            )

        # 8. Finalize IngestionRun Status
        duration = time.time() - start_time
        final_status = "COMPLETED_WITH_ERRORS" if has_dlq else "COMPLETED"
        self.bridge.execute(
            """
            MATCH (r:IngestionRun {id: $run_id})
            SET r.completed_at = datetime(),
                r.status = $status,
                r.duration_sec = $duration_sec,
                r.laws_count = $laws_count,
                r.chapters_count = $chapters_count,
                r.articles_count = $articles_count,
                r.citations_count = $citations_count,
                r.semantic_enrichment_enabled = $semantic_enabled,
                r.semantic_concepts_count = $concepts_count,
                r.semantic_assertions_count = $assertions_count,
                r.semantic_decompositions_count = $decompositions_count;
            """,
            {
                "run_id": self.run_id,
                "status": final_status,
                "duration_sec": round(duration, 2),
                "laws_count": len(laws),
                "chapters_count": len(chapters),
                "articles_count": len(articles),
                "citations_count": len(citations),
                "semantic_enabled": bool(enable_semantic_enrichment),
                "concepts_count": int(semantic_metrics.get("concepts_total", 0)),
                "assertions_count": int(semantic_metrics.get("accepted_assertions", 0)),
                "decompositions_count": int(semantic_metrics.get("decompositions_count", 0)),
            },
        )

        # 9. Compute Fingerprint
        fingerprint = self.compute_graph_fingerprint()
        logger.info(f"✅ Ingestion finalized in {duration:.2f}s. Graph Fingerprint: {fingerprint}")
        return {
            "status": final_status,
            "run_id": self.run_id,
            "duration_sec": duration,
            "fingerprint": fingerprint,
            "remediation": remediation_metrics,
            "inter_law": inter_law_metrics,
            "semantic_enrichment": semantic_metrics,
        }

    ALLOWED_CITATION_RELATIONSHIP_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"REFERENCES", "AMENDS", "REPEALS"}
    )
    ALLOWED_INTER_LAW_RELATIONSHIP_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"AMENDS", "SUPERSEDES", "MANDATES_COMPLIANCE", "EXTENDS"}
    )

    @classmethod
    def _group_citations_by_relationship_type(cls, citations):
        """Fail-closed grouping of citations by their semantic relationship type.

        The relationship type is interpolated into Cypher, so anything outside
        the ontology-approved whitelist must abort ingestion, not be coerced.
        """
        grouped: Dict[str, List[CanonicalCitation]] = {}
        for c in citations:
            if c.citation_type not in cls.ALLOWED_CITATION_RELATIONSHIP_TYPES:
                raise ValueError(
                    f"Fail-closed: citation {c.source_article_id}->{c.target_article_id} "
                    f"has non-whitelisted relationship type {c.citation_type!r}"
                )
            grouped.setdefault(c.citation_type, []).append(c)
        return grouped

    @staticmethod
    def _parse_single_int_output(output: str, default: int = 0) -> int:
        lines = output.strip().splitlines()
        if not lines:
            return default
        record = ast.literal_eval(lines[-1])
        if isinstance(record, dict) and record:
            value = next(iter(record.values()))
            if isinstance(value, int):
                return value
        return default

    def remediate_cross_law_placeholders(
        self,
        *,
        source_hash: str = "",
    ) -> Dict[str, int]:
        """Redirect pre-existing misdirected cross-law stubs & prune isolated phantoms."""
        logger.info("🧹 Remediating cross-law citation placeholders via canonical registry...")
        redirect_rows = [
            {
                "ph_id": ph_id,
                "tgt_id": tgt_id,
                "tgt_law_id": derive_law_id_from_node_id(tgt_id),
                "tgt_number": tgt_id.split(":")[3] if len(tgt_id.split(":")) >= 4 else "",
                "run_id": self.run_id,
                "source_hash": source_hash,
            }
            for ph_id, tgt_id in KNOWN_CROSS_LAW_REDIRECTS.items()
        ]
        redirected_edges = 0
        for rel_type in sorted(self.ALLOWED_CITATION_RELATIONSHIP_TYPES):
            out = self.bridge.execute_apoc_batch(
                f"""
                MATCH (src:Article)-[r:{rel_type}]->(ph:Article {{id: item.ph_id}})
                MERGE (tgt:Article {{id: item.tgt_id}})
                ON CREATE SET
                    tgt.law_id = item.tgt_law_id,
                    tgt.number = item.tgt_number,
                    tgt.status = 'unresolved',
                    tgt.raw_text = null,
                    tgt.normalized_text = null,
                    tgt.created_at = datetime()
                WITH src, r, tgt, item
                OPTIONAL MATCH (tgt_law:Law {{id: item.tgt_law_id}})
                FOREACH (_ IN CASE WHEN tgt_law IS NOT NULL AND tgt.status = 'unresolved' THEN [1] ELSE [] END |
                    MERGE (tgt_law)-[lc:CONTAINS]->(tgt)
                    SET lc.ingestion_run_id = coalesce(lc.ingestion_run_id, item.run_id),
                        lc.source_hash = coalesce(lc.source_hash, item.source_hash)
                )
                WITH src, r, tgt, item
                MERGE (src)-[new_r:{rel_type} {{citation_text: coalesce(r.citation_text, '')}}]->(tgt)
                SET new_r = properties(r),
                    new_r.redirected_from = item.ph_id,
                    new_r.redirected_at = datetime(),
                    new_r.ingestion_run_id = coalesce(r.ingestion_run_id, item.run_id),
                    new_r.source_hash = coalesce(r.source_hash, item.source_hash)
                DELETE r
                RETURN count(new_r) AS cnt
                """,
                redirect_rows,
            )
            for line in out.strip().splitlines():
                try:
                    rec = ast.literal_eval(line)
                    if isinstance(rec, dict):
                        redirected_edges += int(rec.get("cnt", 0))
                except (ValueError, SyntaxError):
                    continue

        prune_out = self.bridge.execute(
            """
            MATCH (ph:Article {status: 'unresolved'})
            WHERE NOT ()-[:REFERENCES|AMENDS|REPEALS]->(ph)
              AND NOT (ph)-[:REFERENCES|AMENDS|REPEALS]->()
            DETACH DELETE ph
            RETURN count(ph) AS deleted;
            """
        )
        deleted_stubs = self._parse_single_int_output(prune_out, default=0)
        return {"redirected_edges": redirected_edges, "deleted_stubs": deleted_stubs}

    def link_inter_law_relations(self, *, source_hash: str = "") -> Dict[str, int]:
        """Enrich registered Law metadata, link inter-law relations, and resolve placeholders."""
        logger.info("🔗 Enriching Law metadata & linking canonical inter-law relations...")

        # 1. Batch-enrich registered Law metadata (title, enactment_date, hierarchy_level, specificity_level)
        law_meta_rows = [
            {"law_id": law_id, **meta}
            for law_id, meta in iter_all_law_metadata()
        ]
        meta_out = self.bridge.execute_apoc_batch(
            """
            MATCH (l:Law {id: item.law_id})
            SET l.title = coalesce(item.title, l.title, l.name),
                l.name = coalesce(l.name, item.name, item.title),
                l.enactment_date = item.enactment_date,
                l.hierarchy_level = item.hierarchy_level,
                l.specificity_level = item.specificity_level,
                l.updated_at = datetime()
            RETURN count(l) AS cnt
            """,
            law_meta_rows,
        )
        laws_enriched = sum(
            int(rec.get("cnt", 0))
            for rec in (
                ast.literal_eval(ln)
                for ln in meta_out.strip().splitlines()
                if ln.strip()
            )
            if isinstance(rec, dict)
        )

        # 2. Canonical inter-law relationships (AMENDS, SUPERSEDES, MANDATES_COMPLIANCE, EXTENDS)
        inter_law_count = 0
        for link in CANONICAL_INTER_LAW_LINKS:
            if link.relationship_type not in self.ALLOWED_INTER_LAW_RELATIONSHIP_TYPES:
                raise ValueError(
                    f"Fail-closed: non-whitelisted inter-law relation {link.relationship_type!r}"
                )
            link_out = self.bridge.execute(
                f"""
                MATCH (s:Law {{id: $src_id}})
                WITH s
                MATCH (t:Law {{id: $tgt_id}})
                MERGE (s)-[r:{link.relationship_type}]->(t)
                ON CREATE SET r.created_at = datetime()
                SET r += $props,
                    r.ingestion_run_id = coalesce(r.ingestion_run_id, $run_id),
                    r.source_hash = coalesce(r.source_hash, $source_hash),
                    r.updated_at = datetime()
                RETURN count(r) AS cnt;
                """,
                {
                    "src_id": link.source_law_id,
                    "tgt_id": link.target_law_id,
                    "props": link.properties,
                    "run_id": self.run_id,
                    "source_hash": source_hash,
                },
            )
            inter_law_count += self._parse_single_int_output(link_out, default=0)

        # 3. Resolve placeholder article:commercial_code:article:51 from article:commercial_code_full:article:51
        self.bridge.execute(
            """
            MATCH (full_art:Article {id: 'article:commercial_code_full:article:51'})
            WITH full_art
            MATCH (base_art:Article {id: 'article:commercial_code:article:51'})
            SET base_art.raw_text = full_art.raw_text,
                base_art.normalized_text = full_art.normalized_text,
                base_art.text_hash = full_art.text_hash,
                base_art.source_file = full_art.source_file,
                base_art.source_line_start = full_art.source_line_start,
                base_art.source_line_end = full_art.source_line_end,
                base_art.source_char_start = full_art.source_char_start,
                base_art.source_char_end = full_art.source_char_end,
                base_art.parser_version = full_art.parser_version,
                base_art.schema_version = full_art.schema_version,
                base_art.status = 'resolved',
                base_art.resolved_from = full_art.id,
                base_art.updated_at = datetime()
            WITH base_art
            MATCH (c:Chapter {id: 'chapter:commercial_code:general'})
            MERGE (c)-[r:CONTAINS]->(base_art)
            SET r.ingestion_run_id = coalesce(r.ingestion_run_id, $run_id),
                r.source_hash = coalesce(r.source_hash, $source_hash);
            """,
            {"run_id": self.run_id, "source_hash": source_hash},
        )

        # 4. Cross-statute Article [:AMENDS] (1347 Amendment -> 1311 Commercial Code)
        amends_out = self.bridge.execute(
            """
            MATCH (a:Article)
            WHERE a.amendment_info IS NOT NULL AND a.status = 'resolved'
              AND a.law_id = 'law:commercial_amendment_1347'
            WITH a
            MATCH (prior:Article {law_id: 'law:commercial_code_1311', number: a.number})
            MERGE (a)-[r:AMENDS]->(prior)
            ON CREATE SET r.created_at = datetime(),
                          r.amendment_type = a.amendment_info,
                          r.confidence = 0.95,
                          r.extractor = 'amendment_extractor'
            SET r.ingestion_run_id = coalesce(r.ingestion_run_id, $run_id),
                r.source_hash = coalesce(r.source_hash, $source_hash)
            RETURN count(r) AS cnt;
            """,
            {"run_id": self.run_id, "source_hash": source_hash},
        )
        article_amends = self._parse_single_int_output(amends_out, default=0)

        # 5. Explicit statutory [:REPEALS] in Check Law (Art. 23 -> Art. 4)
        repeals_out = self.bridge.execute(
            """
            MATCH (s:Article), (t:Article)
            WHERE s.id IN ['article:check_law:article:23', 'law:check_law:article:23']
              AND t.id IN ['article:check_law:article:4', 'law:check_law:article:4']
            MERGE (s)-[r:REPEALS]->(t)
            ON CREATE SET r.created_at = datetime(),
                          r.repeal_type = 'explicit_repeal',
                          r.confidence = 0.95,
                          r.extractor = 'repeal_extractor'
            SET r.ingestion_run_id = coalesce(r.ingestion_run_id, $run_id),
                r.source_hash = coalesce(r.source_hash, $source_hash)
            RETURN count(r) AS cnt;
            """,
            {"run_id": self.run_id, "source_hash": source_hash},
        )
        article_repeals = self._parse_single_int_output(repeals_out, default=0)

        return {
            "laws_enriched": laws_enriched,
            "inter_law_links": inter_law_count,
            "article_amends": article_amends,
            "article_repeals": article_repeals,
        }

    def enrich_semantic_and_deontic_layer(
        self,
        articles: List[CanonicalArticle],
        *,
        source_hash: str = "",
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """Materialize canonical Concept taxonomy plus Article & Clause decompositions/norms/links."""
        logger.info("🧠 Materializing Concept Taxonomy + Article & Clause Semantic/Deontic Graph...")
        extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)
        materializer = BatchedSemanticMaterializer(ontology=CANONICAL_LEGAL_CONCEPTS)

        ontology_stmts = materializer.build_batched_ontology_statements()
        decompositions = []
        raw_assertions = []
        clauses_processed = 0

        for art in articles:
            art_text = art.normalized_text or art.raw_text or ""
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

            for clause in art.clauses:
                clause_text = clause.normalized_text or clause.raw_text or ""
                if not clause_text.strip():
                    continue
                clauses_processed += 1
                decompositions.append(
                    extractor.decompose_article(
                        article_id=clause.id,
                        law_id=clause.law_id,
                        raw_text=clause_text,
                    )
                )
                raw_assertions.extend(
                    extractor.extract_concept_assertions(
                        article_id=clause.id,
                        raw_text=clause_text,
                    )
                )

        accepted_assertions = materializer.accept_extracted_assertions(
            raw_assertions,
            decompositions=decompositions,
            extractor=extractor,
        )
        decomp_stmts = materializer.build_batched_decompositions(decompositions)
        deontic_stmts = materializer.build_batched_deontic_norms(decompositions)
        assertion_stmts = materializer.build_batched_assertions(accepted_assertions)

        all_stmts = [
            *ontology_stmts,
            *decomp_stmts,
            *deontic_stmts,
            *assertion_stmts,
        ]
        receipt = self.bridge.execute_batched_materialization(
            materializer,
            all_stmts,
            batch_size=batch_size,
        )

        conditions_count = sum(len(d.conditions) for d in decompositions)
        exceptions_count = sum(len(d.exceptions) for d in decompositions)
        sanctions_count = sum(len(d.sanctions) for d in decompositions)
        deontic_count = sum(len(getattr(d, "deontic_norms", [])) for d in decompositions)
        return {
            "enabled": True,
            "concepts_total": len(CANONICAL_LEGAL_CONCEPTS),
            "articles_processed": len(articles),
            "clauses_processed": clauses_processed,
            "decompositions_count": len(decompositions),
            "conditions_extracted": conditions_count,
            "exceptions_extracted": exceptions_count,
            "sanctions_extracted": sanctions_count,
            "deontic_norms_extracted": deontic_count,
            "raw_assertions": len(raw_assertions),
            "accepted_assertions": len(accepted_assertions),
            "statements_executed": len(all_stmts),
            "materialization_hash": getattr(receipt, "content_hash", "") if receipt is not None else "",
        }

    def compute_graph_fingerprint(self) -> str:
        """Compute cryptographic graph fingerprint."""
        hasher = hashlib.sha256()
        out_nodes = self.bridge.execute(
            "MATCH (n) WHERE NOT n:IngestionRun RETURN labels(n)[0] AS lbl, n.id AS id, coalesce(n.text_hash, '') AS th ORDER BY n.id"
        )
        hasher.update(out_nodes.encode("utf-8"))

        out_rels = self.bridge.execute(
            "MATCH (a)-[r]->(b) WHERE NOT a:IngestionRun AND NOT b:IngestionRun RETURN a.id AS src, type(r) AS rel, b.id AS dst ORDER BY a.id, type(r), b.id"
        )
        hasher.update(out_rels.encode("utf-8"))
        return hasher.hexdigest()

    def run_integrity_audit(self) -> Dict[str, Any]:
        """Execute forensic integrity queries."""
        logger.info("🔍 Running Forensic Integrity Audit Queries...")
        audit_results = {}

        def count_result(output: str) -> int:
            """Read the scalar count from the bridge's serialized Neo4j record."""
            lines = output.strip().splitlines()
            if not lines:
                return 0
            record = ast.literal_eval(lines[-1])
            if not isinstance(record, dict) or len(record) != 1:
                raise ValueError(f"Unexpected count query result: {lines[-1]!r}")
            value = next(iter(record.values()))
            if not isinstance(value, int):
                raise ValueError(f"Count query returned non-integer value: {value!r}")
            return value

        # 1. Duplicates
        out_dup = self.bridge.execute("MATCH (n) WITH n.id AS id, count(n) AS c WHERE c > 1 RETURN count(id);")
        audit_results["duplicate_canonical_ids"] = count_result(out_dup)

        # 2. Strict Single-Parent Structural Hierarchy (Must be 0)
        out_par = self.bridge.execute(
            """
            MATCH (a:Article {status: 'resolved'})
            OPTIONAL MATCH (c:Chapter)-[:CONTAINS]->(a)
            WITH a, count(c) AS parents
            WHERE parents <> 1
            RETURN count(a);
            """
        )
        audit_results["hierarchy_parent_violations"] = count_result(out_par)

        # 3. Referential Consistency
        out_ref = self.bridge.execute(
            """
            MATCH (a:Article)-[:REFERENCES]->(b:Article)
            WHERE b.status IS NULL OR NOT b.status IN ['resolved', 'unresolved']
            RETURN count(a);
            """
        )
        audit_results["referential_violations"] = count_result(out_ref)

        # 4. Placeholder Hygiene
        out_place = self.bridge.execute(
            """
            MATCH (a:Article {status: 'unresolved'})
            WHERE a.raw_text IS NOT NULL AND size(a.raw_text) > 0
            RETURN count(a);
            """
        )
        audit_results["unresolved_placeholder_violations"] = count_result(out_place)

        # 5. Provenance Completeness
        out_prov = self.bridge.execute(
            """
            MATCH (a:Article {status: 'resolved'})
            WHERE a.text_hash IS NULL OR a.source_file IS NULL OR a.source_line_start IS NULL
            RETURN count(a);
            """
        )
        audit_results["incomplete_provenance_count"] = count_result(out_prov)

        # 6. Relationship Provenance Completeness
        out_rel_prov = self.bridge.execute(
            f"""
            MATCH ()-[r:CONTAINS|REFERENCES]->()
            WHERE (startNode(r).ingestion_run_id = '{self.run_id}'
                OR endNode(r).ingestion_run_id = '{self.run_id}')
              AND (r.ingestion_run_id IS NULL OR r.source_hash IS NULL)
            RETURN count(r);
            """
        )
        audit_results["incomplete_relationship_provenance_count"] = count_result(
            out_rel_prov
        )

        # 7. Graph Summary Counts
        counts_cypher = """
        RETURN
            COUNT { MATCH (:Law) } AS laws,
            COUNT { MATCH (:Chapter) } AS chapters,
            COUNT { MATCH (a:Article {status: 'resolved'}) } AS resolved_articles,
            COUNT { MATCH (a:Article {status: 'unresolved'}) } AS unresolved_articles,
            COUNT { MATCH (:Clause) } AS clauses,
            COUNT { MATCH ()-[:REFERENCES]->() } AS references_count,
            COUNT { MATCH ()-[:CONTAINS]->() } AS contains_count;
        """
        counts_out = self.bridge.execute(counts_cypher)
        lines = counts_out.strip().splitlines()
        audit_results["graph_counts_raw"] = lines[-1] if lines else ""

        audit_results["audit_passed"] = (
            audit_results["duplicate_canonical_ids"] == 0
            and audit_results["hierarchy_parent_violations"] == 0
            and audit_results["referential_violations"] == 0
            and audit_results["unresolved_placeholder_violations"] == 0
            and audit_results["incomplete_provenance_count"] == 0
            and audit_results["incomplete_relationship_provenance_count"] == 0
        )
        return audit_results


# ============================================================================
# 6. Source Dataset Integrity Verification
# ============================================================================

def verify_source_file(file_path: Path) -> Tuple[bool, str, int, Optional[str]]:
    """
    Verify pre-ingestion source file integrity:
    1. File existence
    2. Valid UTF-8 encoding without decode exceptions
    3. Absence of binary control characters (except \\n, \\r, \\t)
    4. Exact SHA-256 calculation
    """
    if not file_path.is_file():
        return False, "", 0, f"Source file does not exist: {file_path}"

    try:
        raw_bytes = file_path.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        decoded_text = raw_bytes.decode("utf-8")
        line_count = len(decoded_text.splitlines())

        for ch in decoded_text:
            code = ord(ch)
            if code < 32 and code not in (9, 10, 13):
                return False, sha256, line_count, f"Corrupted control character U+{code:04X} detected"

        return True, sha256, line_count, None
    except UnicodeDecodeError as ude:
        return False, "", 0, f"UTF-8 decode failed: {ude}"
    except Exception as exc:
        return False, "", 0, f"Source validation error: {exc}"


def _print_panel(title: str, rows: List[Tuple[str, Any]], width: int = 80) -> None:
    """Print a beautiful, consistent CLI panel for ingestion status."""
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    for label, value in rows:
        label_str = f"  {label}:"
        value_str = str(value)
        print(f"{label_str:<35} {value_str}")
    print(f"{'=' * width}\n")

def _print_section(title: str, emoji: str = "📋") -> None:
    """Print a section header with emoji."""
    print(f"\n{emoji} {title}")
    print(f"{'─' * 80}")

def _print_success(message: str) -> None:
    """Print a success message."""
    print(f"✅ {message}")

def _print_error(message: str) -> None:
    """Print an error message."""
    print(f"❌ {message}")

def _print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"⚠️  {message}")

def _print_info(message: str) -> None:
    """Print an info message."""
    print(f"ℹ️  {message}")


# ============================================================================
# 7. CLI Entrypoint
# ============================================================================

def main() -> int:
    from scripts.graph_script_policy import classify_script, describe_script

    script_class = classify_script("build_legal_kg.py")
    descriptor = describe_script("build_legal_kg.py")

    if script_class.value == "forbidden-legacy-writer":
        from scripts.graph_script_policy import quarantine_legacy_writer
        quarantine_legacy_writer(
            "build_legal_kg.py",
            descriptor.canonical_handoff,
        )

    IngestionExecutionGate.require_active()
    parser = argparse.ArgumentParser(
        description="Deterministic Legal Corpus Compiler & Knowledge Graph Ingestion Engine"
    )
    parser.add_argument(
        "--file",
        "--source",
        dest="file",
        type=str,
        default="LAWS/all_legal_sentences.txt",
        help="Path to legal sentences text file",
    )
    parser.add_argument(
        "--default-law-id",
        type=str,
        default=None,
        help="Optional explicit default law ID (e.g. law:commercial_code_full)",
    )
    parser.add_argument(
        "--default-law-name",
        type=str,
        default=None,
        help="Optional explicit default law title",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Cypher mutation transaction batch size",
    )
    parser.add_argument(
        "--target-uri",
        type=str,
        default=os.getenv("NEO4J_URI", "bolt://localhost:7688"),
        help="Target Neo4j Bolt URI (default: Staging bolt://localhost:7688)",
    )
    parser.add_argument(
        "--start-line",
        type=int,
        default=None,
        help="Optional 1-based start line for composite legal files",
    )
    parser.add_argument(
        "--end-line",
        type=int,
        default=None,
        help="Optional 1-based end line for composite legal files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without mutating Neo4j",
    )
    parser.add_argument(
        "--use-canonical-api",
        action="store_true",
        help="Use canonical API ingestion path instead of direct Neo4j mutation",
    )
    parser.add_argument(
        "--allow-direct-fallback",
        action="store_true",
        help="Permit fallback to direct Staging Neo4j compilation if canonical API fails",
    )
    parser.add_argument(
        "--skip-semantic-enrichment",
        action="store_true",
        help="Skip Concept taxonomy & Article/Clause semantic/deontic decomposition pass",
    )
    parser.add_argument(
        "--allow-dlq",
        action="store_true",
        help="Permit execution with DLQ errors (sets status to COMPLETED_WITH_ERRORS)",
    )
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="Allow a source with no Article headers to ingest as one fully-provenanced Law node",
    )
    parser.add_argument(
        "--instrument-type",
        choices=[item.value for item in LegalInstrumentType],
        default=LegalInstrumentType.STATUTE.value,
        help="Normative instrument type stored on the Law node",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional explicit ingestion run ID",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    parser.add_argument(
        "--compiler",
        choices=["regex", "ast"],
        default="regex",
        help="Legal parsing engine: 'regex' (legacy regex parser) or 'ast' (Context-Free Grammar AST compiler)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    source_path = Path(args.file).resolve()
    _print_section("MAHOUN LEGAL CORPUS COMPILER", "🏛️")
    _print_panel(
        "INGESTION CONFIGURATION",
        [
            ("Source File", source_path),
            ("Mode", "DRY-RUN (no Neo4j mutations)" if args.dry_run else "INGEST"),
            ("Ingestion Path", "Canonical API" if args.use_canonical_api else "Direct Neo4j"),
            ("Batch Size", args.batch_size),
            ("Script Classification", script_class.value),
        ],
    )

    # 1. Source File Integrity Verification
    _print_section("Source File Integrity Verification", "🔍")
    valid_file, source_sha256, file_lines, err = verify_source_file(source_path)
    if not valid_file:
        _print_error(f"Source File Integrity Violation: {err}")
        return 1

    _print_success(f"Source integrity verified: {file_lines} lines | SHA-256: {source_sha256[:16]}...")

    # 2. Parse Corpus & Extract Line Records
    _print_section("Parsing Legal Corpus", "📖")
    if getattr(args, "compiler", "regex") == "ast":
        _print_section("Formal AST Legal Compiler (Lark CFG)", "🌲")
        from mahoun.pipelines.legal_compiler.lark_parser import LegalCompilerLarkEngine
        from mahoun.pipelines.legal_compiler.ast_to_canonical_adapter import ASTToCanonicalAdapter

        with open(source_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        if args.start_line is not None or args.end_line is not None:
            s_idx = (args.start_line - 1) if args.start_line else 0
            e_idx = args.end_line if args.end_line else len(all_lines)
            corpus_text = "".join(all_lines[s_idx:e_idx])
        else:
            corpus_text = "".join(all_lines)

        d_law_id = args.default_law_id or "law:compiled_corpus"
        ast_compiler = LegalCompilerLarkEngine()
        ast_law = ast_compiler.compile(corpus_text, default_law_id=d_law_id)
        adapter = ASTToCanonicalAdapter(source_path=source_path)
        laws, chapters, articles, citations, records, stats = adapter.to_canonical(ast_law)
        clauses = [clause for article in articles for clause in article.clauses]
        _print_success(f"AST Legal Compiler executed successfully: {len(articles)} articles parsed with complete line accounting")
    else:
        corpus_parser = LegalCorpusParser(
            source_path,
            default_law_id=args.default_law_id,
            default_law_name=args.default_law_name,
            source_only=args.source_only,
            instrument_type=LegalInstrumentType(args.instrument_type),
            start_line=args.start_line,
            end_line=args.end_line,
        )
        laws, chapters, articles, citations, records, stats = corpus_parser.parse()
        # The parser stores clauses on their parent articles; flatten them for the
        # canonical converter without discarding the extracted semantic units.
        clauses = [clause for article in articles for clause in article.clauses]
        _print_success("Corpus parsed successfully")

    # 3. Line Accounting Invariant Check
    _print_section("Line Accounting Validation", "✓")
    if not stats.verify_line_accounting_invariant():
        _print_error("Line accounting invariant failed!")
        return 1
    _print_success("Line accounting invariant verified")

    # 4. Handle DLQ Records
    _print_section("Dead Letter Queue (DLQ) Check", "📬")
    dlq_records = [r for r in records if r.classification in ("UNPARSED", "INVALID")]
    has_dlq = len(dlq_records) > 0
    if has_dlq:
        dlq_log_path = REPO_ROOT / "unparsed_lines.log"
        with open(dlq_log_path, "w", encoding="utf-8") as dlq_f:
            for r in dlq_records:
                dlq_f.write(json.dumps({
                    "source_line_index": r.source_line_index,
                    "classification": r.classification,
                    "raw_text": r.raw_text,
                    "failure_reason": r.failure_reason,
                    "parser_version": PARSER_VERSION,
                }, ensure_ascii=False) + "\n")
        _print_warning(f"DLQ Emitted: {len(dlq_records)} records written to {dlq_log_path}")

        if not args.allow_dlq:
            _print_error("Fail-Closed: Ingestion aborted due to DLQ violations without --allow-dlq")
            return 1
    else:
        _print_success("No DLQ records - all lines parsed successfully")

    _print_section("Parse Metrics Summary", "📊")
    _print_panel(
        "CORPUS STATISTICS",
        [
            ("Input Lines", stats.total_lines),
            ("Recognized Entities", stats.recognized_entity_lines),
            ("Metadata Lines", stats.recognized_metadata_lines),
            ("Formatting Lines", stats.ignorable_formatting_lines),
            ("DLQ Records", stats.dlq_count),
            ("Laws Extracted", stats.laws_count),
            ("Chapters Extracted", stats.chapters_count),
            ("Articles Extracted", stats.articles_count),
            ("Clauses Extracted", stats.clauses_count),
            ("Resolved Citations", stats.resolved_citations),
            ("Unresolved Citations", stats.unresolved_citations),
            ("Ambiguous Citations", stats.ambiguous_citations),
            ("Amended Citations", stats.amended_citations),
            ("Repealed Citations", stats.repealed_citations),
            ("Source SHA-256", f"{source_sha256[:16]}..."),
        ],
    )

    if args.dry_run:
        if not articles and not args.source_only:
            _print_error("Fail-Closed: no Article headers found; rerun only with explicit --source-only")
            return 1
        _print_section("Dry-Run Mode", "🔒")
        _print_success("Dry-run completed successfully. No mutations performed on Neo4j.")
        return 0

    # 6. Canonical API Ingestion Path (NEW - replaces direct Neo4j mutation)
    if args.use_canonical_api:
        _print_section("Canonical API Ingestion", "🌐")
        _print_info("Using Canonical API ingestion path...")

        try:
            from scripts.canonical_batch_converter import CanonicalBatchConverter
            from scripts.cli_auth_helper import ensure_cli_token, get_cli_actor_id

            # Ensure CLI authentication token is available
            _ = ensure_cli_token()
            _print_success("CLI authentication token obtained")

            # Create converter
            converter = CanonicalBatchConverter(parser_version=PARSER_VERSION)

            # Generate correlation ID
            correlation_id = f"build_legal_kg_{int(time.time())}"
            actor_id = get_cli_actor_id()

            # Convert to canonical batch with 4-fold enrichment when enabled
            _print_info("Converting legacy IR to canonical batch...")
            batch_request = converter.convert_legal_corpus(
                laws=laws,
                chapters=chapters,
                articles=articles,
                clauses=clauses,
                citations=citations,
                source_file=str(source_path.name),
                correlation_id=correlation_id,
                author_id=actor_id,
                include_semantic_enrichment=not getattr(args, "skip_semantic_enrichment", False),
            )
            _print_success("Canonical batch converted successfully")

            # Submit to API
            _print_info("Submitting to canonical API...")
            api_response = converter.submit_to_api(batch_request)

            _print_section("Canonical API Ingestion Result", "✨")
            _print_panel(
                "API RESPONSE METRICS",
                [
                    ("Status", api_response.get("status", "unknown")),
                    ("Correlation ID", api_response.get("correlation_id", correlation_id)),
                    ("Documents Processed", len(api_response.get("document_ids", []))),
                    ("Facts Created", api_response.get("fact_count", 0)),
                    ("Relationships Created", api_response.get("relationship_count", 0)),
                    ("Receipts Generated", len(api_response.get("receipts", []))),
                ],
            )

            _print_section("Final Summary", "🎯")
            _print_panel(
                "INGESTION COMPLETE",
                [
                    ("Source File", source_path.name),
                    ("Total Lines", stats.total_lines),
                    ("Articles Extracted", stats.articles_count),
                    ("Facts Created", api_response.get("fact_count", 0)),
                    ("Relationships Created", api_response.get("relationship_count", 0)),
                    ("Ingestion Path", "Canonical API"),
                    ("Status", "SUCCESS"),
                ],
            )

            _print_success("Canonical API ingestion completed successfully")
            return 0

        except Exception as e:
            _print_error(f"Canonical API ingestion failed: {e}")
            if not getattr(args, "allow_direct_fallback", False):
                _print_error(
                    "Fail-Closed: Canonical API ingestion aborted without --allow-direct-fallback."
                )
                return 1
            _print_warning("Falling back to direct governed Staging compilation...")

    # 6. Direct Governed Database Compilation & Semantic Enrichment
    target_uri = getattr(args, "target_uri", "bolt://localhost:7688")
    if "7687" in target_uri:
        raise RuntimeError(
            "FAIL-CLOSED: Refusing to mutate Production on port 7687! Target must be Staging (port 7688)."
        )
    connection = get_connection(uri=target_uri)
    compiler = HardenedKnowledgeGraphCompiler(run_id=args.run_id, connection=connection)

    res = compiler.compile(
        laws=laws,
        chapters=chapters,
        articles=articles,
        citations=citations,
        source_hash=source_sha256,
        source_file=str(source_path.name),
        batch_size=args.batch_size,
        has_dlq=has_dlq,
        enable_semantic_enrichment=not getattr(args, "skip_semantic_enrichment", False),
    )

    # 7. Post-Ingestion Forensic Integrity Audit
    audit = compiler.run_integrity_audit()
    semantic_info = res.get("semantic_enrichment") or {}
    inter_law_info = res.get("inter_law") or {}
    remediation_info = res.get("remediation") or {}
    _print_panel(
        "POST-INGESTION FORENSIC AUDIT",
        [
            ("Duplicate canonical IDs", audit["duplicate_canonical_ids"]),
            ("Parent hierarchy violations", audit["hierarchy_parent_violations"]),
            ("Referential violations", audit["referential_violations"]),
            ("Placeholder violations", audit["unresolved_placeholder_violations"]),
            ("Incomplete provenance", audit["incomplete_provenance_count"]),
            ("Redirected cross-law edges", remediation_info.get("redirected_edges", 0)),
            ("Pruned phantom stubs", remediation_info.get("deleted_stubs", 0)),
            ("Inter-law links ensured", inter_law_info.get("inter_law_links", 0)),
            ("Semantic decomposition units", semantic_info.get("decompositions_count", 0)),
            ("Verified REGULATES assertions", semantic_info.get("accepted_assertions", 0)),
            ("Audit result", "✅ PASS" if audit["audit_passed"] else "❌ FAIL"),
            ("Graph summary", audit.get("graph_counts_raw", "")),
            ("Graph fingerprint", res["fingerprint"]),
        ],
    )

    if not audit["audit_passed"]:
        logger.error("❌ Post-ingestion audit failed!")
        return 1

    return 0


if __name__ == "__main__":
    from mahoun.core.governance.ingestion_execution_gate import (
        IngestionExecutionGate,
        IngestionExecutionRequest,
    )
    
    # Open the ingestion execution gate before running main
    request = IngestionExecutionRequest(
        source="build_legal_kg.py",
        author_id="build_legal_kg_script",
        correlation_id=f"build_legal_kg_{int(time.time())}",
        adapter_name="LegalCorpusParser",
        contract_version="1"
    )
    
    with IngestionExecutionGate.enter(request):
        sys.exit(main())
