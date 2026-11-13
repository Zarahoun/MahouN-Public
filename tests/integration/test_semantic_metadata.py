"""Test semantic metadata structure in IranianLawAdapter."""

import pytest
from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate, IngestionExecutionRequest
from mahoun.graph.neo4j.enums import DeonticOperator


class TestSemanticMetadata:
    """Test standardized semantic metadata structure."""

    def _build_batch_with_text(self, text: str):
        """Helper to build batch with governance context."""
        adapter = IranianLawAdapter(
            law_id="law:semantic_test",
            law_name="قانون تست معنایی",
            source_uri="test://semantic",
            correlation_id="test-semantic-123",
        )

        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://semantic"
            request = Request()

        with IngestionExecutionGate.enter(IngestionExecutionRequest(
            adapter_name="IranianLawAdapter",
            source="test://semantic",
            author_id="test-author",
            correlation_id="test-semantic-123",
        )):
            return adapter.build_batch(text)

    def test_obligation_has_deontic_operator(self):
        """Obligation extraction should have OBLIGATION deontic operator."""
        text = "ماده ۱: شرکت مکلف است گزارش مالی ارائه دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:obligation" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_OBLIGATION"
        assert fact.metadata["semantic"]["deontic_operator"] == "OBLIGATION"
        assert fact.metadata["semantic"]["semantic_type"] == "obligation"
        assert fact.confidence == 0.85
        assert fact.metadata["semantic"]["extraction_method"] == "deterministic-regex"
        assert fact.metadata["semantic"]["confidence_reason"] == "regex-pattern-match"

    def test_prohibition_has_deontic_operator(self):
        """Prohibition extraction should have PROHIBITION deontic operator."""
        text = "ماده ۲: شرکت ممنوع است از فعالیت غیرمجاز."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:prohibition" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_PROHIBITION"
        assert fact.metadata["semantic"]["deontic_operator"] == "PROHIBITION"
        assert fact.metadata["semantic"]["semantic_type"] == "prohibition"

    def test_permission_has_deontic_operator(self):
        """Permission extraction should have PERMISSION deontic operator."""
        text = "ماده ۳: شرکت می‌تواند شعبه جدید تأسیس کند."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:permission" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_PERMISSION"
        assert fact.metadata["semantic"]["deontic_operator"] == "PERMISSION"
        assert fact.metadata["semantic"]["semantic_type"] == "permission"

    def test_right_has_no_deontic_operator(self):
        """Right extraction should have None deontic operator."""
        text = "ماده ۴: شرکت حق دارد از تسهیلات استفاده کند."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:right" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_RIGHT"
        assert fact.metadata["semantic"]["deontic_operator"] is None
        assert fact.metadata["semantic"]["semantic_type"] == "right"

    def test_metadata_structure_standardized(self):
        """Metadata should have standardized nested structure."""
        text = "ماده ۱: شرکت مکلف است گزارش دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        
        # Check semantic section
        assert "semantic" in fact.metadata
        assert "semantic_type" in fact.metadata["semantic"]
        assert "deontic_operator" in fact.metadata["semantic"]
        assert "extraction_method" in fact.metadata["semantic"]
        assert "confidence_reason" in fact.metadata["semantic"]
        
        # Check extraction section
        assert "extraction" in fact.metadata
        assert "ordinal" in fact.metadata["extraction"]
        assert "pattern" in fact.metadata["extraction"]
        assert "source" in fact.metadata["extraction"]
        
        # Check domain section
        assert "domain" in fact.metadata
        assert fact.metadata["domain"] == "legal"

    def test_provenance_preserved(self):
        """Provenance should be preserved in semantic facts."""
        text = "ماده ۱: شرکت باید گزارش دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.provenance is not None
        assert len(fact.source_spans) > 0

    def test_document_temporal_metadata_preserved(self):
        """Document-level temporal metadata should be preserved."""
        text = "ماده ۱: از تاریخ ۱۴۰۰/۰۱/۰۱ لازم‌الاجرا است."
        batch = self._build_batch_with_text(text)
        
        assert "temporal" in batch.documents[0].metadata
        assert "effective_date" in batch.documents[0].metadata["temporal"]
        # Persian digits are preserved as-is
        assert batch.documents[0].metadata["temporal"]["effective_date"] == "۱۴۰۰/۰۱/۰۱"

    def test_extraction_counts_unchanged(self):
        """Extraction counts should remain unchanged."""
        text = """
قانون تست
ماده ۱: شرکت مکلف است گزارش مالی ارائه دهد.
ماده ۲: شرکت ممنوع است از فعالیت غیرمجاز.
ماده ۳: شرکت می‌تواند شعبه جدید تأسیس کند.
ماده ۴: شرکت صلاحیت دارد تصمیم بگیرد.
"""
        batch = self._build_batch_with_text(text)
        
        # Should have 4 semantic facts (one per article)
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 4
        
        # Should have 4 article facts
        article_facts = [f for f in batch.facts if ":article:" in f.fact_id]
        assert len(article_facts) == 4

"""Test semantic metadata structure in IranianLawAdapter."""

import pytest
from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate, IngestionExecutionRequest
from mahoun.graph.neo4j.enums import DeonticOperator


class TestSemanticMetadata:
    """Test standardized semantic metadata structure."""

    def _build_batch_with_text(self, text: str):
        """Helper to build batch with governance context."""
        adapter = IranianLawAdapter(
            law_id="law:semantic_test",
            law_name="قانون تست معنایی",
            source_uri="test://semantic",
            correlation_id="test-semantic-123",
        )

        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://semantic"
            request = Request()

        with IngestionExecutionGate.enter(IngestionExecutionRequest(
            adapter_name="IranianLawAdapter",
            source="test://semantic",
            author_id="test-author",
            correlation_id="test-semantic-123",
        )):
            return adapter.build_batch(text)

    def test_obligation_has_deontic_operator(self):
        """Obligation extraction should have OBLIGATION deontic operator."""
        text = "ماده ۱: شرکت مکلف است گزارش مالی ارائه دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:obligation" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_OBLIGATION"
        assert fact.metadata["semantic"]["deontic_operator"] == "OBLIGATION"
        assert fact.metadata["semantic"]["semantic_type"] == "obligation"
        assert fact.confidence == 0.85
        assert fact.metadata["semantic"]["extraction_method"] == "deterministic-regex"
        assert fact.metadata["semantic"]["confidence_reason"] == "regex-pattern-match"

    def test_prohibition_has_deontic_operator(self):
        """Prohibition extraction should have PROHIBITION deontic operator."""
        text = "ماده ۲: شرکت ممنوع است از فعالیت غیرمجاز."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:prohibition" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_PROHIBITION"
        assert fact.metadata["semantic"]["deontic_operator"] == "PROHIBITION"
        assert fact.metadata["semantic"]["semantic_type"] == "prohibition"

    def test_permission_has_deontic_operator(self):
        """Permission extraction should have PERMISSION deontic operator."""
        text = "ماده ۳: شرکت می‌تواند شعبه جدید تأسیس کند."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:permission" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_PERMISSION"
        assert fact.metadata["semantic"]["deontic_operator"] == "PERMISSION"
        assert fact.metadata["semantic"]["semantic_type"] == "permission"

    def test_right_has_no_deontic_operator(self):
        """Right extraction should have None deontic operator."""
        text = "ماده ۴: شرکت حق دارد از تسهیلات استفاده کند."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:right" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.predicate == "HAS_RIGHT"
        assert fact.metadata["semantic"]["deontic_operator"] is None
        assert fact.metadata["semantic"]["semantic_type"] == "right"

    def test_metadata_structure_standardized(self):
        """Metadata should have standardized nested structure."""
        text = "ماده ۱: شرکت مکلف است گزارش دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        
        # Check semantic section
        assert "semantic" in fact.metadata
        assert "semantic_type" in fact.metadata["semantic"]
        assert "deontic_operator" in fact.metadata["semantic"]
        assert "extraction_method" in fact.metadata["semantic"]
        assert "confidence_reason" in fact.metadata["semantic"]
        
        # Check extraction section
        assert "extraction" in fact.metadata
        assert "ordinal" in fact.metadata["extraction"]
        assert "pattern" in fact.metadata["extraction"]
        assert "source" in fact.metadata["extraction"]
        
        # Check domain section
        assert "domain" in fact.metadata
        assert fact.metadata["domain"] == "legal"

    def test_provenance_preserved(self):
        """Provenance should be preserved in semantic facts."""
        text = "ماده ۱: شرکت باید گزارش دهد."
        batch = self._build_batch_with_text(text)
        
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 1
        
        fact = semantic_facts[0]
        assert fact.provenance is not None
        assert len(fact.source_spans) > 0

    def test_document_temporal_metadata_preserved(self):
        """Document-level temporal metadata should be preserved."""
        text = "ماده ۱: از تاریخ ۱۴۰۰/۰۱/۰۱ لازم‌الاجرا است."
        batch = self._build_batch_with_text(text)
        
        assert "temporal" in batch.documents[0].metadata
        assert "effective_date" in batch.documents[0].metadata["temporal"]
        # Persian digits are preserved as-is
        assert batch.documents[0].metadata["temporal"]["effective_date"] == "۱۴۰۰/۰۱/۰۱"

    def test_extraction_counts_unchanged(self):
        """Extraction counts should remain unchanged."""
        text = """
قانون تست
ماده ۱: شرکت مکلف است گزارش مالی ارائه دهد.
ماده ۲: شرکت ممنوع است از فعالیت غیرمجاز.
ماده ۳: شرکت می‌تواند شعبه جدید تأسیس کند.
ماده ۴: شرکت اختیار دارد تصمیم بگیرد.
"""
        batch = self._build_batch_with_text(text)
        
        # Should have 4 semantic facts (one per article)
        semantic_facts = [f for f in batch.facts if ":semantic:" in f.fact_id]
        assert len(semantic_facts) == 4
        
        # Should have 4 article facts
        article_facts = [f for f in batch.facts if ":article:" in f.fact_id]
        assert len(article_facts) == 4
