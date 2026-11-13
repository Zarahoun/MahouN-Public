"""Deterministic producer for Iranian laws and regulations.

This adapter contains extraction only.  Materialization remains exclusively in
``GovernedIngestionRuntime``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

from mahoun.core.governance.ingestion_contract import (
    CanonicalIngestionBatch,
    IngestionContractError,
    IngestionDocument,
    RelationshipFact,
    SemanticFact,
    SourceSpan,
    sha256_text,
)
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine
from mahoun.graph.neo4j.enums import DeonticOperator


_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
_SECTION = re.compile(
    r"(?m)^[ \t]*(?P<kind>کتاب|باب|فصل|بخش|مبحث|گفتار)"
    r"[ \t]*(?P<number>[0-9۰-۹٠-٩]+)?[ \t]*(?P<title>[^\n]*)"
)
_ARTICLE = re.compile(
    r"(?m)^[ \t]*(?:ماده|مادّه|اصل)[ \t]*"
    r"(?:[«\"(]?[ \t]*)?(?P<number>[0-9۰-۹٠-٩]+)"
    r"(?:[ \t]*[-–—]?[ \t]*(?P<suffix>مکرر|الحاقی))?[^\n]*"
)
_NOTE = re.compile(
    r"(?m)^[ \t]*(?:تبصره|تبصرە)[ \t]*(?P<number>[0-9۰-۹٠-٩]*)"
    r"[ \t]*[-–—:؛.]?[ \t]*(?P<body>.+?)(?=(?:\n[ \t]*(?:تبصره|تبصرە))|\Z)",
    re.DOTALL,
)
_ITEM = re.compile(
    r"(?m)^[ \t]*(?:بند[ \t]*)?(?P<number>[ا-ی]|[0-9۰-۹٠-٩]+)"
    r"[ \t]*[\)\-–—.:][ \t]*(?P<body>.+?)(?=(?:\n[ \t]*(?:[ا-ی]|[0-9۰-۹٠-٩]+)[ \t]*[\)\-–—.:])|\Z)",
    re.DOTALL,
)
_REFERENCE = re.compile(
    r"(?:مطابق|به موجب|بر اساس|موضوع|مستند به|وفق|مندرج در|ماده)"
    r"[ \t]*(?:ماده|اصل)?[ \t]*(?P<number>[0-9۰-۹٠-٩]+)"
)
_CROSS_LAW_REFERENCE = re.compile(
    r"(?:مطابق|به موجب|بر اساس|موضوع|مستند به|وفق|مندرج در)"
    r"[ \t]*(?:ماده|اصل)?[ \t]*(?P<number>[0-9۰-۹٠-٩]+)"
    r"[ \t]*(?:قانون|آیین‌نامه|مصوبه)[ \t]*(?P<law_name>.+?)(?:[؛.\n]|$)",
    re.DOTALL,
)
_CONDITION = re.compile(
    r"(?P<body>(?:هرگاه|چنانچه|در صورتی که|مشروط بر اینکه|هر کس).{8,260}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_EXCEPTION = re.compile(
    r"(?P<body>(?:مگر|به استثنای|جز در موارد|در غیر این صورت).{5,220}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_SANCTION = re.compile(
    r"(?P<body>(?:به حبس|حبس|جزای نقدی|جریمه|مصادره|ضبط|مجازات).{3,220}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_OBLIGATION = re.compile(
    r"(?P<body>(?:مکلف است|باید|موظف است|الزام است|ملزم است).{5,300}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_PROHIBITION = re.compile(
    r"(?P<body>(?:ممنوع است|نمی‌تواند|نباید|مجاز نیست|جایز نیست).{5,300}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_PERMISSION = re.compile(
    r"(?P<body>(?:مجاز است|می‌تواند|حق دارد|صلاحیت دارد).{5,300}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_RIGHT = re.compile(
    r"(?P<body>(?:حق|اختیار|صلاحیت).{5,300}?)(?=[؛.\n]|$)",
    re.DOTALL,
)
_EFFECTIVE_DATE = re.compile(
    r"(?:از تاریخ|از|به تاریخ|تاریخ اجرا|تاریخ ابلاغ)[ \t]*(?P<date>\d{4}/\d{1,2}/\d{1,2})",
)
_REPEAL_DATE = re.compile(
    r"(?:ملغی شده|باطل شده|منسوخ شده)[ \t]*(?:از تاریخ|در تاریخ)?[ \t]*(?P<date>\d{4}/\d{1,2}/\d{1,2})?",
)

_KNOWN_LAW_MAPPINGS: dict[str, str] = {
    "قانون مدنی": "law:civil_code",
    "قانون تجارت": "law:commercial_code",
    "قانون صدور چک": "law:cheque_law",
    "قانون مجازات اسلامی": "law:islamic_penal_code",
    "قانون آیین دادرسی مدنی": "law:civil_procedure_code",
    "قانون آیین دادرسی کیفری": "law:criminal_procedure_code",
    "قانون مسئولیت مدنی": "law:civil_liability_law",
    "قانون ارتقای سلامت نظام اداری": "law:administrative_integrity_law",
    "قانون مبارزه با پولشویی": "law:anti_money_laundering_law",
    "قانون پولی و بانکی کشور": "law:monetary_banking_1351",
    "شرایط عمومی پیمان": "regulation:nashrieh_4311",
    "نشریه ۴۳۱۱": "regulation:nashrieh_4311",
    "نشریه 4311": "regulation:nashrieh_4311",
}


def _number(value: str) -> str:
    normalized = value.translate(_DIGITS).strip()
    if not normalized.isdigit():
        raise IngestionContractError(f"unsupported legal number: {value!r}")
    return str(int(normalized))


def _span(source_uri: str, text: str, start: int, end: int) -> SourceSpan:
    evidence = text[start:end]
    return SourceSpan(
        source_uri=source_uri,
        start=start,
        end=end,
        text_hash=sha256_text(evidence),
    )


@dataclass(frozen=True, slots=True)
class IranianLawAdapter:
    law_id: str
    law_name: str
    source_uri: str
    correlation_id: str

    def build_batch(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> CanonicalIngestionBatch:
        permit = IngestionExecutionGate.require_active()
        if permit.request.adapter_name != type(self).__name__:
            raise RuntimeError("execution permit does not match adapter")
        if permit.request.source != self.source_uri:
            raise RuntimeError("execution permit does not match source")
        if not isinstance(text, str) or not text.strip():
            raise IngestionContractError("law text must contain content")

        source_hash = sha256_text(text)
        provenance = {
            "source": self.source_uri,
            "source_hash": source_hash,
            "correlation_id": self.correlation_id,
            "adapter": type(self).__name__,
        }
        document_id = f"law:{self.law_id}"
        document = IngestionDocument(
            document_id=document_id,
            source_uri=self.source_uri,
            text=text,
            provenance=provenance,
            metadata={
                "law_id": self.law_id,
                "law_name": self.law_name,
                "document_type": "iranian_law",
                **(metadata or {}),
            },
            parser_version="iranian-law-adapter-2",
        )

        sections = list(_SECTION.finditer(text))
        articles = list(_ARTICLE.finditer(text))
        if not articles:
            raise IngestionContractError(f"law text contains no article boundaries: {self.law_id}")

        facts: list[SemanticFact] = []
        relationships: list[RelationshipFact] = []
        seen: set[str] = set()

        def emit(
            object_id: str,
            object_type: str,
            subject_id: str,
            predicate: str,
            evidence: str,
            start: int,
            end: int,
            properties: dict[str, Any],
        ) -> None:
            if object_id in seen:
                return
            seen.add(object_id)
            spans = (_span(self.source_uri, text, start, end),)
            item_provenance = {**provenance, "source_span": {"start": start, "end": end}}
            facts.append(
                SemanticFact(
                    fact_id=f"fact:{object_id}",
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    evidence_text=evidence.strip(),
                    provenance=item_provenance,
                    source_spans=spans,
                    object_type=object_type,
                )
            )
            relationships.append(
                RelationshipFact(
                    relationship_id=f"rel:{subject_id}:{object_id}:{predicate}",
                    source_id=subject_id,
                    relationship_type=predicate,
                    target_id=object_id,
                    properties=properties,
                    provenance=item_provenance,
                    source_spans=spans,
                )
            )

        # Initialize NER engine once for all articles
        ner_engine = None
        try:
            ner_engine = LegalNEREngine()
        except Exception:
            # NER is best-effort; continue without it if initialization fails
            pass

        # Initialize canonical amendment and repeal extractors along with Quality Gate & Decision Engine
        amendment_extractor = None
        repeal_extractor = None
        quality_gate = None
        decision_engine = None
        try:
            from mahoun.graph.semantic.amendment_extractor import (
                AmendmentExtractor,
                RepealExtractor,
            )
            from mahoun.graph.quality.expansion_quality_gate import (
                ExpansionQualityGate,
                GateDecision,
            )
            from mahoun.graph.quality.expansion_decision import (
                ExpansionDecisionEngine,
                EngineDecision,
            )
            from mahoun.graph.semantic.candidate_relations import (
                CandidateRelation,
                CandidateStatus,
            )
            from mahoun.core.governance.legal_ontology_policy import CANONICAL_LEGAL_ONTOLOGY_POLICY
            from mahoun.core.governance.ontology_enforcer import OntologyEnforcer

            amendment_extractor = AmendmentExtractor()
            repeal_extractor = RepealExtractor()
            ontology_enforcer = OntologyEnforcer(policy=CANONICAL_LEGAL_ONTOLOGY_POLICY)
            quality_gate = ExpansionQualityGate(ontology_enforcer=ontology_enforcer)
            decision_engine = ExpansionDecisionEngine()
        except Exception as exc:
            logger.warning("Failed to initialize semantic expansion gates/extractors: %s", exc)

        chapter_for_article: dict[str, str] = {}
        seen_article_ids: dict[str, int] = {}
        for index, match in enumerate(articles):
            raw_num = _number(match.group("number"))
            suffix_match = match.group("suffix")
            suffix_clean = suffix_match.strip() if suffix_match else ""
            if "مکرر" in suffix_clean:
                article_key = f"{raw_num}_mokarrar"
            elif "الحاقی" in suffix_clean:
                article_key = f"{raw_num}_elhaqi"
            else:
                article_key = raw_num

            count = seen_article_ids.get(article_key, 0)
            seen_article_ids[article_key] = count + 1
            if count > 0:
                article_key = f"{article_key}_{count + 1}"

            article_id = f"{self.law_id}:article:{article_key}"
            body_end = articles[index + 1].start() if index + 1 < len(articles) else len(text)
            evidence = text[match.start():body_end]
            chapter = next((item for item in reversed(sections) if item.start() < match.start()), None)
            if chapter:
                chapter_id = f"{self.law_id}:chapter:{_number(chapter.group('number')) if chapter.group('number') else 'general'}"
                chapter_for_article[article_id] = chapter_id
                emit(
                    chapter_id, "LawChapter", document_id, "CONTAINS",
                    text[chapter.start():chapter.end()], chapter.start(), chapter.end(),
                    {"number": chapter.group("number") or "general", "title": chapter.group("title").strip()},
                )
                parent = chapter_id
            else:
                parent = document_id
            emit(article_id, "LawArticle", parent, "CONTAINS", evidence, match.start(), body_end, {"article_number": raw_num, "article_key": article_key})

            for note_index, note in enumerate(_NOTE.finditer(evidence), start=1):
                note_number = _number(note.group("number")) if note.group("number").strip() else str(note_index)
                note_id = f"{article_id}:clause:{note_number}"
                start = match.start() + note.start()
                emit(note_id, "LawClause", article_id, "CONTAINS", note.group(0), start, match.start() + note.end(), {"clause_type": "note", "number": note_number})

            for item_index, item in enumerate(_ITEM.finditer(evidence), start=1):
                item_number = item.group("number").translate(_DIGITS)
                item_id = f"{article_id}:clause:item:{item_number or item_index}"
                start = match.start() + item.start()
                emit(item_id, "LawClause", article_id, "CONTAINS", item.group(0), start, match.start() + item.end(), {"clause_type": "item", "number": item_number or str(item_index)})

            for pattern, label, object_type, predicate in (
                (_CONDITION, "condition", "LegalCondition", "HAS_CONDITION"),
                (_EXCEPTION, "exception", "LegalException", "HAS_EXCEPTION"),
                (_SANCTION, "sanction", "LegalSanction", "HAS_SANCTION"),
            ):
                for occurrence, found in enumerate(pattern.finditer(evidence), start=1):
                    start = match.start() + found.start()
                    object_id = f"{article_id}:{label}:{occurrence}"
                    emit(object_id, object_type, article_id, predicate, found.group("body"), start, match.start() + found.end(), {"extraction": "deterministic-regex", "ordinal": occurrence})

            # Semantic fact extraction for legal obligations, prohibitions, permissions, rights
            for pattern, semantic_type, deontic_op in (
                (_OBLIGATION, "obligation", DeonticOperator.OBLIGATION),
                (_PROHIBITION, "prohibition", DeonticOperator.PROHIBITION),
                (_PERMISSION, "permission", DeonticOperator.PERMISSION),
                (_RIGHT, "right", None),
            ):
                for occurrence, found in enumerate(pattern.finditer(evidence), start=1):
                    start = match.start() + found.start()
                    object_id = f"{article_id}:{semantic_type}:{occurrence}"
                    emit(
                        object_id=object_id,
                        object_type=f"Legal{semantic_type.capitalize()}",
                        subject_id=article_id,
                        predicate=f"HAS_{semantic_type.upper()}",
                        evidence=found.group("body"),
                        start=start,
                        end=match.start() + found.end(),
                        properties={
                            "extraction": "deterministic-regex",
                            "ordinal": occurrence,
                            "deontic_operator": deontic_op.value if deontic_op else None,
                        },
                    )

            # Temporal information extraction
            effective_date_match = _EFFECTIVE_DATE.search(evidence)
            if effective_date_match:
                document.metadata.setdefault("temporal", {})["effective_date"] = effective_date_match.group("date")

            repeal_date_match = _REPEAL_DATE.search(evidence)
            if repeal_date_match:
                document.metadata.setdefault("temporal", {})["repeal_date"] = repeal_date_match.group("date") if repeal_date_match.group("date") else "unknown"

            # Cross-law reference extraction
            for occurrence, cross_ref in enumerate(_CROSS_LAW_REFERENCE.finditer(evidence), start=1):
                target_number = _number(cross_ref.group("number"))
                law_name = cross_ref.group("law_name").strip()
                # Resolve via canonical known law mappings if recognized, otherwise construct slug
                canonical_mapped = _KNOWN_LAW_MAPPINGS.get(law_name) or _KNOWN_LAW_MAPPINGS.get(f"قانون {law_name}")
                if canonical_mapped:
                    target_law_id = canonical_mapped
                else:
                    target_law_id = f"law:{law_name.lower().replace(' ', '_')}"
                target_article_id = f"{target_law_id}:article:{target_number}"
                start = match.start() + cross_ref.start()
                emit(
                    f"{article_id}:cross_reference:{target_law_id}:{target_number}:{occurrence}",
                    "LawReference",
                    article_id,
                    "REFERENCES",
                    cross_ref.group(0),
                    start,
                    match.start() + cross_ref.end(),
                    {
                        "target_article_id": target_article_id,
                        "target_law_id": target_law_id,
                        "target_law_name": law_name,
                        "target_article_number": target_number,
                        "resolution": "cross-law-explicit",
                    },
                )

            for occurrence, reference in enumerate(_REFERENCE.finditer(evidence), start=1):
                target = _number(reference.group("number"))
                target_id = f"{self.law_id}:article:{target}"
                if target_id == article_id:
                    continue
                start = match.start() + reference.start()
                emit(
                    f"{article_id}:reference:{target}:{occurrence}",
                    "LawReference",
                    article_id,
                    "REFERENCES",
                    reference.group(0),
                    start,
                    match.start() + reference.end(),
                    {"target_article_id": target_id, "target_article_number": target, "resolution": "same-law-explicit"},
                )

            # Canonical Amendment extraction (AMENDS relationships) guarded by ExpansionQualityGate & DecisionEngine
            if amendment_extractor:
                try:
                    amend_candidates = amendment_extractor.extract(
                        evidence,
                        {"source_id": article_id, "law_id": self.law_id},
                    )
                    for occurrence, item in enumerate(amend_candidates, start=1):
                        props = item.get("properties", {})
                        tgt_num = props.get("target_article_number")
                        tgt_law = props.get("target_law_id") or self.law_id
                        target_article_id = f"{tgt_law}:article:{tgt_num}"
                        span = item.get("provenance", {}).get("evidence_span", (0, len(evidence)))
                        confidence = float(item.get("provenance", {}).get("confidence", 0.9))
                        pattern_used = item.get("provenance", {}).get("pattern_used", "explicit_amendment")
                        cand_id = f"cand:{article_id}:amends:{tgt_law}:{tgt_num}:{occurrence}"

                        # ExpansionQualityGate & DecisionEngine evaluation
                        gate_decision_val = "ALLOW"
                        engine_decision_val = "REVIEW"
                        quality_score_val = 0.9
                        checks_passed_list = []
                        checks_flagged_list = []

                        if quality_gate and decision_engine:
                            cand_rel = CandidateRelation(
                                candidate_id=cand_id,
                                type="AMENDS",
                                from_id=article_id,
                                to_id=target_article_id,
                                status=CandidateStatus.VALIDATED,
                                confidence=confidence,
                                extractor_name="amendment_extractor",
                                extraction_method="regex_pattern",
                                evidence_span=span,
                                pattern_used=pattern_used,
                                target_article_number=str(tgt_num) if tgt_num is not None else None,
                                target_law_id=tgt_law,
                                resolved_target_id=target_article_id,
                            )
                            gate_res = quality_gate.evaluate(cand_rel)
                            dec_rec = decision_engine.propose(cand_rel)

                            # Strict Fail-Closed invariant: reject if gate or engine rejects
                            if gate_res.decision == GateDecision.REJECT or dec_rec.proposed_decision == EngineDecision.REJECT:
                                logger.warning(
                                    "Candidate %s REJECTED by ExpansionQualityGate: %s (checks failed: %s)",
                                    cand_id,
                                    gate_res.reason,
                                    gate_res.checks_failed,
                                )
                                continue

                            gate_decision_val = gate_res.decision.value
                            engine_decision_val = dec_rec.proposed_decision.value
                            quality_score_val = round(gate_res.quality_score, 4)
                            checks_passed_list = list(gate_res.checks_passed)
                            checks_flagged_list = list(gate_res.checks_flagged)

                        # High-risk temporal mutation strictly requires human review (HITL Policy)
                        requires_human_review = True
                        review_status = "pending_human_review"

                        start = match.start() + span[0]
                        end = match.start() + span[1]
                        evidence_text = evidence[span[0]:span[1]] if span[1] <= len(evidence) else evidence
                        emit(
                            f"{article_id}:amends:{tgt_law}:{tgt_num}:{occurrence}",
                            "LawReference",
                            article_id,
                            "AMENDS",
                            evidence_text,
                            start,
                            end,
                            {
                                "target_article_id": target_article_id,
                                "target_law_id": tgt_law,
                                "target_article_number": tgt_num,
                                "amendment_type": props.get("amendment_type", "explicit_amendment"),
                                "confidence": confidence,
                                "extractor": "amendment_extractor",
                                "pattern_used": pattern_used,
                                "resolution": "same-law-amendment" if tgt_law == self.law_id else "cross-law-amendment",
                                "requires_human_review": requires_human_review,
                                "review_status": review_status,
                                "gate_decision": gate_decision_val,
                                "engine_decision": engine_decision_val,
                                "quality_score": quality_score_val,
                                "checks_passed": checks_passed_list,
                                "checks_flagged": checks_flagged_list,
                                "candidate_id": cand_id,
                            },
                        )
                except Exception as exc:
                    logger.warning("Error during amendment extraction/gating for %s: %s", article_id, exc)

            # Canonical Repeal extraction (REPEALS relationships) guarded by ExpansionQualityGate & DecisionEngine
            if repeal_extractor:
                try:
                    repeal_candidates = repeal_extractor.extract(
                        evidence,
                        {"source_id": article_id, "law_id": self.law_id},
                    )
                    for occurrence, item in enumerate(repeal_candidates, start=1):
                        props = item.get("properties", {})
                        tgt_num = props.get("target_article_number")
                        tgt_law = props.get("target_law_id") or self.law_id
                        target_article_id = f"{tgt_law}:article:{tgt_num}"
                        span = item.get("provenance", {}).get("evidence_span", (0, len(evidence)))
                        confidence = float(item.get("provenance", {}).get("confidence", 0.9))
                        pattern_used = item.get("provenance", {}).get("pattern_used", "explicit_repeal")
                        cand_id = f"cand:{article_id}:repeals:{tgt_law}:{tgt_num}:{occurrence}"

                        # ExpansionQualityGate & DecisionEngine evaluation
                        gate_decision_val = "ALLOW"
                        engine_decision_val = "REVIEW"
                        quality_score_val = 0.9
                        checks_passed_list = []
                        checks_flagged_list = []

                        if quality_gate and decision_engine:
                            cand_rel = CandidateRelation(
                                candidate_id=cand_id,
                                type="REPEALS",
                                from_id=article_id,
                                to_id=target_article_id,
                                status=CandidateStatus.VALIDATED,
                                confidence=confidence,
                                extractor_name="repeal_extractor",
                                extraction_method="regex_pattern",
                                evidence_span=span,
                                pattern_used=pattern_used,
                                target_article_number=str(tgt_num) if tgt_num is not None else None,
                                target_law_id=tgt_law,
                                resolved_target_id=target_article_id,
                            )
                            gate_res = quality_gate.evaluate(cand_rel)
                            dec_rec = decision_engine.propose(cand_rel)

                            # Strict Fail-Closed invariant: reject if gate or engine rejects
                            if gate_res.decision == GateDecision.REJECT or dec_rec.proposed_decision == EngineDecision.REJECT:
                                logger.warning(
                                    "Candidate %s REJECTED by ExpansionQualityGate: %s (checks failed: %s)",
                                    cand_id,
                                    gate_res.reason,
                                    gate_res.checks_failed,
                                )
                                continue

                            gate_decision_val = gate_res.decision.value
                            engine_decision_val = dec_rec.proposed_decision.value
                            quality_score_val = round(gate_res.quality_score, 4)
                            checks_passed_list = list(gate_res.checks_passed)
                            checks_flagged_list = list(gate_res.checks_flagged)

                        # High-risk temporal mutation strictly requires human review (HITL Policy)
                        requires_human_review = True
                        review_status = "pending_human_review"

                        start = match.start() + span[0]
                        end = match.start() + span[1]
                        evidence_text = evidence[span[0]:span[1]] if span[1] <= len(evidence) else evidence
                        emit(
                            f"{article_id}:repeals:{tgt_law}:{tgt_num}:{occurrence}",
                            "LawReference",
                            article_id,
                            "REPEALS",
                            evidence_text,
                            start,
                            end,
                            {
                                "target_article_id": target_article_id,
                                "target_law_id": tgt_law,
                                "target_article_number": tgt_num,
                                "repeal_type": props.get("repeal_type", "explicit_repeal"),
                                "confidence": confidence,
                                "extractor": "repeal_extractor",
                                "pattern_used": pattern_used,
                                "range_start": props.get("range_start"),
                                "range_end": props.get("range_end"),
                                "resolution": "same-law-repeal" if tgt_law == self.law_id else "cross-law-repeal",
                                "requires_human_review": requires_human_review,
                                "review_status": review_status,
                                "gate_decision": gate_decision_val,
                                "engine_decision": engine_decision_val,
                                "quality_score": quality_score_val,
                                "checks_passed": checks_passed_list,
                                "checks_flagged": checks_flagged_list,
                                "candidate_id": cand_id,
                            },
                        )
                except Exception as exc:
                    logger.warning("Error during repeal extraction/gating for %s: %s", article_id, exc)

            # NER extraction: enrich article metadata with recognized entities
            # This runs for each article individually to ensure all articles get NER
            if ner_engine:
                try:
                    ner_results = ner_engine.extract(evidence)
                    # Attach NER results to the article's metadata in the document
                    document.metadata.setdefault("article_ner", {})[article_id] = {
                        "persons": ner_results.get("persons", []),
                        "organizations": ner_results.get("organizations", []),
                        "courts": ner_results.get("courts", []),
                        "laws": ner_results.get("laws", []),
                        "topics": ner_results.get("topics", []),
                        "legal_concepts": ner_results.get("legal_concepts", []),
                    }

                    # Legal concepts from NER are kept in metadata only, not as SemanticFact
                    # because NER doesn't provide precise source offsets required by contract
                except Exception:
                    # NER is best-effort enrichment; never fail ingestion if it errors
                    pass

        return CanonicalIngestionBatch(
            documents=(document,),
            facts=tuple(facts),
            relationships=tuple(relationships),
            adapter_name=type(self).__name__,
            parser_version="iranian-law-adapter-2",
            warnings=(
                "Cross-law references require a later governed reconciliation pass.",
            ),
        )

    def build_batch_from_path(self, source_path: str, metadata: dict[str, Any] | None = None) -> CanonicalIngestionBatch:
        from pathlib import Path

        path = Path(source_path)
        return self.build_batch(path.read_text(encoding="utf-8"), {"source_path": str(path), **(metadata or {})})
