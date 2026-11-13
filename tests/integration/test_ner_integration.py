"""
Test for NER integration into IranianLawAdapter.
"""

from pathlib import Path

from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate


def test_iranian_law_adapter_includes_ner_metadata():
    """The adapter should include NER-extracted entities in document metadata."""
    # Minimal law text with NER entities
    text = """قانون تست
ماده ۱
این قانون توسط شورای عالیनीय produziert wird.
ماده ۲
به موجب این قانون، شرکت xyz مسئول است."""
    adapter = IranianLawAdapter(
        law_id="law:test",
        law_name="قانون تست",
        source_uri="test://law",
        correlation_id="test-correlation-id",
    )

    # We need an active execution gate for the adapter to work
    # Create a dummy context
    from mahoun.core.governance.governance_context import GovernanceContextManager
    from mahoun.core.governance.ingestion_execution_gate import (
        IngestionExecutionRequest,
    )

    # Manually set up the context for testing
    class DummyPermit:
        class Request:
            adapter_name = "IranianLawAdapter"
            source = "test://law"
        request = Request()

    # Patch the gate to return our dummy permit
    original_require_active = IngestionExecutionGate.require_active
    IngestionExecutionGate.require_active = classmethod(lambda cls: DummyPermit())

    try:
        batch = adapter.build_batch(text)
    finally:
        IngestionExecutionGate.require_active = original_require_active

    # Check that NER metadata is present
    assert len(batch.documents) == 1
    doc = batch.documents[0]
    assert "article_ner" in doc.metadata
    ner_data = doc.metadata["article_ner"]
    # Should have the structure we added
    assert isinstance(ner_data, dict)
    # The article ID should be present
    article_id = f"law:test:article:1"
    assert article_id in ner_data
    article_ner = ner_data[article_id]
    # Should have the expected keys
    assert set(article_ner.keys()) == {
        "persons",
        "organizations",
        "courts",
        "laws",
        "topics",
        "legal_concepts",
    }
    # At minimum, the structure should be there (content depends on NER patterns)
    assert isinstance(article_ner["persons"], list)
    assert isinstance(article_ner["organizations"], list)
    assert isinstance(article_ner["courts"], list)
    assert isinstance(article_ner["laws"], list)
    assert isinstance(article_ner["topics"], list)
    assert isinstance(article_ner["legal_concepts"], list)