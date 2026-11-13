#!/usr/bin/env python3
"""
Ingestion Script: Monetary & Banking Laws (قوانین پولی و بانکی کشور)
==================================================================
Compiles and enriches Iranian Banking Laws into Neo4j:
1. قانون پولی و بانکی کشور (مصوب ۱۳۵۱) - 45 Articles
2. قانون بانک مرکزی جمهوری اسلامی ایران (مصوب ۱۴۰۲) - 67 Articles
3. Inter-law Semantic Linking (SUPERSEDES, CONSTITUTIONAL_BASIS, REFERENCES)
4. Semantic Layer Materialization (Conditions, Sanctions, Exceptions, REGULATES Concepts)
"""

import json
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_legal_kg import (
    LegalCorpusParser,
    HardenedKnowledgeGraphCompiler,
    CypherBridge,
    verify_source_file,
)
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
from mahoun.graph.neo4j.connection import get_connection
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
from mahoun.core.governance.ingestion_contract import sha256_text
from scripts.materialize_phase_2b_semantic_graph import to_cypher_literal, run_cypher_statement

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ingest_banking_laws")


def ingest_corpus(source_path: Path, law_id: str, law_name: str, compiler: HardenedKnowledgeGraphCompiler) -> dict:
    logger.info("==================================================")
    logger.info("📂 Processing: %s", source_path.name)
    logger.info("🏷️  Target Law ID: %s", law_id)
    logger.info("==================================================")

    # 1. Source integrity check
    valid, sha256_hash, line_count, err = verify_source_file(source_path)
    if not valid:
        raise ValueError(f"Source file verification failed for {source_path}: {err}")
    logger.info("✅ Source file verified: %d lines, SHA256: %s...", line_count, sha256_hash[:16])

    # 2. Parse corpus
    parser = LegalCorpusParser(
        source_path=source_path,
        default_law_id=law_id,
        default_law_name=law_name
    )
    laws, chapters, articles, citations, records, stats = parser.parse()

    # 3. Fail-closed invariants check
    if not stats.verify_line_accounting_invariant():
        raise RuntimeError(f"🚨 Line accounting invariant failed on {source_path.name}!")
    if stats.dlq_count > 0:
        raise RuntimeError(f"🚨 DLQ count is {stats.dlq_count} > 0 on {source_path.name}! Fail-closed.")

    logger.info("✅ Parser Stats: %d Laws, %d Chapters, %d Articles, %d Citations, DLQ: 0",
                len(laws), len(chapters), len(articles), len(citations))

    # 4. Ingest into Neo4j
    result = compiler.compile(
        laws=laws,
        chapters=chapters,
        articles=articles,
        citations=citations,
        source_hash=sha256_hash,
        source_file=str(source_path),
        batch_size=200,
        has_dlq=False
    )
    logger.info("🎉 Successfully compiled %s into Neo4j in %.2fs", law_id, result.get("elapsed_seconds", 0))
    return result


def link_banking_inter_law_relationships(bridge: CypherBridge):
    logger.info("🔗 Establishing Inter-Law Banking Relationships...")

    # 1. Law 1402 SUPERSEDES Law 1351 (نسخ صریح و تکمیلی)
    bridge.execute(
        """
        MATCH (new_law:Law {id: 'law:central_bank_1402'}), (old_law:Law {id: 'law:monetary_banking_1351'})
        MERGE (new_law)-[r:SUPERSEDES]->(old_law)
        ON CREATE SET 
            r.description = 'ماده ۶۷ قانون بانک مرکزی مصوب ۱۴۰۲ بخش‌های عمده قانون پولی و بانکی ۱۳۵۱ را صریحاً نسخ کرده است',
            r.effective_date = '1402/08/17',
            r.legislative_body = 'مجلس شورای اسلامی و مجمع تشخیص مصلحت نظام',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:SUPERSEDES] from central_bank_1402 to monetary_banking_1351")

    # 2. Central Bank Law -> Constitution (اصل ۴۳ و ۴۴)
    bridge.execute(
        """
        MATCH (cb:Law {id: 'law:central_bank_1402'}), (const:Law {id: 'law:constitution'})
        MERGE (cb)-[r:CONSTITUTIONAL_BASIS]->(const)
        ON CREATE SET 
            r.description = 'اصل ۴۳ و ۴۴ قانون اساسی مبنای حاکمیت پول ملی و انحصار نشر اسکناس',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:CONSTITUTIONAL_BASIS] from central_bank_1402 to constitution")

    # 3. Central Bank Law -> Commercial Code (اسناد تجاری، چک، برات، ورشکستگی)
    bridge.execute(
        """
        MATCH (cb:Law {id: 'law:central_bank_1402'}), (comm:Law {id: 'law:commercial_code'})
        MERGE (cb)-[r:REFERENCES]->(comm)
        ON CREATE SET 
            r.description = 'مقررات حاکم بر اسناد تجاری و نحوه تصفیه و ورشکستگی مؤسسات اعتباری تابع قانون تجارت است',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:REFERENCES] from central_bank_1402 to commercial_code")

    # 4. Central Bank Law -> Civil Procedure (صلاحیت‌ها و توقیف اموال)
    bridge.execute(
        """
        MATCH (cb:Law {id: 'law:central_bank_1402'}), (cp:Law {id: 'law:civil_procedure'})
        MERGE (cb)-[r:SUBJECT_TO_PROCEDURE]->(cp)
        ON CREATE SET 
            r.description = 'رسیدگی به دعاوی پولی و بانکی و صدور دستور موقت تابع تشریفات آیین دادرسی مدنی است',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:SUBJECT_TO_PROCEDURE] from central_bank_1402 to civil_procedure")


def enrich_banking_semantic_layer():
    logger.info("🧠 Running Semantic Decomposition & Extraction on Banking Articles...")
    extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)

    # Fetch articles of the two banking laws
    fetch_cypher = """
    MATCH (a:Article)
    WHERE a.law_id IN ['law:monetary_banking_1351', 'law:central_bank_1402']
    RETURN a.id AS id, a.law_id AS law_id, coalesce(a.normalized_text, a.raw_text, '') AS text;
    """
    articles = [
        {
            "id": record["id"],
            "law_id": record["law_id"],
            "text": record["text"],
        }
        for record in get_connection().execute_query(fetch_cypher)
    ]

    logger.info("Fetched %d banking articles for semantic decomposition.", len(articles))

    conditions_batch = []
    sanctions_batch = []
    exceptions_batch = []
    assertions_batch = []

    for art in articles:
        art_id = art["id"]
        law_id = art["law_id"]
        text = art["text"]

        if not text:
            continue

        decomp = extractor.decompose_article(art_id, law_id, text)
        for cond in decomp.conditions:
            conditions_batch.append({
                "art_id": art_id,
                "cond_id": cond.id,
                "text": cond.condition_text,
                "trigger": cond.trigger_keyword,
                "start": cond.span_start,
                "end": cond.span_end,
                "text_hash": sha256_text(cond.condition_text),
            })
        for sanc in decomp.sanctions:
            sanctions_batch.append({
                "art_id": art_id,
                "sanc_id": sanc.id,
                "text": sanc.sanction_text,
                "type": sanc.sanction_type,
                "start": sanc.span_start,
                "end": sanc.span_end,
                "text_hash": sha256_text(sanc.sanction_text),
            })
        for exc in decomp.exceptions:
            exceptions_batch.append({
                "art_id": art_id,
                "exc_id": exc.id,
                "text": exc.exception_text,
                "trigger": exc.trigger_keyword,
                "start": exc.span_start,
                "end": exc.span_end,
                "text_hash": sha256_text(exc.exception_text),
            })

        assertions = extractor.extract_concept_assertions(art_id, text)
        for assert_obj in assertions:
            assertions_batch.append({
                "art_id": assert_obj.source_entity_id,
                "concept_id": assert_obj.target_entity_id,
                "assertion_id": assert_obj.assertion_id,
                "evidence_span": assert_obj.evidence_text_span,
                "start": assert_obj.evidence_offset_start,
                "end": assert_obj.evidence_offset_end,
                "sha256": assert_obj.evidence_sha256,
                "status": assert_obj.status.value,
                "method": assert_obj.verification_method,
            })

    logger.info("Extracted %d Conditions, %d Sanctions, %d Exceptions, %d Concept REGULATES Assertions.",
                len(conditions_batch), len(sanctions_batch), len(exceptions_batch), len(assertions_batch))

    # Ingest Conditions
    CHUNK_SIZE = 300
    for i in range(0, len(conditions_batch), CHUNK_SIZE):
        chunk = conditions_batch[i:i + CHUNK_SIZE]
        cypher = f"""
        UNWIND {to_cypher_literal(chunk)} AS row
        MATCH (a:Article {{id: row.art_id}})
        MERGE (c:Condition {{id: row.cond_id}})
        SET c.article_id = row.art_id,
            c.condition_text = row.text,
            c.trigger_keyword = row.trigger,
            c.span_start = row.start,
            c.span_end = row.end,
            c.text_hash = row.text_hash
        MERGE (a)-[:HAS_CONDITION]->(c);
        """
        run_cypher_statement(cypher)

    # Ingest Sanctions
    for i in range(0, len(sanctions_batch), CHUNK_SIZE):
        chunk = sanctions_batch[i:i + CHUNK_SIZE]
        cypher = f"""
        UNWIND {to_cypher_literal(chunk)} AS row
        MATCH (a:Article {{id: row.art_id}})
        MERGE (s:Sanction {{id: row.sanc_id}})
        SET s.article_id = row.art_id,
            s.sanction_text = row.text,
            s.sanction_type = row.type,
            s.span_start = row.start,
            s.span_end = row.end,
            s.text_hash = row.text_hash
        MERGE (a)-[:HAS_SANCTION]->(s);
        """
        run_cypher_statement(cypher)

    # Ingest Exceptions
    for i in range(0, len(exceptions_batch), CHUNK_SIZE):
        chunk = exceptions_batch[i:i + CHUNK_SIZE]
        cypher = f"""
        UNWIND {to_cypher_literal(chunk)} AS row
        MATCH (a:Article {{id: row.art_id}})
        MERGE (e:Exception {{id: row.exc_id}})
        SET e.article_id = row.art_id,
            e.exception_text = row.text,
            e.trigger_keyword = row.trigger,
            e.span_start = row.start,
            e.span_end = row.end,
            e.text_hash = row.text_hash
        MERGE (a)-[:HAS_EXCEPTION]->(e);
        """
        run_cypher_statement(cypher)

    # Ingest Concept REGULATES
    for i in range(0, len(assertions_batch), CHUNK_SIZE):
        chunk = assertions_batch[i:i + CHUNK_SIZE]
        cypher = f"""
        UNWIND {to_cypher_literal(chunk)} AS row
        MATCH (a:Article {{id: row.art_id}})
        MATCH (c:Concept {{id: row.concept_id}})
        MERGE (a)-[r:REGULATES]->(c)
        SET r.assertion_id = row.assertion_id,
            r.evidence_text_span = row.evidence_span,
            r.evidence_offset_start = row.start,
            r.evidence_offset_end = row.end,
            r.evidence_sha256 = row.sha256,
            r.status = row.status,
            r.verification_method = row.method;
        """
        run_cypher_statement(cypher)

    logger.info("Semantic Layer Materialization for Banking Laws Complete!")


def print_overall_graph_state():
    logger.info("📊 LIVE GRAPH OVERALL METRICS:")
    for label, query in [
        ("Total Laws", "MATCH (l:Law) RETURN count(l) AS cnt"),
        ("Total Chapters", "MATCH (c:Chapter) RETURN count(c) AS cnt"),
        ("Total Articles", "MATCH (a:Article) RETURN count(a) AS cnt"),
        ("Total Clauses", "MATCH (cl:Clause) RETURN count(cl) AS cnt"),
        ("Total Conditions", "MATCH (c:Condition) RETURN count(c) AS cnt"),
        ("Total Sanctions", "MATCH (s:Sanction) RETURN count(s) AS cnt"),
        ("Total Exceptions", "MATCH (e:Exception) RETURN count(e) AS cnt"),
        ("Total Concepts", "MATCH (c:Concept) RETURN count(c) AS cnt"),
        ("Total Nodes", "MATCH (n) RETURN count(n) AS cnt"),
        ("Total Relationships", "MATCH ()-[r]->() RETURN count(r) AS cnt"),
        ("SUPERSEDES Rel", "MATCH ()-[r:SUPERSEDES]->() RETURN count(r) AS cnt"),
    ]:
        res = run_cypher_statement(query)
        lines = res.strip().splitlines()
        val = lines[-1].strip() if len(lines) > 1 else lines[0].strip()
        print(f"  {label:<25}: {val}")


def main():
    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "ingest_banking_laws.py",
        "POST /api/v1/ingest/canonical-batch",
    )
    IngestionExecutionGate.require_active()
    start_time = time.time()
    compiler = HardenedKnowledgeGraphCompiler(run_id=f"run_banking_{int(time.time())}")

    # 1. Ingest Law 1351
    law1_path = REPO_ROOT / "data" / "monetary_banking_1351_clean.txt"
    ingest_corpus(
        source_path=law1_path,
        law_id="law:monetary_banking_1351",
        law_name="قانون پولی و بانکی کشور (مصوب ۱۳۵۱ با اصلاحات)",
        compiler=compiler
    )

    # 2. Ingest Law 1402
    law2_path = REPO_ROOT / "data" / "central_bank_1402_clean.txt"
    ingest_corpus(
        source_path=law2_path,
        law_id="law:central_bank_1402",
        law_name="قانون بانک مرکزی جمهوری اسلامی ایران (مصوب ۱۴۰۲)",
        compiler=compiler
    )

    # 3. Inter-law links
    link_banking_inter_law_relationships(compiler.bridge)

    # 4. Enrich Semantic Layer
    enrich_banking_semantic_layer()

    # 5. Summary
    print("\n" + "=" * 60)
    print("      BANKING LAWS COMPILATION & ENRICHMENT COMPLETE")
    print("=" * 60)
    print_overall_graph_state()
    print(f"\nElapsed Time: {time.time() - start_time:.2f} seconds\n")
    print("=" * 60)


if __name__ == "__main__":
    main()
