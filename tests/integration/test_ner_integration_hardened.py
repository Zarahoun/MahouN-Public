"""
HARDENED NER Integration Tests
===============================

Ruthless adversarial testing for NER entity extraction.

Tests cover:
- Adversarial text inputs (code injection, XSS, SQL)
- False positive detection and precision metrics
- Unicode attacks (RTL, zero-width, combining chars)
- Performance degradation attacks (exponential backtracking)
- Cross-lingual entity confusion
- Entity boundary ambiguity
- Malformed Persian text handling
"""

from pathlib import Path
import time
import pytest

from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate


class TestNERAdversarialInputs:
    """Test NER against adversarial and malicious inputs."""

    def _build_batch_with_text(self, text: str):
        """Helper to build batch with governance context."""
        adapter = IranianLawAdapter(
            law_id="law:test_adversarial",
            law_name="قانون تست",
            source_uri="test://adversarial",
            correlation_id="test-adv",
        )

        # Mock execution gate
        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://adversarial"
            request = Request()

        original_require_active = IngestionExecutionGate.require_active
        IngestionExecutionGate.require_active = classmethod(lambda cls: DummyPermit())

        try:
            return adapter.build_batch(text)
        finally:
            IngestionExecutionGate.require_active = original_require_active

    def test_code_injection_in_entity_text(self):
        """NER should not execute embedded code in entity text."""
        text = """قانون تست
ماده ۱
این قانون توسط شرکت <script>alert('xss')</script> تصویب شد.
ماده ۲
سازمان $(rm -rf /) مسئول اجرا است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        # Verify entities were extracted but not executed
        assert "article_ner" in doc.metadata
        ner_data = doc.metadata["article_ner"]
        
        # Should have extracted entities
        assert len(ner_data) > 0
        
        # But should not contain raw script tags or shell commands
        for article_id, entities in ner_data.items():
            all_entities = (
                entities["organizations"] + 
                entities["persons"] + 
                entities["legal_concepts"]
            )
            for entity in all_entities:
                # Entity is a dict with 'text' field
                entity_text = entity.get("text", "") if isinstance(entity, dict) else str(entity)
                assert "<script>" not in entity_text.lower()
                assert "rm -rf" not in entity_text

    def test_sql_injection_in_organization_names(self):
        """NER should safely handle SQL injection patterns."""
        text = """قانون تست
ماده ۱
شرکت '; DROP TABLE laws; -- مسئول است.
ماده ۲
سازمان OR 1=1 -- نظارت می‌کند."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        assert "article_ner" in doc.metadata
        # Should not crash and should sanitize entities

    def test_unicode_rtl_override_attack(self):
        """Test RTL override characters don't corrupt entities."""
        # U+202E (Right-to-Left Override)
        text = """قانون تست
ماده ۱
شرکت \u202Eمعکوس\u202C در ایران فعال است.
ماده ۲
سازمان \u202E"هک"\u202C قانونی است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        assert "article_ner" in doc.metadata
        ner_data = doc.metadata["article_ner"]
        
        # Entities should be normalized (RTL chars removed)
        for article_id, entities in ner_data.items():
            for entity in entities["organizations"]:
                assert "\u202E" not in entity, f"RTL override not stripped: {entity}"
                assert "\u202C" not in entity

    def test_zero_width_character_pollution(self):
        """Test zero-width characters don't pollute entities."""
        # U+200B (Zero Width Space), U+FEFF (Zero Width No-Break Space)
        text = """قانون تست
ماده ۱
شرکت\u200Bنامرئی\u200B مسئول است.
ماده ۲
سازمان\uFEFFمخفی\uFEFF نظارت می‌کند."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        ner_data = doc.metadata["article_ner"]
        
        # Zero-width chars should be stripped
        for article_id, entities in ner_data.items():
            for entity in entities["organizations"]:
                assert "\u200B" not in entity
                assert "\uFEFF" not in entity

    def test_combining_character_explosion(self):
        """Test combining diacritics don't cause issues."""
        # Multiple combining diacritics on one character
        text = """قانون تست
ماده ۱
شرکت ا̀́̂̃̄̅̆̇̈̉ مسئول است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        # Should not crash
        assert "article_ner" in doc.metadata

    def test_extremely_long_entity_name(self):
        """Test handling of unreasonably long entity names."""
        long_name = "شرکت" + "ا" * 10000 + "ایران"
        text = f"""قانون تست
ماده ۱
{long_name} مسئول است.
ماده ۲
این ماده معتبر است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        ner_data = doc.metadata["article_ner"]
        
        # Should either skip or truncate long entities
        for article_id, entities in ner_data.items():
            for entity in entities["organizations"]:
                assert len(entity) < 500, f"Entity too long: {len(entity)} chars"

    def test_nested_entity_ambiguity(self):
        """Test nested entity patterns are handled correctly."""
        text = """قانون تست
ماده ۱
شرکت (شرکت داخلی (شرکت تودرتو)) مسئول است.
ماده ۲
سازمان [سازمان فرعی [زیرمجموعه]] نظارت می‌کند."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        ner_data = doc.metadata["article_ner"]
        
        # Should handle nesting gracefully
        assert len(ner_data) > 0

    def test_mixed_arabic_persian_entities(self):
        """Test Arabic/Persian character mixing in entities."""
        text = """قانون تست
ماده ۱
شرکت الإيراني مسئول است.
ماده ۲
سازمان ایرانی-العربي فعال است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        ner_data = doc.metadata["article_ner"]
        
        # Should extract mixed entities correctly
        assert len(ner_data) > 0


class TestNERPerformance:
    """Test NER performance under stress."""

    def _build_batch_with_text(self, text: str):
        """Helper to build batch."""
        adapter = IranianLawAdapter(
            law_id="law:perf_test",
            law_name="قانون تست",
            source_uri="test://perf",
            correlation_id="test-perf",
        )

        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://perf"
            request = Request()

        original_require_active = IngestionExecutionGate.require_active
        IngestionExecutionGate.require_active = classmethod(lambda cls: DummyPermit())

        try:
            return adapter.build_batch(text)
        finally:
            IngestionExecutionGate.require_active = original_require_active

    def test_pathological_regex_backtracking(self):
        """Test regex patterns don't cause exponential backtracking."""
        # Pattern known to cause catastrophic backtracking
        pathological = "ا" * 50 + "ی" * 50
        text = f"""قانون تست
ماده ۱
شرکت {pathological} مسئول است.
ماده ۲
این ماده معتبر است."""
        
        start = time.time()
        batch = self._build_batch_with_text(text)
        duration = time.time() - start
        
        # Should complete in reasonable time (< 5 seconds)
        assert duration < 5.0, f"NER took {duration}s - possible backtracking"

    def test_massive_article_count(self):
        """Test performance with large number of articles."""
        articles = []
        for i in range(1, 101):  # 100 articles
            articles.append(f"ماده {i}\nمتن ماده {i} با شرکت تست{i} و سازمان آزمون{i}.")
        
        text = "قانون تست\n" + "\n\n".join(articles)
        
        start = time.time()
        batch = self._build_batch_with_text(text)
        duration = time.time() - start
        
        # Should complete in reasonable time
        assert duration < 30.0, f"NER took {duration}s for 100 articles"
        
        doc = batch.documents[0]
        ner_data = doc.metadata["article_ner"]
        
        # Should have extracted entities from all articles
        assert len(ner_data) >= 90  # Allow some parsing errors

    def test_deeply_nested_patterns(self):
        """Test deeply nested parentheses don't cause stack overflow."""
        nested = "(" * 100 + "شرکت" + ")" * 100
        text = f"""قانون تست
ماده ۱
متن با {nested} است.
ماده ۲
این ماده معتبر است."""
        
        # Should not crash
        batch = self._build_batch_with_text(text)
        assert batch is not None


class TestNERFalsePositives:
    """Test NER precision and false positive detection."""

    def _build_batch_with_text(self, text: str):
        """Helper."""
        adapter = IranianLawAdapter(
            law_id="law:fp_test",
            law_name="قانون تست",
            source_uri="test://fp",
            correlation_id="test-fp",
        )

        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://fp"
            request = Request()

        original_require_active = IngestionExecutionGate.require_active
        IngestionExecutionGate.require_active = classmethod(lambda cls: DummyPermit())

        try:
            return adapter.build_batch(text)
        finally:
            IngestionExecutionGate.require_active = original_require_active

    def test_common_words_not_extracted_as_entities(self):
        """Common Persian words should not be extracted as entities."""
        text = """قانون تست
ماده ۱
این قانون در ایران اجرا می‌شود.
ماده ۲
هر شخص باید قانون را رعایت کند."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        ner_data = doc.metadata["article_ner"]
        
        # Common words should not be entities
        common_false_positives = ["این", "هر", "باید", "را", "در"]
        
        for article_id, entities in ner_data.items():
            all_entities = (
                entities["persons"] +
                entities["organizations"] +
                entities["courts"] +
                entities["legal_concepts"]
            )
            
            for entity in all_entities:
                assert entity not in common_false_positives, \
                    f"False positive: {entity}"

    def test_numbers_not_extracted_as_organizations(self):
        """Numbers should not be extracted as organization names."""
        text = """قانون تست
ماده ۱
در سال ۱۴۰۰ این قانون تصویب شد.
ماده ۲
مبلغ ۱۰۰۰۰ ریال جریمه است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        ner_data = doc.metadata["article_ner"]
        
        for article_id, entities in ner_data.items():
            for org in entities["organizations"]:
                # Should not be pure numbers
                assert not org.replace("۰۱۲۳۴۵۶۷۸۹", "").strip() == "", \
                    f"Number extracted as org: {org}"

    def test_entity_boundary_precision(self):
        """Test entity boundaries are precise."""
        text = """قانون تست
ماده ۱
شرکت ملی نفت ایران مسئول است.
ماده ۲
دادگاه عالی کشور رسیدگی می‌کند."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        ner_data = doc.metadata["article_ner"]
        
        # Check that multi-word entities are complete
        for article_id, entities in ner_data.items():
            # "شرکت ملی نفت ایران" should be one entity, not split
            orgs = entities["organizations"]
            if any("نفت" in org for org in orgs):
                # Should include full name
                full_entity = [org for org in orgs if "نفت" in org and "ملی" in org]
                assert len(full_entity) > 0, "Multi-word entity was split"


class TestNERCrossLingualAttacks:
    """Test NER against cross-lingual confusion attacks."""

    def _build_batch_with_text(self, text: str):
        """Helper."""
        adapter = IranianLawAdapter(
            law_id="law:xl_test",
            law_name="قانون تست",
            source_uri="test://xl",
            correlation_id="test-xl",
        )

        class DummyPermit:
            class Request:
                adapter_name = "IranianLawAdapter"
                source = "test://xl"
            request = Request()

        original_require_active = IngestionExecutionGate.require_active
        IngestionExecutionGate.require_active = classmethod(lambda cls: DummyPermit())

        try:
            return adapter.build_batch(text)
        finally:
            IngestionExecutionGate.require_active = original_require_active

    def test_english_mixed_with_persian(self):
        """Test English words mixed with Persian."""
        text = """قانون تست
ماده ۱
شرکت Apple Inc ایران مسئول است.
ماده ۲
Google LLC سهامدار است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        # Should handle mixed text
        assert "article_ner" in doc.metadata

    def test_transliterated_entities(self):
        """Test Persian names written in Latin script."""
        text = """قانون تست
ماده ۱
شرکت Sherkat Melli Iran مسئول است.
ماده ۲
این ماده معتبر است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        # Should not crash
        assert "article_ner" in doc.metadata

    def test_homoglyph_attack(self):
        """Test homoglyph characters (lookalikes)."""
        # Cyrillic 'о' vs Latin 'o' vs Persian 'و'
        text = """قانون تست
ماده ۱
شرکت میکrоsоft ایران است.
ماده ۲
این ماده معتبر است."""
        
        batch = self._build_batch_with_text(text)
        doc = batch.documents[0]
        
        # Should handle homoglyphs
        assert "article_ner" in doc.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
