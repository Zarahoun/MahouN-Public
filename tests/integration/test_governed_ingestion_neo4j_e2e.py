"""End-to-end checks for governed Neo4j writes using a real Neo4j service."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator

import pytest

from mahoun.core.governance.domain_validation_gate import (
    get_domain_gate,
    reset_domain_gate,
)
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.ingestion_runtime import GovernedIngestionRuntime
from mahoun.core.governance.mutation_boundary import (
    get_audit_sink,
    set_audit_sink,
    unset_audit_sink,
)
from mahoun.core.governance.violations import GovernanceViolationError
from mahoun.graph.neo4j.connection import Neo4jConnection, get_connection
from mahoun.graph.schemas.legal_schemas import LegalArticleProperties
from mahoun.infrastructure.audit.filesink import FilesystemAuditSink


@pytest.fixture(scope="module")
def neo4j_connection() -> Iterator[Neo4jConnection]:
    """Use the canonical connection and skip only when the configured DB is unavailable."""
    connection = get_connection()
    try:
        result = connection.execute_query("RETURN 1 AS value")
        assert result[0]["value"] == 1
    except Exception as exc:
        # quality-gate-approved: requires live Neo4j service; skips only when DB connectivity check fails
        pytest.skip(f"Neo4j is not available: {exc}")
    yield connection


@pytest.fixture
def test_audit_sink(tmp_path: Path) -> Iterator[Path]:
    """Use a per-test audit file and restore the process-global sink afterward."""
    audit_path = tmp_path / "governance.audit"
    previous_sink = get_audit_sink()
    set_audit_sink(FilesystemAuditSink(path=str(audit_path), mirror_path=None))
    try:
        yield audit_path
    finally:
        if previous_sink is None:
            unset_audit_sink()
        else:
            set_audit_sink(previous_sink)


@pytest.fixture
def node_id_prefix() -> str:
    return f"graph-v2-test:{uuid.uuid4().hex}:"


@pytest.fixture(autouse=True)
def cleanup_test_nodes(
    neo4j_connection: Neo4jConnection,
    test_audit_sink: Path,
    node_id_prefix: str,
) -> Iterator[None]:
    """Remove only nodes created by this test, through the governed write surface."""

    def cleanup() -> None:
        rows = neo4j_connection.execute_query(
            "MATCH (n) WHERE n.id STARTS WITH $prefix "
            "RETURN labels(n) AS labels, n.id AS id",
            {"prefix": node_id_prefix},
        )
        for row in rows:
            labels = row["labels"]
            if labels:
                with neo4j_connection.governed_session(
                    actor_id="graph-v2-test-cleanup",
                    correlation_id=f"{node_id_prefix}cleanup",
                ) as session:
                    session.delete_node(labels[0], row["id"], soft_delete=False)

    cleanup()
    yield
    cleanup()


@pytest.fixture
def registered_legal_schema() -> Iterator[None]:
    reset_domain_gate()
    get_domain_gate().register_schema("LawArticle", LegalArticleProperties)
    try:
        yield
    finally:
        reset_domain_gate()


class TestAtomicRollback:
    def test_invalid_extension_properties_create_zero_nodes(
        self,
        neo4j_connection: Neo4jConnection,
        node_id_prefix: str,
        registered_legal_schema: None,
    ) -> None:
        valid_id = f"{node_id_prefix}valid"
        invalid_id = f"{node_id_prefix}invalid"

        with neo4j_connection.governed_session(
            actor_id="graph-v2-test",
            correlation_id=f"{node_id_prefix}rollback",
        ) as session:
            provenance = GovernanceContextManager.require_provenance(
                source="graph-v2-test",
                author="graph-v2-test",
            ).to_dict()
            transaction = session.begin_transaction()
            transaction.queue_node(
                "Document",
                {
                    "id": valid_id,
                    "text_content": "A valid document",
                    "provenance": provenance,
                },
            )
            transaction.queue_node(
                "LawArticle",
                {
                    "id": invalid_id,
                    "extension_properties": {
                        "article_number": "15",
                        "unregistered_field": "must be rejected",
                    },
                    "provenance": provenance,
                },
            )

            with pytest.raises(GovernanceViolationError):
                transaction.commit()
            transaction.abort()

        rows = neo4j_connection.execute_query(
            "MATCH (n) WHERE n.id IN $ids RETURN count(n) AS count",
            {"ids": [valid_id, invalid_id]},
        )
        assert rows[0]["count"] == 0


class TestDomainValidationIntegration:
    def test_validated_extension_properties_are_persisted_as_json(
        self,
        neo4j_connection: Neo4jConnection,
        node_id_prefix: str,
        test_audit_sink: Path,
        registered_legal_schema: None,
    ) -> None:
        node_id = f"{node_id_prefix}article"
        extensions = {
            "article_number": "۱۵",
            "valid_from": "1402/03/15",
            "repeal_indicator": False,
        }

        with neo4j_connection.governed_session(
            actor_id="graph-v2-test",
            correlation_id=f"{node_id_prefix}valid-extension",
        ) as session:
            session.write_node(
                "LawArticle",
                {
                    "id": node_id,
                    "extension_properties": extensions,
                },
            )

        rows = neo4j_connection.execute_query(
            "MATCH (n:LawArticle {id: $id}) "
            "RETURN n.extension_properties AS extension_properties",
            {"id": node_id},
        )
        assert len(rows) == 1
        assert json.loads(rows[0]["extension_properties"]) == extensions


class TestProvenanceAndAudit:
    def test_write_is_recorded_in_the_configured_audit_sink(
        self,
        neo4j_connection: Neo4jConnection,
        node_id_prefix: str,
        test_audit_sink: Path,
    ) -> None:
        correlation_id = f"{node_id_prefix}audit"

        with neo4j_connection.governed_session(
            actor_id="graph-v2-test",
            correlation_id=correlation_id,
        ) as session:
            session.write_node(
                "Document",
                {
                    "id": f"{node_id_prefix}audited",
                    "text_content": "Audited document",
                },
            )

        events = [
            json.loads(line)
            for line in test_audit_sink.read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            event.get("operation") == "write_node"
            and event.get("correlation_id") == correlation_id
            for event in events
        )


class TestConcurrentIsolation:
    def test_failed_transaction_does_not_affect_concurrent_write(
        self,
        neo4j_connection: Neo4jConnection,
        node_id_prefix: str,
    ) -> None:
        failed_id = f"{node_id_prefix}failed"
        successful_id = f"{node_id_prefix}successful"

        def fail_before_commit() -> None:
            with neo4j_connection.governed_session(
                actor_id="graph-v2-test",
                correlation_id=f"{node_id_prefix}failed-write",
            ) as session:
                provenance = GovernanceContextManager.require_provenance(
                    source="graph-v2-test",
                    author="graph-v2-test",
                ).to_dict()
                transaction = session.begin_transaction()
                transaction.queue_node(
                    "Document",
                    {
                        "id": failed_id,
                        "text_content": "Must be rolled back",
                        "provenance": provenance,
                    },
                )
                raise RuntimeError("intentional rollback")

        def commit_write() -> None:
            with neo4j_connection.governed_session(
                actor_id="graph-v2-test",
                correlation_id=f"{node_id_prefix}successful-write",
            ) as session:
                session.write_node(
                    "Document",
                    {
                        "id": successful_id,
                        "text_content": "Must be committed",
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            failed = executor.submit(fail_before_commit)
            successful = executor.submit(commit_write)
            with pytest.raises(RuntimeError, match="intentional rollback"):
                failed.result()
            successful.result()

        rows = neo4j_connection.execute_query(
            "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id",
            {"ids": [failed_id, successful_id]},
        )
        assert [row["id"] for row in rows] == [successful_id]


class TestIdempotency:
    def test_reingesting_same_document_id_does_not_duplicate_node(
        self,
        neo4j_connection: Neo4jConnection,
        node_id_prefix: str,
    ) -> None:
        doc_id = f"{node_id_prefix}document"

        with neo4j_connection.governed_session(
            actor_id="graph-v2-test",
            correlation_id=f"{node_id_prefix}idempotency",
        ) as session:
            runtime = GovernedIngestionRuntime(session)
            runtime.ingest_document_atomic(
                doc_id=doc_id,
                text="Repeatable document",
                metadata={"source": "graph-v2-test"},
                author_id="graph-v2-test",
            )
            runtime.ingest_document_atomic(
                doc_id=doc_id,
                text="Repeatable document",
                metadata={"source": "graph-v2-test"},
                author_id="graph-v2-test",
            )

        rows = neo4j_connection.execute_query(
            "MATCH (n:Document {id: $id}) RETURN count(n) AS count",
            {"id": doc_id},
        )
        assert rows[0]["count"] == 1


pytestmark = [
    pytest.mark.integration,
    pytest.mark.neo4j,
    pytest.mark.slow,
]
