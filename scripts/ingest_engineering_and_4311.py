#!/usr/bin/env python3
"""
Ingestion Script: Engineering System Law & Nashrieh 4311 (شرایط عمومی پیمان)
===========================================================================
Compiles cleaned Iranian Engineering System Law & General Conditions of Contract
into Neo4j with Line Accounting Invariant checks and Inter-Law Relationship Linking.
"""

import sys
import time
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_legal_kg import (
    LegalCorpusParser,
    HardenedKnowledgeGraphCompiler,
    CypherBridge,
    verify_source_file,
    PARSER_VERSION,
    SCHEMA_VERSION
)
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ingest_engineering_and_4311")


def ingest_corpus(source_path: Path, law_id: str, law_name: str, compiler: HardenedKnowledgeGraphCompiler) -> dict:
    logger.info(f"==================================================")
    logger.info(f"📂 Processing: {source_path.name}")
    logger.info(f"🏷️  Target Law ID: {law_id}")
    logger.info(f"==================================================")

    # 1. Source integrity check
    valid, sha256_hash, line_count, err = verify_source_file(source_path)
    if not valid:
        raise ValueError(f"Source file verification failed for {source_path}: {err}")
    logger.info(f"✅ Source file verified: {line_count} lines, SHA256: {sha256_hash[:16]}...")

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

    logger.info(f"✅ Parser Stats: {len(laws)} Laws, {len(chapters)} Chapters, {len(articles)} Articles, {len(citations)} Citations, DLQ: 0")

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
    logger.info(f"🎉 Successfully compiled {law_id} into Neo4j in {result.get('elapsed_seconds', 0):.2f}s")
    return result


def link_inter_law_relationships(bridge: CypherBridge):
    logger.info("🔗 Establishing Inter-Law Domain Relationships...")

    # 1. Engineering System -> Conditions of Contract 4311
    # Law of Engineering System mandates technical and engineering standards in construction contracts
    bridge.execute(
        """
        MATCH (eng:Law {id: 'law:engineering_system'}), (pact:Law {id: 'law:conditions_of_contract_4311'})
        MERGE (eng)-[r:MANDATES_COMPLIANCE]->(pact)
        ON CREATE SET 
            r.description = 'قانون نظام مهندسی استانداردهای فنی و نظارتی حاکم بر اجرای پیمان را تعیین می‌کند',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:MANDATES_COMPLIANCE] from engineering_system to conditions_of_contract_4311")

    # 2. Conditions of Contract 4311 -> Civil Procedure Code
    # Article 53 (Dispute Resolution) & Article 30 (Delays/Damages) are subject to arbitration & civil procedure rules
    bridge.execute(
        """
        MATCH (pact:Law {id: 'law:conditions_of_contract_4311'}), (cp:Law {id: 'law:civil_procedure'})
        MERGE (pact)-[r:SUBJECT_TO_PROCEDURE]->(cp)
        ON CREATE SET 
            r.description = 'حل اختلاف موضوع ماده ۵۳ و خسارات ماده ۵۰ تابع قانون آیین دادرسی مدنی است',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:SUBJECT_TO_PROCEDURE] from conditions_of_contract_4311 to civil_procedure")

    # 3. Conditions of Contract 4311 -> Constitution
    bridge.execute(
        """
        MATCH (pact:Law {id: 'law:conditions_of_contract_4311'}), (const:Law {id: 'law:constitution'})
        MERGE (pact)-[r:CONSTITUTIONAL_BASIS]->(const)
        ON CREATE SET 
            r.description = 'اصل ۴۴ و ۴۶ قانون اساسی مبنای قراردادهای عمومی و خصوصی عمرانی',
            r.created_at = datetime();
        """
    )
    logger.info("  -> Created [:CONSTITUTIONAL_BASIS] from conditions_of_contract_4311 to constitution")


def print_graph_summary(bridge: CypherBridge):
    logger.info("==================================================")
    logger.info("📊 CURRENT KNOWLEDGE GRAPH SUMMARY IN NEO4J")
    logger.info("==================================================")
    out = bridge.execute(
        """
        MATCH (l:Law)
        OPTIONAL MATCH (l)<-[:BELONGS_TO]-(a:Article)
        OPTIONAL MATCH (l)-[:CONTAINS]->(c:Chapter)
        RETURN l.id as law_id, l.name as law_name, count(DISTINCT c) as chapters_count, count(DISTINCT a) as articles_count
        ORDER BY articles_count DESC;
        """
    )
    print(out)


def main():
    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "ingest_engineering_and_4311.py",
        "POST /api/v1/ingest/canonical-batch",
    )
    IngestionExecutionGate.require_active()
    start_all = time.time()
    compiler = HardenedKnowledgeGraphCompiler(run_id=f"run_eng_4311_{int(time.time())}")
    
    # 1. Ingest Nezam Mohandesi
    nezam_path = REPO_ROOT / "data" / "nezam_mohandesi_clean.txt"
    ingest_corpus(
        source_path=nezam_path,
        law_id="law:engineering_system",
        law_name="قانون نظام مهندسی و کنترل ساختمان (مصوب ۱۳۷۴ با اصلاحات)",
        compiler=compiler
    )

    # 2. Ingest Nashrieh 4311
    nashrieh_path = REPO_ROOT / "data" / "nashrieh_4311_clean.txt"
    ingest_corpus(
        source_path=nashrieh_path,
        law_id="law:conditions_of_contract_4311",
        law_name="شرایط عمومی پیمان (نشریه ۴۳۱۱ سازمان مدیریت و برنامه‌ریزی کشور)",
        compiler=compiler
    )

    # 3. Inter-law links
    link_inter_law_relationships(compiler.bridge)

    # 4. Summary
    print_graph_summary(compiler.bridge)
    logger.info(f"✨ Ingestion complete in {time.time() - start_all:.2f}s!")


if __name__ == "__main__":
    main()
