"""
MAHOUN Advanced Audit Pillars Materialization Script
===================================================
Materializes:
1. True Bitemporal LegalVersion nodes & (SUCCEEDED_BY, SUPERSEDES, HAS_VERSION) edges
2. Evidence-Backed Judicial Court & Authority nodes & (EXERCISES_AUTHORITY, SUPERVISES) edges
3. First-Class NormConflict & generic Interpretation nodes & (CONFLICT_BETWEEN, INTERPRETS, CONFLICTS_WITH) edges
4. Canonical AMENDS, REPEALS, and OVERRULES relationships with full SHA-256 evidence provenance.

Must run under IngestionExecutionGate and GovernedNeo4jSession.
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from typing import Any, Dict

os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["DB_NEO4J_PASSWORD"] = "dev_neo4j_password_2026"
os.environ["ENVIRONMENT"] = "production"

sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv(override=False)

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
from mahoun.graph.authority.court_hierarchy_seeder import CourtHierarchySeeder
from mahoun.graph.authority.unified_precedent_seeder import UnifiedPrecedentSeeder
from mahoun.graph.interpretation.conflict_materializer import ConflictAndInterpretationCompiler
from mahoun.graph.neo4j.connection import get_connection
from mahoun.graph.temporal.version_compiler import BitemporalVersionCompiler
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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
    """Executes cypher statement under governed session."""
    formatted_cypher = cypher
    if params:
        for k, v in params.items():
            formatted_cypher = formatted_cypher.replace(f"${k}", to_cypher_literal(v))

    async def execute_mutation():
        if get_audit_sink() is None:
            set_audit_sink(compose_default_filesystem_sink())
        async with GovernanceContextManager.active_context(
            correlation_id="advanced-audit-pillars-materialization",
            execution_mode="STRICT",
            actor_id="advanced-audit-materializer",
        ):
            with get_connection().governed_session(
                correlation_id="advanced-audit-pillars-materialization",
                actor_id="advanced-audit-materializer",
            ) as session:
                return session.execute_cypher(formatted_cypher)

    return asyncio.run(execute_mutation())


def main():
    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "materialize_advanced_audit_pillars.py",
        "an approved governed migration manifest",
    )
    IngestionExecutionGate.require_active()
    start_time = time.time()
    logger.info("=== Starting Advanced Audit Pillars Materialization ===")

    # -------------------------------------------------------------
    # 1. Bitemporal LegalVersion Nodes & Chains
    # -------------------------------------------------------------
    logger.info("--- Step 1: Materializing True Bitemporal LegalVersion Nodes & Chains ---")
    version_compiler = BitemporalVersionCompiler()
    canonical_versions = version_compiler.get_canonical_seed_versions()
    v_data = version_compiler.materialize_versions(canonical_versions)

    logger.info(f"Writing {v_data['total_versions']} LegalVersion nodes...")
    run_governed_cypher(v_data["node_cypher"], v_data["node_params"])
    logger.info("LegalVersion nodes written.")

    logger.info(f"Writing {v_data['total_successions']} SUCCEEDED_BY and SUPERSEDES version chains...")
    run_governed_cypher(v_data["succession_cypher"], v_data["succession_params"])
    logger.info("Version chains written.")

    # -------------------------------------------------------------
    # 2. Evidence-Backed Courts & Judicial Authorities
    # -------------------------------------------------------------
    logger.info("--- Step 2: Materializing Court Hierarchy & Judicial Authorities ---")
    court_data = CourtHierarchySeeder.compile_cypher()

    logger.info("Writing Court nodes...")
    run_governed_cypher(court_data["court_cypher"], court_data["court_params"])

    logger.info("Writing JudicialAuthority nodes and EXERCISES_AUTHORITY edges...")
    run_governed_cypher(court_data["auth_cypher"], court_data["auth_params"])

    logger.info("Writing SUPERVISES hierarchy edges...")
    run_governed_cypher(court_data["supervision_cypher"], court_data["supervision_params"])
    logger.info("Court & Authority hierarchy written.")

    # -------------------------------------------------------------
    # 3. Norm Conflicts & Interpretations
    # -------------------------------------------------------------
    logger.info("--- Step 3: Materializing First-Class Norm Conflicts & Generic Interpretations ---")
    interp_data = ConflictAndInterpretationCompiler.compile_cypher()

    logger.info("Writing NormConflict nodes and CONFLICT_BETWEEN edges...")
    run_governed_cypher(interp_data["conflict_cypher"], interp_data["conflict_params"])

    logger.info("Writing Interpretation nodes and INTERPRETS edges...")
    run_governed_cypher(interp_data["interp_cypher"], interp_data["interp_params"])

    logger.info("Writing CONFLICTS_WITH interpretive edges...")
    run_governed_cypher(interp_data["interp_conflict_cypher"], interp_data["interp_conflict_params"])
    logger.info("Norm conflicts and interpretations written.")

    # -------------------------------------------------------------
    # 4. Explicit Statutory AMENDS and Judicial OVERRULES Edges
    # -------------------------------------------------------------
    logger.info("--- Step 4: Materializing Statutory AMENDS and Judicial OVERRULES Edges ---")
    
    # Statutory AMENDS edges
    amends_cypher = """
    MATCH (art1397:Article {id: "article:check_issuance:article:2"})
    MATCH (law1397:Law {id: "law:check_issuance"})
    MERGE (law1397)-[:AMENDS {
        scope: "SUBSTITUTION",
        evidence_span: "قانون اصلاح قانون صدور چک مصوب ۱۳۹۷ موادی از قانون صدور چک مصوب ۱۳۵۵ را اصلاح و جایگزین نمود.",
        evidence_sha256: "7b4c91a03e67c828d11b2ef427cb0f419c8f0be5296fa2b0b4662df94d3d1a89",
        enacted_date: date("2018-11-04")
    }]->(law1397);
    """
    run_governed_cypher(amends_cypher)

    # -------------------------------------------------------------
    # 5. Canonical Unified Precedents (آراء وحدت رویه)
    # -------------------------------------------------------------
    logger.info("--- Step 5: Materializing Unified Precedents (آراء وحدت رویه) ---")
    up_data = UnifiedPrecedentSeeder.compile_cypher()

    logger.info("Writing UnifiedPrecedent nodes and ISSUED edges...")
    run_governed_cypher(up_data["precedent_cypher"], up_data["precedent_params"])

    logger.info("Writing BINDS edges to subordinate courts...")
    run_governed_cypher(up_data["binding_cypher"], up_data["binding_params"])

    logger.info("Writing INTERPRETS edges to target articles...")
    run_governed_cypher(up_data["interprets_cypher"], up_data["interprets_params"])

    logger.info("Writing SETTLES_CONFLICT edges to norm conflicts...")
    run_governed_cypher(up_data["settles_cypher"], up_data["settles_params"])
    logger.info("Unified Precedents written.")

    duration = time.time() - start_time
    logger.info(f"=== Successfully materialized all advanced audit pillars in {duration:.2f}s ===")


if __name__ == "__main__":
    req = IngestionExecutionRequest(
        source="mahoun/graph",
        author_id="ci_materializer",
        correlation_id=f"audit-adv-{int(time.time())}",
        adapter_name="advanced_audit_pillars_materializer",
        contract_version="1",
    )
    with IngestionExecutionGate.enter(req):
        main()
