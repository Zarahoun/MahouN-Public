#!/usr/bin/env python3
"""
MAHOUN GRAPH V2 — PHASE 5 PILOT BUILD EXECUTION
================================================

Executes the canonical governed ingestion for the 3 pilot laws:
1. anti_money_laundering_law.txt
2. check_law.txt
3. monetary_banking_1351_clean.txt

This script uses the IranianLawAdapter -> CanonicalIngestionBatch ->
GovernedIngestionRuntime.ingest_batch_atomic() path under strict
governance boundary.
"""

import asyncio
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("phase5_pilot_build")


def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def _set_neo4j_password():
    """Ensure Neo4j credentials are appropriately loaded from environment or .env."""
    import os
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass

    pwd = os.environ.get('DB_NEO4J_PASSWORD') or os.environ.get('NEO4J_PASSWORD') or 'dev_neo4j_password_2026'
    os.environ['DB_NEO4J_PASSWORD'] = pwd
    os.environ['NEO4J_PASSWORD'] = pwd


def _wire_audit_sink_once():
    """Wire the canonical FilesystemAuditSink."""
    from mahoun.core.governance.mutation_boundary import (
        get_audit_sink,
        set_audit_sink,
    )
    from mahoun.infrastructure.audit.filesink import (
        compose_default_filesystem_sink,
    )

    if get_audit_sink() is None:
        set_audit_sink(compose_default_filesystem_sink())


async def _run_pilot_build():
    """Execute governed ingestion for all 3 pilot laws."""
    from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
    from mahoun.core.governance.ingestion_execution_gate import (
        IngestionExecutionGate,
        IngestionExecutionRequest,
    )
    from mahoun.core.governance.ingestion_runtime import (
        GovernedIngestionRuntime,
        IngestionAbortedError,
    )
    from mahoun.core.governance.governance_context import (
        GovernanceContextManager,
    )
    from mahoun.graph.neo4j.connection import get_connection

    # Define pilot laws
    pilot_laws = [
        ("anti_money_laundering", "قانون مبارزه با پولشویی", REPO_ROOT / "LAWS" / "data" / "anti_money_laundering_law.txt"),
        ("check_law", "قانون صدور چک", REPO_ROOT / "LAWS" / "data" / "check_law.txt"),
        ("monetary_banking_1351", "قانون پولی و بانکی کشور", REPO_ROOT / "LAWS" / "data" / "monetary_banking_1351_clean.txt"),
    ]

    # Wire audit sink
    _wire_audit_sink_once()

    # Get connection
    connection = get_connection()

    results = []

    for law_id, law_name, law_path in pilot_laws:
        logger.info(f"=== Processing pilot law: {law_name} ({law_id}) ===")

        if not law_path.exists():
            logger.error(f"Law file not found: {law_path}")
            continue

        source_uri = str(law_path.relative_to(REPO_ROOT))
        correlation_id = f"corr_pilot_{law_id}"
        author_id = "governance_council"

        # Read law text
        text = law_path.read_text(encoding="utf-8")
        logger.info(f"Loaded {len(text)} characters from {law_path.name}")

        # Create execution request
        req = IngestionExecutionRequest(
            source=source_uri,
            author_id=author_id,
            correlation_id=correlation_id,
            adapter_name="IranianLawAdapter",
        )

        # Create adapter
        adapter = IranianLawAdapter(
            law_id=law_id,
            law_name=law_name,
            source_uri=source_uri,
            correlation_id=correlation_id,
        )

        try:
            # Build batch under gate
            with IngestionExecutionGate.enter(req):
                batch = adapter.build_batch(text)

            logger.info(f"Batch built: {len(batch.documents)} docs, {len(batch.facts)} facts, {len(batch.relationships)} rels")
            logger.info(f"Idempotency key: {batch.idempotency_key}")

            # Ingest batch under governed runtime
            with IngestionExecutionGate.enter(req):
                async with GovernanceContextManager.active_context(
                    correlation_id=correlation_id,
                    execution_mode="STRICT",
                    actor_id=author_id,
                ):
                    with connection.governed_session(
                        correlation_id=correlation_id,
                        actor_id=author_id,
                    ) as session:
                        runtime = GovernedIngestionRuntime(session=session)
                        result = runtime.ingest_batch_atomic(
                            batch,
                            author_id=author_id,
                        )

            logger.info(f"Ingestion result: {result['status']}")
            logger.info(f"Document IDs: {result.get('document_ids', [])}")
            logger.info(f"Fact count: {result.get('fact_count', 0)}")
            logger.info(f"Relationship count: {result.get('relationship_count', 0)}")
            logger.info(f"Receipts generated: {len(result.get('receipts', []))}")

            results.append({
                "law_id": law_id,
                "law_name": law_name,
                "status": result["status"],
                "document_ids": result.get("document_ids", []),
                "fact_count": result.get("fact_count", 0),
                "relationship_count": result.get("relationship_count", 0),
                "receipts_count": len(result.get("receipts", [])),
                "idempotency_key": batch.idempotency_key,
            })

        except IngestionAbortedError as exc:
            logger.error(f"Ingestion aborted for {law_id}: {exc}")
            results.append({
                "law_id": law_id,
                "law_name": law_name,
                "status": "aborted",
                "error": str(exc),
            })
        except Exception as exc:
            logger.exception(f"Unexpected error for {law_id}")
            results.append({
                "law_id": law_id,
                "law_name": law_name,
                "status": "error",
                "error": str(exc),
            })

    # Print summary
    print("\n" + "=" * 80)
    print("PHASE 5 PILOT BUILD SUMMARY")
    print("=" * 80)

    total_facts = 0
    total_rels = 0
    total_receipts = 0
    success_count = 0

    for r in results:
        print(f"\n{r['law_name']} ({r['law_id']})")
        print(f"  Status: {r['status']}")
        if r['status'] == 'success' or r['status'] == 'already_committed':
            print(f"  Facts: {r['fact_count']}")
            print(f"  Relationships: {r['relationship_count']}")
            print(f"  Receipts: {r['receipts_count']}")
            total_facts += r['fact_count']
            total_rels += r['relationship_count']
            total_receipts += r['receipts_count']
            success_count += 1
        else:
            print(f"  Error: {r.get('error', 'Unknown')}")

    print("\n" + "-" * 80)
    print(f"Total pilot laws processed: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Total facts: {total_facts}")
    print(f"Total relationships: {total_rels}")
    print(f"Total receipts: {total_receipts}")
    print("=" * 80)

    # Expected totals from manifest
    expected_facts = 593
    expected_rels = 593

    if total_facts == expected_facts and total_rels == expected_rels:
        print("\n✅ PILOT BUILD VERIFIED: Totals match expected manifest")
        return 0
    else:
        print(f"\n⚠️  PILOT BUILD DISCREPANCY: Expected {expected_facts} facts and {expected_rels} rels")
        return 1


def main():
    _configure_logging()
    _set_neo4j_password()
    return asyncio.run(_run_pilot_build())


if __name__ == "__main__":
    sys.exit(main())
