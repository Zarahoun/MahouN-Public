"""Specialized adapter for Iranian banking-law text corpora."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mahoun.core.governance.ingestion_contract import (
    CanonicalIngestionBatch,
    IngestionContractError,
    IngestionDocument,
    RelationshipFact,
    SemanticFact,
    SourceSpan,
    sha256_text,
)
from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionGate,
)


_ARTICLE_PATTERN = re.compile(r"(?m)^\s*(?:ماده|اصل)\s+([^\s:،؛()]+)[^\n]*")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _canonical_article_number(value: str) -> str:
    normalized = value.translate(_PERSIAN_DIGITS).strip()
    if not normalized or not re.fullmatch(r"\d+", normalized):
        raise IngestionContractError(f"unsupported article number: {value!r}")
    return str(int(normalized))


@dataclass(frozen=True, slots=True)
class BankingLawAdapter:
    """Parse banking-law boundaries without graph mutations."""

    law_id: str
    law_name: str
    source_uri: str
    correlation_id: str

    def build_batch(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> CanonicalIngestionBatch:
        permit = IngestionExecutionGate.require_active()
        if permit.request.adapter_name != type(self).__name__:
            raise RuntimeError("execution permit does not match adapter")
        if permit.request.source != self.source_uri:
            raise RuntimeError("execution permit does not match source")
        if not isinstance(text, str) or not text.strip():
            raise IngestionContractError(
                "banking-law text must contain content"
            )

        source_hash = sha256_text(text)
        provenance = {
            "source": self.source_uri,
            "source_hash": source_hash,
            "correlation_id": self.correlation_id,
            "adapter": type(self).__name__,
        }
        document = IngestionDocument(
            document_id=f"law:{self.law_id}",
            source_uri=self.source_uri,
            text=text,
            provenance=provenance,
            metadata={
                "law_id": self.law_id,
                "law_name": self.law_name,
                **(metadata or {}),
            },
        )

        matches = list(_ARTICLE_PATTERN.finditer(text))
        if not matches:
            raise IngestionContractError(
                "banking-law text contains no article boundaries"
            )

        articles: list[tuple[str, str, int, int]] = []
        seen_numbers: set[str] = set()
        for index, match in enumerate(matches):
            number = _canonical_article_number(match.group(1))
            if number in seen_numbers:
                raise IngestionContractError(
                    f"duplicate article number: {number}"
                )
            seen_numbers.add(number)
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )
            evidence = text[match.start():end].strip()
            articles.append((number, evidence, match.start(), end))

        facts: list[SemanticFact] = []
        relationships: list[RelationshipFact] = []
        for number, evidence, start, end in articles:
            article_id = f"{self.law_id}:article:{number}"
            fact_id = f"fact:{article_id}:document"
            relationship_id = (
                f"rel:{document.document_id}:{article_id}:contains"
            )
            source_span = SourceSpan(
                source_uri=self.source_uri,
                start=start,
                end=end,
                text_hash=sha256_text(text[start:end]),
            )
            facts.append(
                SemanticFact(
                    fact_id=fact_id,
                    subject_id=document.document_id,
                    predicate="REFERENCES",
                    object_id=article_id,
                    evidence_text=evidence,
                    provenance=provenance,
                    source_spans=(source_span,),
                    object_type="LawArticle",
                )
            )
            relationships.append(
                RelationshipFact(
                    relationship_id=relationship_id,
                    source_id=document.document_id,
                    relationship_type="REFERENCES",
                    target_id=article_id,
                    properties={
                        "article_number": number,
                        "law_id": self.law_id,
                    },
                    provenance=provenance,
                    source_spans=(source_span,),
                )
            )

        return CanonicalIngestionBatch(
            (document,), tuple(facts), tuple(relationships)
        )

    def build_batch_from_path(
        self,
        source_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> CanonicalIngestionBatch:
        text = source_path.read_text(encoding="utf-8")
        return self.build_batch(
            text,
            {"source_path": str(source_path), **(metadata or {})},
        )
