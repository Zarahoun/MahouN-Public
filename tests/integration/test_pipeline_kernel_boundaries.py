"""Adversarial architectural tests for the pipeline-to-governance boundary.

These tests intentionally inspect syntax and execute quarantine surfaces. A
pipeline is allowed to produce candidates or vector indexes, but it is never
allowed to become a second Neo4j writer.
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).parents[2]
PIPELINES = ROOT / "mahoun" / "pipelines"
QUARANTINED_DIRS = {"graph_build", "sync"}
ACTIVE_FILES = tuple(
    path
    for path in PIPELINES.rglob("*.py")
    if "__pycache__" not in path.parts
    and path.relative_to(PIPELINES).parts[0] not in QUARANTINED_DIRS
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _calls(tree: ast.AST):
    return (node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _called_attribute(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_active_pipeline_ast_has_no_graph_transaction_mutations():
    forbidden = {
        "begin_transaction",
        "queue_node",
        "queue_relationship",
        "write_node",
        "write_relationship",
        "execute_query",
        "commit",
        "abort",
    }
    violations = []
    for path in ACTIVE_FILES:
        tree = ast.parse(_source(path), filename=str(path))
        for node in _calls(tree):
            if _called_attribute(node) in forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}:"
                    f"{_called_attribute(node)}"
                )
    assert not violations, "\n".join(violations)


def test_active_pipeline_ast_has_no_legacy_graph_writer_imports():
    forbidden = {
        "mahoun.graph.neo4j.operations",
        "mahoun.graph.neo4j.connection",
        "mahoun.graph.concurrent_graph_builder",
        "mahoun.graph.ultra_graph_builder",
    }
    violations = []
    for path in ACTIVE_FILES:
        tree = ast.parse(_source(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in forbidden:
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {alias.name}"
                        )
    assert not violations, "\n".join(violations)


def test_all_pipeline_source_is_free_of_legacy_destructive_or_direct_writer_tokens():
    forbidden = (
        "upsert_verdict_struct",
        "GraphDatabase.driver",
        "AsyncGraphDatabase.driver",
        "DETACH DELETE",
    )
    violations = [
        f"{path.relative_to(ROOT)} contains {token!r}"
        for path in ACTIVE_FILES
        for token in forbidden
        if token in _source(path)
    ]
    assert not violations, "\n".join(violations)


def test_active_pipeline_cannot_hide_writer_access_behind_dynamic_lookup():
    forbidden_dynamic_names = {
        "begin_transaction",
        "queue_node",
        "queue_relationship",
        "execute_query",
        "execute_cypher",
        "raw_execute",
        "submit_to_neo4j",
        "upsert_verdict_struct",
    }
    violations = []
    for path in ACTIVE_FILES:
        tree = ast.parse(_source(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    if node.args[1].value in forbidden_dynamic_names:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}:"
                            f"dynamic lookup of {node.args[1].value}"
                        )
            if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}:dynamic module import"
                )
    assert not violations, "\n".join(violations)


def test_pipeline_writer_named_surfaces_are_fail_closed():
    violations = []
    for path in PIPELINES.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(_source(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"submit_to_neo4j", "link_and_submit"}:
                continue
            body = ast.get_source_segment(_source(path), node) or ""
            if "raise RuntimeError" not in body or "blocked" not in body:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
    assert not violations, "\n".join(violations)


def test_legacy_graph_pipeline_is_unreachable_and_runtime_blocked():
    switchboard = _source(ROOT / "mahoun" / "switchboard.py")
    route = _source(ROOT / "api" / "routers" / "ingest.py")
    assert '"graph_build_pipeline"' not in switchboard
    assert "GraphBuildPipeline" not in route

    from mahoun.graph.ingestion.run_import import GraphBuildPipeline

    with pytest.raises(RuntimeError, match="canonical"):
        GraphBuildPipeline()


def test_entity_linker_every_direct_submission_surface_is_blocked():
    from mahoun.graph.builders.entity_linker import EntityLinker, link_and_submit

    with pytest.raises(RuntimeError, match="blocked"):
        EntityLinker().submit_to_neo4j([], [])
    with pytest.raises(RuntimeError, match="blocked"):
        link_and_submit({}, "case-1", neo4j_adapter=object())


def test_bootstrap_gates_secondary_graph_writers_in_graph_build_mode():
    source = _source(ROOT / "mahoun" / "bootstrap" / "runtime.py")
    assert "is_graph_build_mode()" in source
    assert source.count("if not is_graph_build_mode():") >= 2
    assert 'register_service("graph_vector_sync"' in source
    assert 'register_service("gnn"' in source


def test_api_startup_critical_services_match_graph_build_mode_contract():
    source = _source(ROOT / "api" / "main.py")
    assert "is_graph_build_mode()" in source
    assert 'critical_services = ["query"]' in source
    assert 'critical_services.extend(["graph_retriever", "gnn"])' in source


def test_ingest_route_has_only_canonical_graph_writer_chain():
    source = _source(ROOT / "api" / "routers" / "ingest.py")
    required = (
        "GovernedIngestionRuntime",
        "IngestionExecutionGate",
        "create_adapter",
        "governed_session",
        "ingest_batch_atomic",
    )
    for token in required:
        assert token in source
    for forbidden in (
        "GraphBuildPipeline",
        "upsert_verdict_struct",
        "link_and_submit",
    ):
        assert forbidden not in source


def test_reasoning_router_cannot_materialize_graph_batches():
    source = _source(ROOT / "api" / "routers" / "reasoning.py")
    forbidden = (
        "GovernedIngestionRuntime",
        "ingest_batch_atomic",
        "queue_node",
        "queue_relationship",
        "upsert_verdict_struct",
        "GraphBuildPipeline",
    )
    violations = [token for token in forbidden if token in source]
    assert not violations, (
        "reasoning endpoints must be graph consumers, not materializers: "
        + ", ".join(violations)
    )


def test_canonical_batch_api_contract_is_versioned_and_receipt_bearing():
    source = _source(ROOT / "api" / "routers" / "ingest.py")
    model_source = _source(ROOT / "api" / "models" / "core.py")
    for token in (
        '@router.post("/canonical-batch"',
        "CanonicalBatchRequest",
        "GovernedIngestionRuntime",
        "ingest_batch_atomic",
        "CanonicalBatchResponse",
        "receipts",
    ):
        assert token in source or token in model_source
    assert 'pattern=r"^1$"' in model_source


def test_canonical_batch_request_rejects_unknown_contract_versions():
    from api.models import CanonicalBatchRequest

    with pytest.raises(ValidationError):
        CanonicalBatchRequest(
            contract_version="999",
            adapter_name="BankingLawAdapter",
            correlation_id="corr",
            author_id="actor",
            parser_version="test-parser-1",
            documents=[],
        )


def test_canonical_batch_conversion_enforces_source_hash_and_relationship_targets():
    from api.models import (
        CanonicalBatchDocument,
        CanonicalBatchFact,
        CanonicalBatchRelationship,
        CanonicalBatchRequest,
        CanonicalSourceSpan,
    )
    from api.routers.ingest import _canonical_batch_from_request
    from mahoun.core.governance.ingestion_contract import IngestionContractError

    document = CanonicalBatchDocument(
        document_id="law-1",
        source_uri="test://law",
        text="ماده ۱: بانک موظف است.",
        provenance={
            "source": "test://law",
            "source_hash": "0" * 64,
            "correlation_id": "corr",
        },
    )
    with pytest.raises(IngestionContractError, match="source_hash"):
        _canonical_batch_from_request(
            CanonicalBatchRequest(
                contract_version="1",
                adapter_name="BankingLawAdapter",
                correlation_id="corr",
                author_id="actor",
                parser_version="test-parser-1",
                documents=[document],
            )
        )

    valid_hash = __import__("hashlib").sha256(
        document.text.encode("utf-8")
    ).hexdigest()
    valid_document = document.model_copy(
        update={"provenance": {**document.provenance, "source_hash": valid_hash}}
    )
    fact = CanonicalBatchFact(
        fact_id="fact-1",
        subject_id="law-1",
        predicate="CONTAINS",
        object_id="article-1",
        evidence_text="بانک موظف است.",
        provenance={
            "source": "test://law",
            "source_hash": valid_hash,
            "correlation_id": "corr",
        },
        source_spans=[
            CanonicalSourceSpan(
                source_uri="test://law",
                start=document.text.index("بانک"),
                end=document.text.index("بانک") + len("بانک موظف است."),
                text_hash=__import__("hashlib").sha256(
                    "بانک موظف است.".encode()
                ).hexdigest(),
            )
        ],
    )
    forged_relationship = CanonicalBatchRelationship(
        relationship_id="rel-1",
        source_id="law-1",
        relationship_type="CONTAINS",
        target_id="article-not-emitted",
        properties={},
        provenance={
            "source": "test://law",
            "source_hash": valid_hash,
            "correlation_id": "corr",
        },
    )
    # Conversion accepts only the immutable contract; runtime must reject the
    # forged target before commit. This prevents the API adapter from silently
    # rewriting or inventing semantic targets.
    batch = _canonical_batch_from_request(
        CanonicalBatchRequest(
            contract_version="1",
            adapter_name="BankingLawAdapter",
            correlation_id="corr",
            author_id="actor",
            parser_version="test-parser-1",
            documents=[valid_document],
            facts=[fact],
            relationships=[forged_relationship],
        )
    )
    assert batch.relationships[0].target_id == "article-not-emitted"
