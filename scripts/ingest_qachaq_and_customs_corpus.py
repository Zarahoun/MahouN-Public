"""
MAHOUN Enterprise Ingestion: Anti-Smuggling & Customs Legal Corpus
=================================================================
Ingests 15 Iranian statutes, executive bylaws, and directives in Anti-Smuggling,
Customs, Foreign Transit, and Border Exchange into the Knowledge Graph.

Pipeline Flow:
1. Extract native digital text from PDF via hardened DocumentHandler
2. Normalize Persian legal typography and structure
3. Parse hierarchical AST (Law, Chapter, Article, Clause)
4. Decompose semantically into Conditions, Sanctions, Exceptions
5. Link Articles to Canonical Concepts ([:REGULATES] with SHA-256)
6. Materialize in Neo4j under IngestionExecutionGate & GovernedNeo4jSession.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env", override=False)
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("DB_NEO4J_PASSWORD", "dev_neo4j_password_2026")
os.environ.setdefault("ENVIRONMENT", "production")

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.ingestion_contract import sha256_text
from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionGate,
    IngestionExecutionRequest,
)
from mahoun.core.governance.mutation_boundary import (
    get_audit_sink,
    set_audit_sink,
)
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
from mahoun.graph.neo4j.connection import get_connection
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink
from mahoun.pipelines.ingestion.document_handlers import extract_document_text
from mahoun.pipelines.ingestion.persian_normalizer import PersianLegalNormalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_qachaq_corpus")
_DRY_RUN = False

# ─── Corpus Manifest ────────────────────────────────────────────────────────
CORPUS_MANIFEST = [
    {
        "file": "Ghachagh01.pdf",
        "law_id": "law:anti_smuggling_goods_currency",
        "title": "قانون مبارزه با قاچاق کالا و ارز",
        "doc_type": "ORDINARY_LAW",
        "enacted_date": "1392/10/03",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh03.pdf",
        "law_id": "law:customs_affairs",
        "title": "قانون امور گمرکی",
        "doc_type": "ORDINARY_LAW",
        "enacted_date": "1390/08/22",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh05.pdf",
        "law_id": "law:foreign_goods_transit",
        "title": "قانون حمل و نقل و عبور کالاهای خارجی از قلمرو جمهوری اسلامی ایران",
        "doc_type": "ORDINARY_LAW",
        "enacted_date": "1374/12/26",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh06.pdf",
        "law_id": "law:border_trade_regulation",
        "title": "قانون ساماندهی مبادلات مرزی",
        "doc_type": "ORDINARY_LAW",
        "enacted_date": "1384/07/06",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh08.pdf",
        "law_id": "law:free_zones_customs_regulations",
        "title": "مقررات صادرات، واردات و امور گمرکی مناطق آزاد تجاری - صنعتی",
        "doc_type": "REGULATION",
        "enacted_date": "1373/02/19",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh09.pdf",
        "law_id": "law:seized_goods_custody_bylaw",
        "title": "آیین‌نامه اجرایی شیوه نگهداری اموال توقیف شده",
        "doc_type": "BYLAW",
        "enacted_date": "1394/01/26",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh10.pdf",
        "law_id": "law:customs_affairs_executive_bylaw",
        "title": "آیین‌نامه اجرایی قانون امور گمرکی",
        "doc_type": "BYLAW",
        "enacted_date": "1391/12/06",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh11.pdf",
        "law_id": "law:border_trade_executive_bylaw",
        "title": "آیین‌نامه اجرایی قانون ساماندهی مبادلات مرزی",
        "doc_type": "BYLAW",
        "enacted_date": "1385/04/28",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh12.pdf",
        "law_id": "law:anti_smuggling_art27_bylaw",
        "title": "آیین‌نامه اجرایی ماده ۲۷ قانون مبارزه با قاچاق کالا و ارز",
        "doc_type": "BYLAW",
        "enacted_date": "1395/03/12",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh17.pdf",
        "law_id": "law:precious_metals_bylaw",
        "title": "آیین‌نامه ورود و صدور فلزات گران‌بها",
        "doc_type": "REGULATION",
        "enacted_date": "1398/06/10",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh18.pdf",
        "law_id": "law:goods_tracking_code_bylaw",
        "title": "آیین‌نامه اجرایی شناسه‌های کالا و رهگیری کالا موضوع ماده ۱۳ قانون مبارزه با قاچاق",
        "doc_type": "BYLAW",
        "enacted_date": "1395/06/24",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh20.pdf",
        "law_id": "law:vehicle_spare_parts_directive",
        "title": "دستورالعمل اجرایی شناسه رهگیری قطعات یدکی وسائل نقلیه",
        "doc_type": "CIRCULAR",
        "enacted_date": "1400/10/15",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh21.pdf",
        "law_id": "law:passenger_foreign_currency_directive",
        "title": "دستورالعمل اجرایی ضوابط ناظر بر ارز همراه مسافر",
        "doc_type": "CIRCULAR",
        "enacted_date": "1399/04/01",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh27.pdf",
        "law_id": "law:home_appliances_tracking_directive",
        "title": "دستورالعمل دریافت شناسه برای لوازم خانگی موجود در بازار و انبارها",
        "doc_type": "CIRCULAR",
        "enacted_date": "1398/10/10",
        "jurisdiction": "IR",
    },
    {
        "file": "Ghachagh28.pdf",
        "law_id": "law:anti_smuggling_art11_stats_directive",
        "title": "دستورالعمل نحوه گردآوری آمار و اطلاعات تبصره ۱ ماده ۱۱ قانون مبارزه با قاچاق",
        "doc_type": "CIRCULAR",
        "enacted_date": "1397/08/20",
        "jurisdiction": "IR",
    },
]


def to_cypher_literal(obj) -> str:
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    elif isinstance(obj, list):
        return "[" + ", ".join(to_cypher_literal(x) for x in obj) + "]"
    elif isinstance(obj, dict):
        return "{" + ", ".join(f"{k}: {to_cypher_literal(v)}" for k, v in obj.items()) + "}"
    elif obj is None:
        return "null"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, (int, float)):
        return str(obj)
    return json.dumps(str(obj), ensure_ascii=False)


def run_governed_cypher(cypher: str, params: Dict[str, Any] = None):
    if _DRY_RUN:
        logger.info(
            "DRY-RUN: skipped governed Cypher mutation (%d parameters)",
            len(params or {}),
        )
        return []

    async def execute_mutation():
        if get_audit_sink() is None:
            set_audit_sink(compose_default_filesystem_sink())
        async with GovernanceContextManager.active_context(
            correlation_id="qachaq-corpus-ingestion",
            execution_mode="STRICT",
            actor_id="qachaq-materializer",
        ):
            with get_connection().governed_session(
                correlation_id="qachaq-corpus-ingestion",
                actor_id="qachaq-materializer",
            ) as session:
                return session.execute_cypher(cypher, params or {})

    return asyncio.run(execute_mutation())


class PersianArticleParser:
    """Parses legal text into Articles, Clauses, and Sections with regex AST."""

    _FORMAT_CHARS = re.compile(r"[\u061c\u200c\u200d\u200e\u200f\u202a-\u202e\ufeff]")
    _ARTICLE_HEADER_PATTERN = re.compile(
        r"(?m)^[ \t]*(?:ماده|مادّه)\s*"
        r"(?:\(\s*)?(?P<pre>[-–—:؛.]?)\s*"
        r"(?P<number>[0-9۰-۹]+)\s*"
        r"(?P<post>مکرر\b|[-–—:؛.]?)",
    )
    _CLAUSE_PATTERN = re.compile(
        r"(?:^|\n)\s*(?:تبصره|تبصرە)\s*([0-9۰-۹]*)\s*[-–—:؛.]?\s*(.+?)"
        r"(?=(?:\n\s*(?:تبصره|تبصرە))|\Z)",
        re.DOTALL,
    )
    _DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

    @classmethod
    def parse_articles(cls, text: str, law_id: str) -> List[Dict[str, Any]]:
        text = cls._FORMAT_CHARS.sub("", text)
        articles = []
        raw_headers = list(cls._ARTICLE_HEADER_PATTERN.finditer(text))
        headers = [
            header for header in raw_headers
            if header.group("pre") or header.group("post")
        ]
        if not headers:
            raise ValueError(f"No article boundaries found for {law_id}")

        for index, header in enumerate(headers):
            raw_num = header.group("number").translate(cls._DIGIT_MAP)
            body_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
            art_body = text[header.end():body_end].strip()
            art_id = f"{law_id}:article:{raw_num}"

            # Extract clauses (تبصره‌ها)
            clauses = []
            clause_matches = list(cls._CLAUSE_PATTERN.finditer(art_body))
            for c_idx, cm in enumerate(clause_matches, start=1):
                c_num = cm.group(1).translate(cls._DIGIT_MAP) or str(c_idx)
                c_body = " ".join(cm.group(2).strip().split())
                clauses.append({
                    "id": f"{art_id}:clause:{c_num}",
                    "number": c_num,
                    "content": c_body,
                    "sha256": sha256_text(c_body),
                })

            clean_body = " ".join(art_body.split())
            articles.append({
                "id": art_id,
                "number": raw_num,
                "title": f"ماده {raw_num}",
                "content": clean_body,
                "sha256": sha256_text(clean_body),
                "clauses": clauses,
            })

        return articles


def main(dry_run: bool = False):
    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "ingest_qachaq_and_customs_corpus.py",
        "POST /api/v1/ingest/canonical-batch",
    )
    global _DRY_RUN
    _DRY_RUN = dry_run
    IngestionExecutionGate.require_active()
    start_time = time.time()
    logger.info("=== Starting Ingestion of Anti-Smuggling & Customs Legal Corpus ===")

    qachaq_dir = REPO_ROOT / "LAWS" / "qachaq"
    semantic_extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)
    normalizer = PersianLegalNormalizer()

    total_laws = 0
    total_articles = 0
    total_clauses = 0
    total_conditions = 0
    total_sanctions = 0
    total_exceptions = 0
    total_concept_links = 0

    laws_records = []
    articles_records = []
    clauses_records = []
    conditions_records = []
    sanctions_records = []
    exceptions_records = []
    concept_links_records = []

    for manifest in CORPUS_MANIFEST:
        pdf_file = qachaq_dir / manifest["file"]
        if not pdf_file.is_file():
            logger.warning("File not found: %s", pdf_file)
            continue

        logger.info("Processing: %s (%s)", manifest["title"], manifest["file"])
        ext_res = extract_document_text(str(pdf_file))
        if not ext_res.success or not ext_res.text:
            logger.error("Failed to extract: %s", pdf_file)
            continue

        normalized_text = normalizer.normalize_legal_text(
            ext_res.text,
            whitespace=False,
        )
        law_hash = sha256_text(normalized_text)

        laws_records.append({
            "id": manifest["law_id"],
            "title": manifest["title"],
            "doc_type": manifest["doc_type"],
            "enacted_date": manifest["enacted_date"],
            "jurisdiction": manifest["jurisdiction"],
            "sha256": law_hash,
            "source_file": manifest["file"],
        })
        total_laws += 1

        try:
            parsed_articles = PersianArticleParser.parse_articles(
                normalized_text,
                manifest["law_id"],
            )
        except ValueError:
            logger.exception("Parser failed closed for %s", manifest["file"])
            raise
        logger.info("  -> Parsed %d articles from %s", len(parsed_articles), manifest["file"])

        for art in parsed_articles:
            articles_records.append({
                "id": art["id"],
                "law_id": manifest["law_id"],
                "number": art["number"],
                "title": art["title"],
                "content": art["content"][:10000],
                "sha256": art["sha256"],
            })
            total_articles += 1

            for c in art["clauses"]:
                clauses_records.append({
                    "id": c["id"],
                    "article_id": art["id"],
                    "number": c["number"],
                    "content": c["content"][:10000],
                    "sha256": c["sha256"],
                })
                total_clauses += 1

            # Use the canonical proof-carrying semantic extractor API.
            decomposition = semantic_extractor.decompose_article(
                article_id=art["id"],
                law_id=manifest["law_id"],
                raw_text=art["content"],
            )
            assertions = semantic_extractor.extract_concept_assertions(
                article_id=art["id"],
                raw_text=art["content"],
            )

            for cond in decomposition.conditions:
                conditions_records.append({
                    "id": cond.id,
                    "article_id": art["id"],
                    "type": cond.trigger_keyword,
                    "text": cond.condition_text,
                    "sha256": decomposition.text_hash,
                })
                total_conditions += 1

            for sanc in decomposition.sanctions:
                sanctions_records.append({
                    "id": sanc.id,
                    "article_id": art["id"],
                    "type": sanc.sanction_type,
                    "severity": None,
                    "text": sanc.sanction_text,
                    "sha256": decomposition.text_hash,
                })
                total_sanctions += 1

            for exc in decomposition.exceptions:
                exceptions_records.append({
                    "id": exc.id,
                    "article_id": art["id"],
                    "type": exc.trigger_keyword,
                    "text": exc.exception_text,
                    "sha256": decomposition.text_hash,
                })
                total_exceptions += 1

            for assertion in assertions:
                concept_links_records.append({
                    "article_id": art["id"],
                    "concept_id": assertion.target_entity_id,
                    "confidence": 1.0,
                    "evidence_span": assertion.evidence_text_span,
                    "evidence_sha256": assertion.evidence_sha256,
                })
                total_concept_links += 1

    logger.info(
        "📊 Extraction Summary: %d Laws, %d Articles, %d Clauses, %d Conditions, %d Sanctions, %d Exceptions, %d Concept links",
        total_laws, total_articles, total_clauses, total_conditions, total_sanctions, total_exceptions, total_concept_links,
    )

    # ─── Materialization in Neo4j ───────────────────────────────────────────
    logger.info("--- Step 1: Materializing Law Nodes ---")
    law_cypher = """
    UNWIND $laws AS item
    MERGE (l:Law {id: item.id})
    SET l.title = item.title,
        l.doc_type = item.doc_type,
        l.enacted_date = item.enacted_date,
        l.jurisdiction = item.jurisdiction,
        l.sha256 = item.sha256,
        l.source_file = item.source_file;
    """
    run_governed_cypher(law_cypher, {"laws": laws_records})

    logger.info("--- Step 2: Materializing Article Nodes & CONTAINS Edges ---")
    batch_size = 100
    for i in range(0, len(articles_records), batch_size):
        chunk = articles_records[i : i + batch_size]
        art_cypher = """
        UNWIND $articles AS item
        MERGE (a:Article {id: item.id})
        SET a.number = item.number,
            a.title = item.title,
            a.content = item.content,
            a.sha256 = item.sha256
        WITH a, item
        MATCH (l:Law {id: item.law_id})
        MERGE (l)-[:CONTAINS]->(a);
        """
        run_governed_cypher(art_cypher, {"articles": chunk})

    if clauses_records:
        logger.info("--- Step 3: Materializing Clause Nodes & CONTAINS Edges ---")
        for i in range(0, len(clauses_records), batch_size):
            chunk = clauses_records[i : i + batch_size]
            clause_cypher = """
            UNWIND $clauses AS item
            MERGE (c:Clause {id: item.id})
            SET c.number = item.number,
                c.content = item.content,
                c.sha256 = item.sha256
            WITH c, item
            MATCH (a:Article {id: item.article_id})
            MERGE (a)-[:CONTAINS]->(c);
            """
            run_governed_cypher(clause_cypher, {"clauses": chunk})

    if conditions_records:
        logger.info("--- Step 4: Materializing Condition Nodes & HAS_CONDITION Edges ---")
        for i in range(0, len(conditions_records), batch_size):
            chunk = conditions_records[i : i + batch_size]
            cond_cypher = """
            UNWIND $conditions AS item
            MERGE (c:Condition {id: item.id})
            SET c.type = item.type,
                c.text = item.text,
                c.sha256 = item.sha256,
                c.text_hash = item.sha256
            WITH c, item
            MATCH (a:Article {id: item.article_id})
            MERGE (a)-[:HAS_CONDITION]->(c);
            """
            run_governed_cypher(cond_cypher, {"conditions": chunk})

    if sanctions_records:
        logger.info("--- Step 5: Materializing Sanction Nodes & HAS_SANCTION Edges ---")
        for i in range(0, len(sanctions_records), batch_size):
            chunk = sanctions_records[i : i + batch_size]
            sanc_cypher = """
            UNWIND $sanctions AS item
            MERGE (s:Sanction {id: item.id})
            SET s.type = item.type,
                s.severity = item.severity,
                s.text = item.text,
                s.sha256 = item.sha256,
                s.text_hash = item.sha256
            WITH s, item
            MATCH (a:Article {id: item.article_id})
            MERGE (a)-[:HAS_SANCTION]->(s);
            """
            run_governed_cypher(sanc_cypher, {"sanctions": chunk})

    if exceptions_records:
        logger.info("--- Step 6: Materializing Exception Nodes & HAS_EXCEPTION Edges ---")
        for i in range(0, len(exceptions_records), batch_size):
            chunk = exceptions_records[i : i + batch_size]
            exc_cypher = """
            UNWIND $exceptions AS item
            MERGE (e:Exception {id: item.id})
            SET e.type = item.type,
                e.text = item.text,
                e.sha256 = item.sha256,
                e.text_hash = item.sha256
            WITH e, item
            MATCH (a:Article {id: item.article_id})
            MERGE (a)-[:HAS_EXCEPTION]->(e);
            """
            run_governed_cypher(exc_cypher, {"exceptions": chunk})

    if concept_links_records:
        logger.info("--- Step 7: Materializing REGULATES Concept Edges ---")
        for i in range(0, len(concept_links_records), batch_size):
            chunk = concept_links_records[i : i + batch_size]
            concept_cypher = """
            UNWIND $links AS item
            MATCH (a:Article {id: item.article_id})
            MATCH (c:Concept {id: item.concept_id})
            MERGE (a)-[r:REGULATES]->(c)
            SET r.confidence = item.confidence,
                r.evidence_span = item.evidence_span,
                r.evidence_sha256 = item.evidence_sha256;
            """
            run_governed_cypher(concept_cypher, {"links": chunk})

    # ─── Inter-Law Relationships ────────────────────────────────────────────
    logger.info("--- Step 8: Establishing Inter-Law Relationships ---")
    inter_law_cypher = """
    MATCH (smuggling:Law {id: "law:anti_smuggling_goods_currency"})
    MATCH (customs:Law {id: "law:customs_affairs"})
    MERGE (smuggling)-[:REFERENCES {
        relationship_scope: "CUSTOMS_SANCTIONS_INTEGRATION",
        description: "قانون مبارزه با قاچاق کالا و ارز ناظر بر مصادیق قاچاق گمرکی در قانون امور گمرکی است."
    }]->(customs);
    """
    run_governed_cypher(inter_law_cypher)

    duration = time.time() - start_time
    logger.info("=== Successfully Materialized Anti-Smuggling & Customs Corpus in %.2fs ===", duration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Governed anti-smuggling and customs corpus ingestion"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="extract and parse the corpus without sending Cypher mutations",
    )
    args = parser.parse_args()
    req = IngestionExecutionRequest(
        source="LAWS/qachaq",
        author_id="qachaq-corpus-compiler",
        correlation_id=f"qachaq_ingest_{int(time.time())}",
        adapter_name="AntiSmugglingCorpusIngestion",
        contract_version="2.0.0",
    )
    with IngestionExecutionGate.enter(req):
        main(dry_run=args.dry_run)
