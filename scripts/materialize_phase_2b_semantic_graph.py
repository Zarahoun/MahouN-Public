"""
Materialize Phase 2B Semantic Layer in Neo4j
=============================================
Enriches the MahouN Legal Knowledge Graph with:
1. Canonical Legal Concepts (:Concept) and hierarchy (:INHERITS_FROM)
2. Article logical decomposition (:Condition, :Sanction, :Exception)
3. Logical relationships (:HAS_CONDITION, :HAS_SANCTION, :HAS_EXCEPTION)
4. Taxonomic semantic assertions (Article -[:REGULATES]-> Concept)
"""

import json
import logging
import os
import sys
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv()

from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
from mahoun.graph.neo4j.connection import get_connection
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionGate,
    IngestionExecutionRequest,
)
from mahoun.core.governance.mutation_boundary import (
    classify_cypher,
    get_audit_sink,
    set_audit_sink,
)
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
from mahoun.core.governance.ingestion_contract import sha256_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def to_cypher_literal(obj) -> str:
    """Recursively converts Python objects into valid Cypher map / list literal syntax."""
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


def run_cypher_statement(cypher: str) -> str:
    """Execute a read or governed mutation through the canonical connection."""
    if classify_cypher(cypher):
        async def execute_mutation():
            if get_audit_sink() is None:
                set_audit_sink(compose_default_filesystem_sink())
            async with GovernanceContextManager.active_context(
                correlation_id="phase-2b-semantic-materialization",
                execution_mode="STRICT",
                actor_id="phase-2b-materializer",
            ):
                with get_connection().governed_session(
                    correlation_id="phase-2b-semantic-materialization",
                    actor_id="phase-2b-materializer",
                ) as session:
                    return session.execute_cypher(cypher)
        records = asyncio.run(execute_mutation())
    else:
        records = get_connection().execute_query(cypher)
    return "\n".join(str(dict(record)) for record in records)


def main():
    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "materialize_phase_2b_semantic_graph.py",
        "an approved governed migration manifest",
    )
    IngestionExecutionGate.require_active()
    start_time = time.time()
    logger.info("Starting Phase 2B Semantic Layer Materialization...")

    extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)

    # 1. Materialize Canonical Concepts and Hierarchy
    logger.info("--- Step 1: Materializing Concepts Taxonomy ---")
    concepts_list = []
    hierarchy_list = []

    for concept_id, concept in CANONICAL_LEGAL_CONCEPTS.items():
        concepts_list.append({
            "id": concept.canonical_id,
            "label_fa": concept.canonical_label_fa,
            "label_en": concept.canonical_label_en,
            "norm_label": concept.normalized_label,
            "domain": concept.domain,
            "jurisdiction": concept.jurisdiction,
            "onto_ver": concept.ontology_version,
            "schema_ver": concept.semantic_schema_version,
            "desc_fa": concept.description_fa or "",
            "aliases_fa": concept.aliases_fa,
            "aliases_en": concept.aliases_en,
            "source_hash": sha256_text(
                json.dumps(
                    {
                        "id": concept.canonical_id,
                        "label_fa": concept.canonical_label_fa,
                        "label_en": concept.canonical_label_en,
                        "description_fa": concept.description_fa or "",
                        "ontology_version": concept.ontology_version,
                        "semantic_schema_version": concept.semantic_schema_version,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            ),
        })
        if concept.parent_concept_id:
            hierarchy_list.append({
                "child_id": concept.canonical_id,
                "parent_id": concept.parent_concept_id,
            })

    concept_cypher = f"""
    UNWIND {to_cypher_literal(concepts_list)} AS c
    MERGE (node:Concept {{id: c.id}})
    SET node.canonical_label_fa = c.label_fa,
        node.canonical_label_en = c.label_en,
        node.normalized_label = c.norm_label,
        node.domain = c.domain,
        node.jurisdiction = c.jurisdiction,
        node.ontology_version = c.onto_ver,
        node.semantic_schema_version = c.schema_ver,
        node.description_fa = c.desc_fa,
        node.aliases_fa = c.aliases_fa,
        node.aliases_en = c.aliases_en,
        node.source_hash = c.source_hash;
    """
    run_cypher_statement(concept_cypher)

    hierarchy_cypher = f"""
    UNWIND {to_cypher_literal(hierarchy_list)} AS h
    MATCH (child:Concept {{id: h.child_id}})
    MATCH (parent:Concept {{id: h.parent_id}})
    MERGE (child)-[:INHERITS_FROM]->(parent);
    """
    run_cypher_statement(hierarchy_cypher)
    logger.info("Concepts and Hierarchy successfully materialized.")

    # 2. Fetch all Articles from Neo4j
    logger.info("--- Step 2: Fetching All Articles from Neo4j ---")
    fetch_cypher = """
    MATCH (a:Article)
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

    logger.info("Fetched %d articles for semantic decomposition.", len(articles))

    # 3. Process Articles in batches
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

    logger.info("Extracted %d Conditions, %d Sanctions, %d Exceptions, %d REGULATES Assertions.",
                len(conditions_batch), len(sanctions_batch), len(exceptions_batch), len(assertions_batch))

    # 4. Ingest Conditions in Chunks
    logger.info("--- Step 3: Materializing Conditions into Neo4j ---")
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
        logger.info("  Conditions progress: %d/%d", min(i + CHUNK_SIZE, len(conditions_batch)), len(conditions_batch))

    # 5. Ingest Sanctions in Chunks
    logger.info("--- Step 4: Materializing Sanctions into Neo4j ---")
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
        logger.info("  Sanctions progress: %d/%d", min(i + CHUNK_SIZE, len(sanctions_batch)), len(sanctions_batch))

    # 6. Ingest Exceptions in Chunks
    logger.info("--- Step 5: Materializing Exceptions into Neo4j ---")
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
        logger.info("  Exceptions progress: %d/%d", min(i + CHUNK_SIZE, len(exceptions_batch)), len(exceptions_batch))

    # 7. Ingest Concept REGULATES Assertions in Chunks
    logger.info("--- Step 6: Materializing REGULATES Assertions into Neo4j ---")
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
        logger.info("  REGULATES progress: %d/%d", min(i + CHUNK_SIZE, len(assertions_batch)), len(assertions_batch))

    # 8. Verification Queries
    logger.info("--- Step 7: Verifying Live Graph State ---")
    verification_metrics = {}
    for label, query in [
        ("Total Nodes", "MATCH (n) RETURN count(n) AS cnt"),
        ("Total Relationships", "MATCH ()-[r]->() RETURN count(r) AS cnt"),
        ("Concept Nodes", "MATCH (c:Concept) RETURN count(c) AS cnt"),
        ("Condition Nodes", "MATCH (c:Condition) RETURN count(c) AS cnt"),
        ("Sanction Nodes", "MATCH (s:Sanction) RETURN count(s) AS cnt"),
        ("Exception Nodes", "MATCH (e:Exception) RETURN count(e) AS cnt"),
        ("REGULATES Rel", "MATCH ()-[r:REGULATES]->() RETURN count(r) AS cnt"),
        ("HAS_CONDITION Rel", "MATCH ()-[r:HAS_CONDITION]->() RETURN count(r) AS cnt"),
        ("HAS_SANCTION Rel", "MATCH ()-[r:HAS_SANCTION]->() RETURN count(r) AS cnt"),
        ("HAS_EXCEPTION Rel", "MATCH ()-[r:HAS_EXCEPTION]->() RETURN count(r) AS cnt"),
        ("INHERITS_FROM Rel", "MATCH ()-[r:INHERITS_FROM]->() RETURN count(r) AS cnt"),
    ]:
        res = run_cypher_statement(query)
        lines = res.strip().splitlines()
        val = lines[-1].strip() if len(lines) > 1 else lines[0].strip()
        verification_metrics[label] = val

    print("\n" + "=" * 65)
    print("           LIVE NEO4J VERIFICATION RESULTS")
    print("=" * 65)
    for k, v in verification_metrics.items():
        print(f"  {k:<28}: {v}")
    print(f"\n  Elapsed Time                : {time.time() - start_time:.2f} seconds")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    request = IngestionExecutionRequest(
        source="scripts/materialize_phase_2b_semantic_graph.py",
        author_id="phase-2b-materializer",
        correlation_id=f"phase_2b_{int(time.time())}",
        adapter_name="SemanticGraphMaterializer",
        contract_version="1.0.0",
    )
    with IngestionExecutionGate.enter(request):
        main()
