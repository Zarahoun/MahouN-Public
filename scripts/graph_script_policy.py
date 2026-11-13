"""Classification and fail-closed policy for graph-related scripts.

Scripts may parse and emit a canonical producer payload, but they may not
materialize document data by issuing their own Cypher.  Existing materializers
are retained for migration work only and are quarantined from CLI execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GraphScriptClass(StrEnum):
    EXTRACTION_ONLY = "extraction-only"
    SERVER_PRODUCER = "server-producer"
    GOVERNED_MIGRATION = "governed-migration"
    FORBIDDEN_LEGACY_WRITER = "forbidden-legacy-writer"


class LegacyGraphWriterQuarantined(RuntimeError):
    """Raised when a legacy graph-writing CLI is invoked."""


@dataclass(frozen=True, slots=True)
class GraphScriptDescriptor:
    """Operational role and canonical hand-off for a graph-related script."""

    classification: GraphScriptClass
    document_family: str
    responsibility: str
    canonical_handoff: str
    dry_run_required: bool = True


GRAPH_SCRIPT_CLASSIFICATION: dict[str, GraphScriptClass] = {
    "build_judgment_kg.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "build_legal_kg.py": GraphScriptClass.SERVER_PRODUCER,
    "governed_relationship_enrichment.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "ingest_banking_laws.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "ingest_qachaq_and_customs_corpus.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "materialize_advanced_audit_pillars.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "materialize_phase_2b_semantic_graph.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "materialize_semantic_ultra.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "backfill_vectors.py": GraphScriptClass.GOVERNED_MIGRATION,
    "integrate_orphan_modules.py": GraphScriptClass.GOVERNED_MIGRATION,
    "load_knowledge_graph_parallel.py": GraphScriptClass.GOVERNED_MIGRATION,
    "kg_loader_enterprise.py": GraphScriptClass.GOVERNED_MIGRATION,
    "ingest_ara_judgments.py": GraphScriptClass.GOVERNED_MIGRATION,
    "run_full_forensic_audit.py": GraphScriptClass.EXTRACTION_ONLY,
    "run_preproduction_validation.py": GraphScriptClass.EXTRACTION_ONLY,
    "analyze_weak_modules.py": GraphScriptClass.EXTRACTION_ONLY,
    "backup.py": GraphScriptClass.GOVERNED_MIGRATION,
    "classify_tests.py": GraphScriptClass.EXTRACTION_ONLY,
    "classify_tests_serial.py": GraphScriptClass.EXTRACTION_ONLY,
    "clean_4311.py": GraphScriptClass.EXTRACTION_ONLY,
    "create_top_333.py": GraphScriptClass.EXTRACTION_ONLY,
    "quick_system_test.py": GraphScriptClass.EXTRACTION_ONLY,
    "restore.py": GraphScriptClass.GOVERNED_MIGRATION,
    "runtime_trace.py": GraphScriptClass.EXTRACTION_ONLY,
    "ultra_production_tracker.py": GraphScriptClass.EXTRACTION_ONLY,
    "validate_governance_compliance.py": GraphScriptClass.EXTRACTION_ONLY,
    "verify_governance.py": GraphScriptClass.EXTRACTION_ONLY,
    "verify_hajix.py": GraphScriptClass.EXTRACTION_ONLY,
    "version_dataset.py": GraphScriptClass.EXTRACTION_ONLY,
    "parse_ara_judgments.py": GraphScriptClass.EXTRACTION_ONLY,
    "extract_patent_docs.py": GraphScriptClass.EXTRACTION_ONLY,
    "pdf_to_clean_text.py": GraphScriptClass.EXTRACTION_ONLY,
    "prepare_banking_corpus.py": GraphScriptClass.EXTRACTION_ONLY,
    "consolidate_for_graph.py": GraphScriptClass.SERVER_PRODUCER,
    "unified_ingest.py": GraphScriptClass.SERVER_PRODUCER,
    "ingest_engineering_and_4311.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "simple_neo4j_ingest.py": GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
    "connect_slm_to_graph.py": GraphScriptClass.EXTRACTION_ONLY,
}

GRAPH_SCRIPT_DESCRIPTORS: dict[str, GraphScriptDescriptor] = {
    "build_legal_kg.py": GraphScriptDescriptor(
        GraphScriptClass.SERVER_PRODUCER,
        "statute",
        "parse and normalize hierarchical legal corpus",
        "POST /api/v1/ingest/canonical-batch",
    ),
    "parse_ara_judgments.py": GraphScriptDescriptor(
        GraphScriptClass.EXTRACTION_ONLY,
        "judgment",
        "parse judgment boundaries and metadata",
        "canonical ingestion batch",
    ),
    "build_judgment_kg.py": GraphScriptDescriptor(
        GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
        "judgment",
        "compile canonical judgment entities and references",
        "canonical ingestion batch",
    ),
    "ingest_banking_laws.py": GraphScriptDescriptor(
        GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
        "banking",
        "extract banking-law domain semantics",
        "canonical ingestion batch",
    ),
    "ingest_engineering_and_4311.py": GraphScriptDescriptor(
        GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
        "contract-4311",
        "extract contract and engineering-specific semantics",
        "canonical ingestion batch",
    ),
    "ingest_qachaq_and_customs_corpus.py": GraphScriptDescriptor(
        GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
        "customs-anti-smuggling",
        "extract customs and anti-smuggling corpus semantics",
        "canonical ingestion batch",
    ),
    "governed_relationship_enrichment.py": GraphScriptDescriptor(
        GraphScriptClass.FORBIDDEN_LEGACY_WRITER,
        "cross-domain",
        "validate and enrich evidence-backed relationships",
        "governed enrichment batch",
    ),
    "pdf_to_clean_text.py": GraphScriptDescriptor(
        GraphScriptClass.EXTRACTION_ONLY,
        "document-source",
        "normalize Persian legal PDF text",
        "specialized document adapter",
    ),
    "unified_ingest.py": GraphScriptDescriptor(
        GraphScriptClass.SERVER_PRODUCER,
        "all-supported",
        "dispatch a source to the selected specialized adapter",
        "GovernedIngestionRuntime",
    ),
}


def quarantine_legacy_writer(script_name: str, replacement: str) -> None:
    """Stop a legacy writer before it can open a graph mutation path."""

    raise LegacyGraphWriterQuarantined(
        f"{script_name} is quarantined as a {GraphScriptClass.FORBIDDEN_LEGACY_WRITER}; "
        f"emit a canonical producer manifest and submit it through {replacement}"
    )


def classify_script(script_name: str) -> GraphScriptClass:
    """Return a classification, failing closed for unknown graph scripts."""

    try:
        return GRAPH_SCRIPT_CLASSIFICATION[script_name]
    except KeyError as exc:
        raise KeyError(f"unclassified graph-related script: {script_name}") from exc


def describe_script(script_name: str) -> GraphScriptDescriptor:
    """Return the explicit role of a recent graph script, failing closed."""

    try:
        descriptor = GRAPH_SCRIPT_DESCRIPTORS[script_name]
    except KeyError as exc:
        raise KeyError(f"undescribed graph script: {script_name}") from exc
    if descriptor.classification != classify_script(script_name):
        raise RuntimeError(
            f"script policy mismatch for {script_name}: "
            f"{descriptor.classification} != {classify_script(script_name)}"
        )
    return descriptor
