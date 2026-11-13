"""High-fidelity end-to-end tests for canonical graph materialization.

These tests use the real adapter, execution permit, governance context,
``GovernedNeo4jSession``, validator pipeline, and write transaction.  The
database driver is replaced only by a deterministic in-memory Cypher
executor so the assertions cover the complete graph contract without
requiring a live Neo4j service.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionGate,
    IngestionExecutionRequest,
)
from mahoun.core.governance.ingestion_runtime import (
    GovernedIngestionRuntime,
    IngestionAbortedError,
)
from mahoun.core.governance.mutation_boundary import (
    GovernedNeo4jSession,
    get_audit_sink,
    set_audit_sink,
)
from mahoun.ingestion_adapters.banking_law_adapter import BankingLawAdapter


SOURCE = "test://graph-e2e"
AUTHOR = "graph-e2e-operator"
CORRELATION = "graph-e2e-correlation"
TEXT = "ماده ۱: بانک موظف است.\nماده ۲: گزارش ارائه کند."


class InMemoryCypherGraph:
    """Small deterministic executor for the Cypher emitted by the real writer."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], dict] = {}
        self.relationships: dict[tuple[str, str, str, str, str], dict] = {}
        self.queries: list[tuple[str, dict]] = []

    def execute(self, query: str, parameters: dict) -> list[dict]:
        self.queries.append((query, dict(parameters)))
        if query.startswith("MATCH (r:IngestionRun"):
            row = self.nodes.get(("IngestionRun", parameters["id"]))
            return [row] if row else []

        node_match = re.search(r"MERGE \(n:([A-Za-z_][A-Za-z0-9_]*) \{id: \$id\}\)", query)
        if node_match:
            label = node_match.group(1)
            node_id = str(parameters["id"])
            self.nodes[(label, node_id)] = dict(parameters)
            return []

        rel_match = re.search(
            r"MATCH \(a:([A-Za-z_][A-Za-z0-9_]*) \{id: \$__src\}\) "
            r"MATCH \(b:([A-Za-z_][A-Za-z0-9_]*) \{id: \$__tgt\}\) "
            r"MERGE \(a\)-\[r:([A-Z_][A-Z0-9_]*)\]->\(b\)",
            query,
        )
        if rel_match:
            source_type, target_type, relationship_type = rel_match.groups()
            key = (
                source_type,
                str(parameters["__src"]),
                relationship_type,
                target_type,
                str(parameters["__tgt"]),
            )
            self.relationships[key] = dict(parameters)
            return []

        raise AssertionError(f"unexpected Cypher emitted by governed writer: {query}")


class InMemorySession:
    def __init__(self, graph: InMemoryCypherGraph, correlation_id: str) -> None:
        self.graph = graph
        self._session = GovernedNeo4jSession(
            raw_executor=graph.execute,
            correlation_id=correlation_id,
            actor_id=AUTHOR,
        )

    def begin_transaction(self):
        return self._session.begin_transaction()

    def execute_read_cypher(self, query: str, parameters: dict):
        return self.graph.execute(query, parameters)


class RecordingAuditSink:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, entry: dict) -> None:
        self.entries.append(entry)


@pytest.fixture
def audit_sink() -> RecordingAuditSink:
    previous = get_audit_sink()
    sink = RecordingAuditSink()
    set_audit_sink(sink)
    try:
        yield sink
    finally:
        if previous is None:
            from mahoun.core.governance.mutation_boundary import unset_audit_sink

            unset_audit_sink()
        else:
            set_audit_sink(previous)


def _batch():
    adapter = BankingLawAdapter(
        law_id="law:e2e",
        law_name="قانون بانکی آزمایشی",
        source_uri=SOURCE,
        correlation_id=CORRELATION,
    )
    return adapter.build_batch(TEXT)


@asynccontextmanager
async def _governance_scope():
    async with GovernanceContextManager.active_context(
        correlation_id=CORRELATION,
        execution_mode="STRICT",
        actor_id=AUTHOR,
    ):
        yield


@pytest.mark.asyncio
async def test_real_adapter_to_governed_graph_materialization_preserves_provenance(
    audit_sink: RecordingAuditSink,
):
    graph = InMemoryCypherGraph()
    async with _governance_scope():
        with IngestionExecutionGate.enter(
            IngestionExecutionRequest(
                source=SOURCE,
                author_id=AUTHOR,
                correlation_id=CORRELATION,
                adapter_name="BankingLawAdapter",
            )
        ):
            batch = _batch()
            result = GovernedIngestionRuntime(
                InMemorySession(graph, CORRELATION)
            ).ingest_batch_atomic(batch, AUTHOR)

    assert result["status"] == "success"
    assert {label for label, _ in graph.nodes} >= {
        "IngestionRun",
        "Document",
        "LawArticle",
    }
    assert len(graph.relationships) == 2
    assert len(audit_sink.entries) == 1
    assert audit_sink.entries[0]["mutation_count"] == 7
    assert all(
        node["provenance"]["author"] == AUTHOR
        for node in graph.nodes.values()
        if "provenance" in node
    )
    assert all(
        "provenance" not in parameters
        for query, parameters in graph.queries
        if query.startswith("MERGE")
    )


@pytest.mark.asyncio
async def test_invalid_relationship_is_rejected_before_any_graph_mutation():
    graph = InMemoryCypherGraph()

    async with _governance_scope():
        with IngestionExecutionGate.enter(
            IngestionExecutionRequest(
                source=SOURCE,
                author_id=AUTHOR,
                correlation_id=CORRELATION,
                adapter_name="BankingLawAdapter",
            )
        ), pytest.raises(IngestionAbortedError):
            batch = _batch()
            relationship = batch.relationships[0]
            invalid = batch.__class__(
                batch.documents,
                batch.facts,
                (
                    relationship.__class__(
                        relationship.relationship_id,
                        relationship.source_id,
                        "UNAUTHORIZED_RELATIONSHIP",
                        relationship.target_id,
                        relationship.properties,
                        relationship.provenance,
                    ),
                    *batch.relationships[1:],
                ),
                batch.adapter_name,
                batch.parser_version,
                batch.warnings,
                batch.idempotency_key,
            )
            GovernedIngestionRuntime(
                InMemorySession(graph, CORRELATION)
            ).ingest_batch_atomic(invalid, AUTHOR)

    assert graph.nodes == {}
    assert graph.relationships == {}


@pytest.mark.asyncio
async def test_replay_returns_durable_marker_without_duplicate_graph_edges(
    audit_sink: RecordingAuditSink,
):
    graph = InMemoryCypherGraph()

    async with _governance_scope():
        session = InMemorySession(graph, CORRELATION)
        with IngestionExecutionGate.enter(
            IngestionExecutionRequest(
                source=SOURCE,
                author_id=AUTHOR,
                correlation_id=CORRELATION,
                adapter_name="BankingLawAdapter",
            )
        ):
            batch = _batch()
            runtime = GovernedIngestionRuntime(session)
            first = runtime.ingest_batch_atomic(batch, AUTHOR)
            first_nodes = len(graph.nodes)
            first_edges = len(graph.relationships)
            second = runtime.ingest_batch_atomic(batch, AUTHOR)

    assert first["status"] == "success"
    assert second["status"] == "already_committed"
    assert len(graph.nodes) == first_nodes
    assert len(graph.relationships) == first_edges
    assert second["receipts"] == first["receipts"]
