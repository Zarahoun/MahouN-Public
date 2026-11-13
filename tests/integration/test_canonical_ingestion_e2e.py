"""Adversarial integration tests for the canonical governed ingestion path."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import hashlib
import json

import pytest

from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionDenied,
    IngestionExecutionGate,
    IngestionExecutionRequest,
)
from mahoun.core.governance.ingestion_runtime import (
    GovernedIngestionRuntime,
    IngestionAbortedError,
)
from mahoun.core.governance.ingestion_contract import (
    CanonicalIngestionBatch,
    IngestionContractError,
    IngestionDocument,
)
from mahoun.ingestion_adapters.banking_law_adapter import BankingLawAdapter
from mahoun.core.governance.mutation_boundary import MutationReceipt, MutationType
from mahoun.core.governance.mutation_replayer import (
    InMemoryGraphState,
    MutationReplayer,
    ReplayStatus,
)


TEXT = "ماده ۱: بانک موظف است.\nماده ۲: گزارش ارائه کند."
REQUEST = IngestionExecutionRequest(
    source="test://law",
    author_id="author-1",
    correlation_id="corr-1",
    adapter_name="BankingLawAdapter",
)
ATTESTED = SimpleNamespace(
    to_dict=lambda: {
        "source": "test://law",
        "source_hash": "attested-by-governance",
        "correlation_id": "corr-1",
        "author": "author-1",
    }
)


def build_batch():
    adapter = BankingLawAdapter(
        law_id="law-1",
        law_name="قانون آزمایشی",
        source_uri="test://law",
        correlation_id="corr-1",
    )
    with IngestionExecutionGate.enter(REQUEST):
        return adapter.build_batch(TEXT)


def runtime_with_transaction():
    transaction = MagicMock()
    transaction.is_open = True
    transaction.commit.return_value = (
        SimpleNamespace(
            receipt_id="receipt-document",
            mutation_type="NODE_MERGE",
            label="Document",
            entity_id="law-1",
            correlation_id="corr-1",
            content_hash="document-content-hash",
            pipeline_hash="document-pipeline-hash",
            timestamp="2026-09-14T00:00:00+00:00",
        ),
        SimpleNamespace(
            receipt_id="receipt-article-1",
            mutation_type="NODE_MERGE",
            label="LawArticle",
            entity_id="article-1",
            correlation_id="corr-1",
            content_hash="article-content-hash",
            pipeline_hash="article-pipeline-hash",
            timestamp="2026-09-14T00:00:00+00:00",
        ),
        SimpleNamespace(
            receipt_id="receipt-article-2",
            mutation_type="NODE_MERGE",
            label="LawArticle",
            entity_id="article-2",
            correlation_id="corr-1",
            content_hash="article-content-hash-2",
            pipeline_hash="article-pipeline-hash-2",
            timestamp="2026-09-14T00:00:00+00:00",
        ),
        SimpleNamespace(
            receipt_id="receipt-rel-1",
            mutation_type="RELATIONSHIP_MERGE",
            label="CONTAINS",
            entity_id="law-1->article-1",
            correlation_id="corr-1",
            content_hash="relationship-content-hash",
            pipeline_hash="relationship-pipeline-hash",
            timestamp="2026-09-14T00:00:00+00:00",
        ),
        SimpleNamespace(
            receipt_id="receipt-rel-2",
            mutation_type="RELATIONSHIP_MERGE",
            label="CONTAINS",
            entity_id="law-1->article-2",
            correlation_id="corr-1",
            content_hash="relationship-content-hash-2",
            pipeline_hash="relationship-pipeline-hash-2",
            timestamp="2026-09-14T00:00:00+00:00",
        ),
    )
    session = MagicMock()
    session.begin_transaction.return_value = transaction
    return GovernedIngestionRuntime(session), transaction


def test_full_adapter_to_runtime_path_is_single_atomic_idempotent_write():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST):
        result = runtime.ingest_batch_atomic(batch, author_id="author-1")

    assert result["status"] == "success"
    assert result["fact_count"] == 2
    assert result["relationship_count"] == 2
    transaction.commit.assert_called_once_with()
    transaction.abort.assert_not_called()
    # Processing marker, document, two facts, and committed marker are queued
    # before the single atomic commit.
    assert transaction.queue_node.call_count == 5
    assert transaction.queue_relationship.call_count == 2
    assert len(result["receipts"]) == 5
    assert all(receipt_id for receipt_id in result["receipts"])
    for call in (*transaction.queue_node.call_args_list, *transaction.queue_relationship.call_args_list):
        assert call.kwargs["merge"] is True
        assert call.kwargs["node_data" if "node_data" in call.kwargs else "rel_data"][
            "provenance"
        ]["author"] == "author-1"
    run_marker = transaction.queue_node.call_args_list[0].kwargs["node_data"]
    assert run_marker["status"] == "processing"


def test_successful_commit_receipts_include_forensic_fields():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST):
        result = runtime.ingest_batch_atomic(batch, author_id="author-1")

    receipt_objects = transaction.commit.return_value
    required_fields = {
        "receipt_id",
        "mutation_type",
        "label",
        "entity_id",
        "correlation_id",
        "content_hash",
        "pipeline_hash",
        "timestamp",
    }
    for receipt in receipt_objects:
        assert required_fields <= vars(receipt).keys()
        assert receipt.correlation_id == REQUEST.correlation_id
    assert result["receipts"] == [receipt.receipt_id for receipt in receipt_objects]


def _queued_mutation_fingerprint(transaction):
    queued = []
    for call in transaction.queue_node.call_args_list:
        queued.append(
            {
                "kind": "node",
                "label": call.kwargs["label"],
                "data": call.kwargs["node_data"],
                "merge": call.kwargs["merge"],
            }
        )
    for call in transaction.queue_relationship.call_args_list:
        queued.append(
            {
                "kind": "relationship",
                "source_type": call.kwargs["source_type"],
                "source_id": call.kwargs["source_id"],
                "relationship_type": call.kwargs["relationship_type"],
                "target_type": call.kwargs["target_type"],
                "target_id": call.kwargs["target_id"],
                "data": call.kwargs["rel_data"],
                "merge": call.kwargs["merge"],
            }
        )
    return hashlib.sha256(
        json.dumps(queued, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def test_same_batch_produces_same_queued_mutation_fingerprint():
    runtime_one, transaction_one = runtime_with_transaction()
    runtime_two, transaction_two = runtime_with_transaction()
    batch = build_batch()

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ):
        with IngestionExecutionGate.enter(REQUEST):
            runtime_one.ingest_batch_atomic(batch, author_id="author-1")
        with IngestionExecutionGate.enter(REQUEST):
            runtime_two.ingest_batch_atomic(batch, author_id="author-1")

    assert _queued_mutation_fingerprint(transaction_one) == _queued_mutation_fingerprint(
        transaction_two
    )
    assert transaction_one.commit.call_count == transaction_two.commit.call_count == 1
    assert transaction_one.abort.call_count == transaction_two.abort.call_count == 0


def test_replay_idempotency_is_proven_by_graph_state_fingerprint():
    """A replay must reconstruct the same graph subset, not just call mocks."""
    receipts = [
        MutationReceipt(
            receipt_id="document-receipt",
            mutation_type=MutationType.NODE_MERGE,
            label="Document",
            entity_id="law-1",
            timestamp="2026-09-14T00:00:00+00:00",
            correlation_id=REQUEST.correlation_id,
            content_hash="document-content",
            pipeline_hash="pipeline",
        ),
        MutationReceipt(
            receipt_id="article-receipt",
            mutation_type=MutationType.NODE_MERGE,
            label="LawArticle",
            entity_id="article-1",
            timestamp="2026-09-14T00:00:00+00:00",
            correlation_id=REQUEST.correlation_id,
            content_hash="article-content",
            pipeline_hash="pipeline",
        ),
    ]
    expected_graph = InMemoryGraphState()
    expected_graph.apply_node_merge("law-1", "Document", "document-content")
    expected_graph.apply_node_merge("article-1", "LawArticle", "article-content")
    expected_hash = expected_graph.state_hash()
    first = MutationReplayer().replay(receipts, expected_hash=expected_hash)
    second = MutationReplayer().replay(receipts, expected_hash=expected_hash)

    assert first.status == ReplayStatus.MATCH
    assert second.status == ReplayStatus.MATCH
    assert first.reconstructed_hash == second.reconstructed_hash
    assert first.applied_count == second.applied_count == len(receipts)


def test_commit_cannot_run_before_all_nodes_and_relationships_are_queued():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    events = []

    transaction.queue_node.side_effect = lambda **_: events.append("node")
    transaction.queue_relationship.side_effect = lambda **_: events.append(
        "relationship"
    )
    transaction.commit.side_effect = lambda: (
        events.append("commit"),
        *transaction.commit.return_value,
    )[1:]

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    assert events == [
        "node",
        "node",
        "node",
        "node",
        "relationship",
        "relationship",
        "node",
        "commit",
    ]


def test_forged_attestation_cannot_replace_batch_identity_or_authority():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    forged = SimpleNamespace(
        to_dict=lambda: {
            "source": "test://forged-authority",
            "source_hash": "forged-hash",
            "correlation_id": "forged-correlation",
            "author": "forged-author",
        }
    )

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=forged,
    ), IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="attestation does not match"
    ):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    assert transaction.begin_transaction.call_count == 0
    assert transaction.queue_node.call_count == 0
    assert transaction.commit.call_count == 0
    assert transaction.abort.call_count == 0


def test_forged_relationship_target_cannot_be_materialized():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    relationship = batch.relationships[0]
    forged = batch.__class__(
        batch.documents,
        batch.facts,
        (
            relationship.__class__(
                relationship_id=relationship.relationship_id,
                source_id=relationship.source_id,
                relationship_type=relationship.relationship_type,
                target_id="fact:not-in-batch",
                properties=relationship.properties,
                provenance=relationship.provenance,
            ),
        ),
    )

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="matching semantic fact"
    ):
        runtime.ingest_batch_atomic(forged, author_id="author-1")

    assert transaction.commit.call_count == 0
    assert transaction.abort.call_count == 1


def test_missing_execution_permit_blocks_before_transaction_creation():
    runtime, transaction = runtime_with_transaction()

    with pytest.raises(IngestionExecutionDenied, match="No Gate"):
        runtime.ingest_batch_atomic(build_batch(), author_id="author-1")

    transaction.begin_transaction.assert_not_called()


def test_permit_source_mismatch_blocks_before_transaction_creation():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    wrong_request = IngestionExecutionRequest(
        source="test://different",
        author_id="author-1",
        correlation_id="corr-1",
        adapter_name="BankingLawAdapter",
    )

    with IngestionExecutionGate.enter(wrong_request), pytest.raises(
        IngestionAbortedError, match="permit"
    ):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    transaction.begin_transaction.assert_not_called()


def test_permit_actor_mismatch_blocks_before_transaction_creation():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()

    with IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="author"
    ):
        runtime.ingest_batch_atomic(batch, author_id="different-author")

    transaction.begin_transaction.assert_not_called()


def test_permit_rejects_a_batch_with_a_second_unpermitted_source():
    runtime, transaction = runtime_with_transaction()
    primary = build_batch().documents[0]
    secondary_text = "ماده ۳: منبع دیگری است."
    secondary = IngestionDocument(
        document_id="law:second",
        source_uri="test://second-law",
        text=secondary_text,
        provenance={
            "source": "test://second-law",
            "source_hash": "eea12e415a28ab720464b5637c232e747f63a5291a3562893e5b5c284250a22e",
            "correlation_id": "corr-1",
        },
    )
    batch = CanonicalIngestionBatch((primary, secondary))

    with IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="every batch source"
    ):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    transaction.begin_transaction.assert_not_called()


def test_contract_rejects_document_provenance_from_another_source():
    with pytest.raises(IngestionContractError, match="source_uri"):
        IngestionDocument(
            document_id="law:forged-source",
            source_uri="test://expected",
            text="متن قانون",
            provenance={
                "source": "test://forged",
                "source_hash": "bd72fe549ae912261683135ff1d9dccb0b46a5e9d217fca08cc915eda34b7b3b",
                "correlation_id": "corr-1",
            },
        )


def test_commit_failure_aborts_and_never_returns_success():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    transaction.commit.side_effect = RuntimeError("neo4j unavailable")

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="neo4j unavailable"
    ):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    transaction.commit.assert_called_once_with()
    transaction.abort.assert_called_once_with()


def test_queue_failure_after_facts_are_queued_aborts_without_success():
    runtime, transaction = runtime_with_transaction()
    batch = build_batch()
    transaction.queue_relationship.side_effect = RuntimeError(
        "relationship validation failed after facts were queued"
    )

    with patch(
        "mahoun.core.governance.ingestion_runtime.GovernanceContextManager"
        ".require_provenance",
        return_value=ATTESTED,
    ), IngestionExecutionGate.enter(REQUEST), pytest.raises(
        IngestionAbortedError, match="relationship validation failed"
    ):
        runtime.ingest_batch_atomic(batch, author_id="author-1")

    assert transaction.queue_node.call_count == 4
    transaction.commit.assert_not_called()
    transaction.abort.assert_called_once_with()


def test_invalid_runtime_batch_type_is_rejected_before_mutation():
    runtime, transaction = runtime_with_transaction()

    with pytest.raises(IngestionAbortedError, match="invalid type"):
        with IngestionExecutionGate.enter(REQUEST):
            runtime.ingest_batch_atomic(object(), author_id="author-1")

    transaction.begin_transaction.assert_not_called()


def test_canonical_runtime_has_no_legacy_writer_dependency():
    from pathlib import Path

    source = Path("mahoun/core/governance/ingestion_runtime.py").read_text()
    assert "upsert_verdict_struct" not in source
    assert "GraphBuildPipeline" not in source
