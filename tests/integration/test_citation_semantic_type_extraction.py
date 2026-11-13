"""
Ruthless reality-based tests for AMENDS/REPEALS citation classification.
No mocks - uses real LegalCorpusParser on real Persian legal text.
"""

from pathlib import Path
import tempfile

import pytest

from scripts.build_legal_kg import (
    LegalCorpusParser,
    CanonicalCitation,
    HardenedKnowledgeGraphCompiler,
    IngestionStats,
)


class TestCitationSemanticTypeClassification:
    """Tests for _resolve_citations and _classify_citation_type."""

    @pytest.fixture
    def parser(self) -> LegalCorpusParser:
        """Create a parser with a minimal commercial law text containing
        REFERENCES, AMENDS, and REPEALS citations.

        Body lines avoid starting with "ماده N" to prevent the parser
        from misidentifying them as article headers (known parser bug)."""
        text = """قانون تجارت
ماده ۱
متن ماده یک.

ماده ۲
این قانون بر اساس ماده ۱ تدوین شده است.

ماده ۳
این ماده، ماده ۲ قانون تجارت را اصلاح می‌کند.

ماده ۴
این ماده، ماده ۱ قانون تجارت را لغو می‌کند.

ماده ۵
این ماده، ماده ۱۰ قانون تجارت را نسخ می‌کند.

ماده ۶
این قانون از تاریخ تصویب لازم‌الاجرا است."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = Path(f.name)

        parser = LegalCorpusParser(
            source_path=path,
            default_law_id="law:commercial_code_test",
            default_law_name="قانون تجارت تست",
        )
        yield parser
        path.unlink(missing_ok=True)

    def test_parse_finds_all_articles(self, parser: LegalCorpusParser):
        laws, chapters, articles, citations, records, stats = parser.parse()
        assert len(articles) >= 5, f"Expected >=5 articles, got {len(articles)}"
        article_nums = sorted(int(a.number) for a in articles)
        assert article_nums[:6] == [1, 2, 3, 4, 5, 6]

    def test_citation_types_correctly_classified(self, parser: LegalCorpusParser):
        laws, chapters, articles, citations, records, stats = parser.parse()

        # Map by source article number for readability
        by_source = {}
        for c in citations:
            src_num = c.source_article_id.split(":")[-1]
            by_source.setdefault(src_num, []).append(c)

        # Article 2: references Article 1 ("بر اساس ماده ۱") -> REFERENCES
        art2_cites = by_source.get("2", [])
        assert len(art2_cites) == 1, f"Article 2 citations: {art2_cites}"
        assert art2_cites[0].citation_type == "REFERENCES"
        assert art2_cites[0].status == "RESOLVED"
        assert art2_cites[0].target_article_id == "article:commercial_code_test:article:1"

        # Article 3: "ماده ۲ ... اصلاح می‌کند" -> AMENDS
        art3_cites = by_source.get("3", [])
        assert len(art3_cites) == 1
        assert art3_cites[0].citation_type == "AMENDS"
        assert art3_cites[0].status == "RESOLVED"
        assert art3_cites[0].target_article_id == "article:commercial_code_test:article:2"

        # Article 4: "ماده ۱ ... لغو می‌کند" -> REPEALS
        art4_cites = by_source.get("4", [])
        assert len(art4_cites) == 1
        assert art4_cites[0].citation_type == "REPEALS"
        assert art4_cites[0].status == "RESOLVED"
        assert art4_cites[0].target_article_id == "article:commercial_code_test:article:1"

        # Article 5: "ماده ۱۰ ... نسخ می‌کند" -> REPEALS (UNRESOLVED because article 10 doesn't exist)
        art5_cites = by_source.get("5", [])
        assert len(art5_cites) == 1
        assert art5_cites[0].citation_type == "REPEALS"
        assert art5_cites[0].status == "UNRESOLVED"
        assert art5_cites[0].target_article_id == "article:commercial_code_test:article:10"

        # Article 6: no citations
        art6_cites = by_source.get("6", [])
        assert len(art6_cites) == 0

    def test_stats_counts_amends_and_repeals(self, parser: LegalCorpusParser):
        laws, chapters, articles, citations, records, stats = parser.parse()
        # The text has: 1 AMENDS (art3), 2 REPEALS (art4, art5), 1 REFERENCES (art2)
        assert stats.amended_citations == 1
        assert stats.repealed_citations == 2
        assert stats.resolved_citations == 3  # art2, art3, art4
        assert stats.unresolved_citations == 1  # art5

    def test_classify_citation_type_edge_cases(self):
        """Test _classify_citation_type directly with various context windows."""
        classify = LegalCorpusParser._classify_citation_type

        # AMENDS triggers
        assert classify("اصلاح می‌شود") == "AMENDS"
        assert classify("اصلاح می‌گردد") == "AMENDS"
        assert classify("اصلاح می‌کند") == "AMENDS"
        assert classify("اصلاح نموده") == "AMENDS"
        assert classify("جایگزین می‌شود") == "AMENDS"
        # With ZWNJ (U+200C)
        assert classify("اصلاح می\u200cشود") == "AMENDS"
        assert classify("اصلاح می\u200cگردد") == "AMENDS"

        # REPEALS triggers
        assert classify("نسخ می‌شود") == "REPEALS"
        assert classify("لغو می‌گردد") == "REPEALS"
        assert classify("ابطال می‌شود") == "REPEALS"
        assert classify("ملغی است") == "REPEALS"
        assert classify("ملغی می‌شود") == "REPEALS"
        assert classify("ملغی اعلام می‌شود") == "REPEALS"
        # With ZWNJ
        assert classify("نسخ می\u200cشود") == "REPEALS"
        assert classify("لغو می\u200cگردد") == "REPEALS"

        # Plain reference (no trigger)
        assert classify("به موجب ماده ۳ این قانون") == "REFERENCES"
        assert classify("طبق ماده ۵") == "REFERENCES"
        assert classify("استناد به اصل ۱") == "REFERENCES"

        # Empty/unknown -> REFERENCES (fail-closed default)
        assert classify("") == "REFERENCES"
        assert classify("متن بی‌ارتباط") == "REFERENCES"

    def test_classify_ambiguous_window_uses_earliest_trigger(self):
        """When both AMENDS and REPEALS triggers appear, earliest wins."""
        classify = LegalCorpusParser._classify_citation_type
        # "لغو می‌شود و اصلاح می‌شود" -> REPEALS appears first
        assert classify("لغو می‌شود و اصلاح می‌شود") == "REPEALS"
        # "اصلاح می‌شود و لغو می‌شود" -> AMENDS appears first
        assert classify("اصلاح می‌شود و لغو می‌شود") == "AMENDS"

    def test_multi_number_citation_same_classification(self, parser: LegalCorpusParser):
        """A multi-number citation like 'ماده ۲ و ۳' gets same classification for both."""
        text = """قانون تجارت
ماده ۲
متن ماده ۲.

ماده ۳
متن ماده ۳.

ماده ۴
این ماده به ماده ۲ و ۳ اصلاح می‌کند."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = Path(f.name)

        parser2 = LegalCorpusParser(
            source_path=path,
            default_law_id="law:test",
            default_law_name="تست",
        )
        laws, chapters, articles, citations, records, stats = parser2.parse()
        path.unlink(missing_ok=True)

        # Article 4 cites both 2 and 3 with "اصلاح می‌کند"
        art4_cites = [c for c in citations if c.source_article_id.endswith(":4")]
        assert len(art4_cites) == 2, f"Expected 2 citations from article 4, got {art4_cites}"
        target_nums = {c.target_article_id.split(":")[-1] for c in art4_cites}
        assert target_nums == {"2", "3"}
        for c in art4_cites:
            assert c.citation_type == "AMENDS"


class TestCompilerGroupingWhitelist:
    """Tests for HardenedKnowledgeGraphCompiler._group_citations_by_relationship_type."""

    def test_groups_by_type_correctly(self):
        citations = [
            CanonicalCitation(source_article_id="a:1", target_article_id="a:2", citation_text="t",
                              citation_type="REFERENCES", status="RESOLVED"),
            CanonicalCitation(source_article_id="a:3", target_article_id="a:4", citation_text="t",
                              citation_type="AMENDS", status="RESOLVED"),
            CanonicalCitation(source_article_id="a:5", target_article_id="a:6", citation_text="t",
                              citation_type="AMENDS", status="UNRESOLVED"),
            CanonicalCitation(source_article_id="a:7", target_article_id="a:8", citation_text="t",
                              citation_type="REPEALS", status="RESOLVED"),
        ]
        grouped = HardenedKnowledgeGraphCompiler._group_citations_by_relationship_type(citations)
        assert set(grouped.keys()) == {"REFERENCES", "AMENDS", "REPEALS"}
        assert len(grouped["REFERENCES"]) == 1
        assert len(grouped["AMENDS"]) == 2
        assert len(grouped["REPEALS"]) == 1

    def test_whitelist_rejects_unknown_type(self):
        citations = [
            CanonicalCitation(source_article_id="a:1", target_article_id="a:2", citation_text="t",
                              citation_type="SUPERSEDES", status="RESOLVED"),  # Not in whitelist
        ]
        with pytest.raises(ValueError, match="non-whitelisted relationship type"):
            HardenedKnowledgeGraphCompiler._group_citations_by_relationship_type(citations)

    def test_whitelist_rejects_empty_string(self):
        citations = [
            CanonicalCitation(source_article_id="a:1", target_article_id="a:2", citation_text="t",
                              citation_type="", status="RESOLVED"),
        ]
        with pytest.raises(ValueError, match="non-whitelisted relationship type"):
            HardenedKnowledgeGraphCompiler._group_citations_by_relationship_type(citations)