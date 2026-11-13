from __future__ import annotations

import hashlib
import ast
from pathlib import Path

import pytest

from mahoun.core.governance.ingestion_contract import (
    CanonicalIngestionBatch,
    IngestionContractError,
    IngestionDocument,
    SourceSpan,
)
from scripts.graph_script_policy import (
    GRAPH_SCRIPT_DESCRIPTORS,
    GRAPH_SCRIPT_CLASSIFICATION,
    GraphScriptClass,
    LegacyGraphWriterQuarantined,
    classify_script,
    describe_script,
    quarantine_legacy_writer,
)


ROOT = Path(__file__).resolve().parents[2]


def test_every_registered_graph_script_exists_and_is_classified():
    for script_name, classification in GRAPH_SCRIPT_CLASSIFICATION.items():
        assert (ROOT / "scripts" / script_name).exists(), script_name
        assert classification in set(GraphScriptClass)


def test_unknown_graph_script_fails_closed():
    with pytest.raises(KeyError, match="unclassified"):
        classify_script("new_graph_writer.py")


def test_recent_specialized_scripts_have_explicit_handoff_roles():
    expected = {
        "build_legal_kg.py": "statute",
        "parse_ara_judgments.py": "judgment",
        "ingest_banking_laws.py": "banking",
        "ingest_qachaq_and_customs_corpus.py": "customs-anti-smuggling",
        "unified_ingest.py": "all-supported",
    }
    assert set(expected).issubset(GRAPH_SCRIPT_DESCRIPTORS)
    for script_name, document_family in expected.items():
        descriptor = describe_script(script_name)
        assert descriptor.document_family == document_family
        assert descriptor.canonical_handoff
        assert descriptor.dry_run_required


def test_undescribed_graph_script_fails_closed():
    with pytest.raises(KeyError, match="undescribed"):
        describe_script("new_graph_writer.py")


def test_legacy_writer_quarantine_is_not_an_opt_in_bypass():
    with pytest.raises(LegacyGraphWriterQuarantined, match="canonical producer"):
        quarantine_legacy_writer(
            "materialize_semantic_ultra.py",
            "POST /api/v1/ingest/canonical-batch",
        )


def test_forbidden_writer_clis_are_guarded_before_materialization():
    for script_name, classification in GRAPH_SCRIPT_CLASSIFICATION.items():
        if classification != GraphScriptClass.FORBIDDEN_LEGACY_WRITER:
            continue
        tree = ast.parse((ROOT / "scripts" / script_name).read_text(encoding="utf-8"))
        source = ast.unparse(tree)
        assert "quarantine_legacy_writer" in source, script_name


def _quarantine_call_ancestors(tree: ast.AST) -> dict[int, list[ast.AST]]:
    """Map each quarantine_legacy_writer call to its ancestor node chain."""

    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "quarantine_legacy_writer":
                calls.append(node)

    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    chains: dict[int, list[ast.AST]] = {}
    for call in calls:
        chain: list[ast.AST] = []
        cursor: ast.AST | None = parents.get(id(call))
        while cursor is not None:
            chain.append(cursor)
            cursor = parents.get(id(cursor))
        chains[id(call)] = chain
    return chains


def test_forbidden_writer_quarantine_is_unconditional_ast():
    """A quarantine call guarded by any condition (e.g. `if not dry_run:`)
    is a bypass vector: it must execute unconditionally, in every
    FORBIDDEN_LEGACY_WRITER script, and must never be swallowed by try/except.
    """
    for script_name, classification in GRAPH_SCRIPT_CLASSIFICATION.items():
        if classification != GraphScriptClass.FORBIDDEN_LEGACY_WRITER:
            continue
        tree = ast.parse((ROOT / "scripts" / script_name).read_text(encoding="utf-8"))
        chains = _quarantine_call_ancestors(tree)
        assert chains, f"{script_name}: no quarantine_legacy_writer call found"
        for ancestors in chains.values():
            for ancestor in ancestors:
                assert not isinstance(
                    ancestor, ast.If
                ), f"{script_name}: quarantine_legacy_writer is guarded by a condition"
                assert not isinstance(
                    ancestor, ast.Try
                ), f"{script_name}: quarantine_legacy_writer is wrapped in try/except"


def test_previously_bypassed_writer_clis_fail_closed_in_dry_run_mode():
    """Reality check: the two scripts that once bypassed quarantine behind
    `if not dry_run:` must now fail closed even when explicitly invoked
    with the dry-run flag. No mocks — real CLI subprocess execution.
    """
    import subprocess
    import sys

    invocations = [
        ("ingest_qachaq_and_customs_corpus.py", ["--dry-run"]),
        ("ingest_qachaq_and_customs_corpus.py", []),
        ("simple_neo4j_ingest.py", ["--input", "dummy.json", "--dry-run"]),
        ("simple_neo4j_ingest.py", ["--input", "dummy.json"]),
    ]
    for script_name, extra_args in invocations:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script_name), *extra_args],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(ROOT),
        )
        assert proc.returncode != 0, f"{script_name} {extra_args}: exited successfully"
        assert "LegacyGraphWriterQuarantined" in proc.stderr, (
            f"{script_name} {extra_args}: quarantine exception not raised"
        )
        assert "quarantined as a forbidden-legacy-writer" in proc.stderr
        assert "canonical-batch" in proc.stderr


def test_producer_contract_requires_traceable_spans_and_parser_metadata():
    text = "ماده ۱: متن آزمایشی"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    span = SourceSpan(
        source_uri="test://law",
        start=0,
        end=len(text),
        text_hash=digest,
    )
    document = IngestionDocument(
        document_id="law-1",
        source_uri="test://law",
        text=text,
        provenance={
            "source": "test://law",
            "source_hash": digest,
            "correlation_id": "corr-1",
        },
        parser_version="qachaq-parser-2",
        source_spans=(span,),
        warnings=("bidi marker normalized",),
    )
    batch = CanonicalIngestionBatch(
        documents=(document,),
        adapter_name="QachaqAdapter",
        parser_version="qachaq-parser-2",
        warnings=("one clause required fallback normalization",),
    )
    assert batch.documents[0].source_spans == (span,)
    assert batch.parser_version == "qachaq-parser-2"


def test_producer_contract_rejects_span_from_another_source():
    text = "قانون"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    foreign_span = SourceSpan(
        source_uri="test://other",
        start=0,
        end=1,
        text_hash=digest,
    )
    with pytest.raises(IngestionContractError, match="source spans"):
        CanonicalIngestionBatch(
            documents=(
                IngestionDocument(
                    document_id="law-1",
                    source_uri="test://law",
                    text=text,
                    provenance={
                        "source": "test://law",
                        "source_hash": digest,
                        "correlation_id": "corr-1",
                    },
                    source_spans=(foreign_span,),
                ),
            ),
            adapter_name="adapter",
            parser_version="parser-1",
        )
