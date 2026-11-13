#!/usr/bin/env python3
"""
MAHOUN GRAPH V2 — Dual-Label Alignment Migration
=================================================
Classification: MIGRATION / GOVERNANCE / ONTOLOGY ALIGNMENT
Governed under MAHOUN V2 Constitutional Authority.

Resolves FND-L1-003:
Synchronizes storage labels (:Document, :LawArticle, :LawChapter, :LawClause)
with canonical domain labels (:Law, :Article, :Chapter, :Clause)
via non-destructive dual-labeling under GovernedNeo4jSession.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.mutation_boundary import get_audit_sink, set_audit_sink
from mahoun.core.governance.system_identities import SCHEMA_MIGRATION_ACTOR
from mahoun.graph.neo4j.connection import get_connection
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_dual_entity_labels")


def _wire_audit_sink_once():
    if get_audit_sink() is None:
        set_audit_sink(compose_default_filesystem_sink())


async def migrate_dual_labels() -> bool:
    """Execute dual-label alignment migration under GovernedNeo4jSession."""
    _wire_audit_sink_once()
    conn = get_connection()
    correlation_id = "migration_dual_label_alignment_v2_1"
    actor_id = SCHEMA_MIGRATION_ACTOR.id

    logger.info("🛡️ Initiating governed dual-label migration...")
    async with GovernanceContextManager.active_context(
        correlation_id=correlation_id,
        execution_mode="STRICT",
        actor_id=actor_id,
    ):
        with conn.governed_session(
            correlation_id=correlation_id,
            actor_id=actor_id,
        ) as session:
            # 1. Document -> Law
            res_doc = session.execute_cypher("MATCH (d:Document) WHERE NOT d:Law SET d:Law RETURN count(d) as c")
            doc_updated = res_doc[0]["c"] if res_doc else 0
            logger.info(f"✅ Document -> Law alignment: {doc_updated} nodes updated")

            # 2. LawArticle -> Article
            res_art = session.execute_cypher("MATCH (a:LawArticle) WHERE NOT a:Article SET a:Article RETURN count(a) as c")
            art_updated = res_art[0]["c"] if res_art else 0
            logger.info(f"✅ LawArticle -> Article alignment: {art_updated} nodes updated")

            # 3. LawChapter -> Chapter
            res_ch = session.execute_cypher("MATCH (c:LawChapter) WHERE NOT c:Chapter SET c:Chapter RETURN count(c) as c")
            ch_updated = res_ch[0]["c"] if res_ch else 0
            logger.info(f"✅ LawChapter -> Chapter alignment: {ch_updated} nodes updated")

            # 4. LawClause -> Clause
            res_cl = session.execute_cypher("MATCH (cl:LawClause) WHERE NOT cl:Clause SET cl:Clause RETURN count(cl) as c")
            cl_updated = res_cl[0]["c"] if res_cl else 0
            logger.info(f"✅ LawClause -> Clause alignment: {cl_updated} nodes updated")

    # Read-only verification
    logger.info("🔍 Verifying dual-label parity in live Neo4j...")
    art_count = conn.execute_query("MATCH (a:Article) RETURN count(a) as c")[0]["c"]
    law_art_count = conn.execute_query("MATCH (a:LawArticle) RETURN count(a) as c")[0]["c"]
    law_count = conn.execute_query("MATCH (l:Law) RETURN count(l) as c")[0]["c"]
    doc_count = conn.execute_query("MATCH (d:Document) RETURN count(d) as c")[0]["c"]
    ch_count = conn.execute_query("MATCH (c:Chapter) RETURN count(c) as c")[0]["c"]
    law_ch_count = conn.execute_query("MATCH (c:LawChapter) RETURN count(c) as c")[0]["c"]
    cl_count = conn.execute_query("MATCH (cl:Clause) RETURN count(cl) as c")[0]["c"]
    law_cl_count = conn.execute_query("MATCH (cl:LawClause) RETURN count(cl) as c")[0]["c"]

    logger.info(f"📊 Parity Check:")
    logger.info(f"   Article: {art_count} == LawArticle: {law_art_count}")
    logger.info(f"   Law: {law_count} == Document: {doc_count}")
    logger.info(f"   Chapter: {ch_count} == LawChapter: {law_ch_count}")
    logger.info(f"   Clause: {cl_count} == LawClause: {law_cl_count}")

    assert art_count == law_art_count and art_count > 0, "Article / LawArticle parity check failed"
    assert law_count == doc_count and law_count > 0, "Law / Document parity check failed"
    assert ch_count == law_ch_count and ch_count > 0, "Chapter / LawChapter parity check failed"
    assert cl_count == law_cl_count and cl_count > 0, "Clause / LawClause parity check failed"

    logger.info("🎉 Dual-label migration completed and verified successfully!")
    return True


if __name__ == "__main__":
    success = asyncio.run(migrate_dual_labels())
    sys.exit(0 if success else 1)

