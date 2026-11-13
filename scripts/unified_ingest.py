#!/usr/bin/env python3
"""
Governed Ingestion CLI
======================

Manual operator CLI that drives the canonical governed ingestion path.

Replaces the legacy ``UnifiedLoader`` (which imported from
``mahoun.orchestrator.unified_loader`` — a module that has never existed
in this repository and which this script previously imported by
construction-broken assumption).

Canonical wiring, in order:

    1. ``set_audit_sink(...)``        — required by the governance boundary;
                                        every mutation aborts closed without it.
    2. ``GovernanceContextManager.active_context(...)`` — establishes the
                                        governance scope every
                                        ``GovernedNeo4jSession`` requires.
    3. ``connection.governed_session(...)`` — the ONLY authorized entry point
                                        for graph mutation.
    4. ``GovernedIngestionRuntime.ingest_document_atomic(...)`` — capability-
                                        scoped atomic write into the graph.

Usage:
    python scripts/unified_ingest.py --file /path/to/document.txt

Scope:
    This CLI handles text-only documents and writes only to the graph
    knowledge store. PDF/DOCX OCR, vector embedding, and graph-vector
    sync are not part of the atomic governance path; for those flows,
    use the production HTTP API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("governed_ingest_cli")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def _wire_audit_sink_once() -> None:
    """Wire the canonical FilesystemAuditSink if no sink is already wired.

    The sink is a process-global singleton (see
    ``mahoun.core.governance.mutation_boundary.set_audit_sink``); the same
    wiring used by ``api/main.py`` keeps this CLI and the API on a single
    audit substrate.
    """
    from mahoun.core.governance.mutation_boundary import (
        get_audit_sink,
        set_audit_sink,
    )
    from mahoun.infrastructure.audit.filesink import (
        compose_default_filesystem_sink,
    )

    if get_audit_sink() is None:
        set_audit_sink(compose_default_filesystem_sink())


def _read_text_file(path: Path) -> str:
    """Read a UTF-8 text file. PDFs/DOCX are out of CLI scope."""
    if path.suffix.lower() != ".txt":
        raise ValueError(
            f"CLI only supports .txt files for atomic graph ingestion; "
            f"got {path.suffix!r}. Use the HTTP API for OCR-backed flows."
        )
    return path.read_text(encoding="utf-8", errors="replace")


def _build_metadata(args: argparse.Namespace, file_path: Path) -> dict:
    metadata: dict = {"title": file_path.stem, "source": "cli_ingestion"}
    if args.meta:
        try:
            metadata.update(json.loads(args.meta))
        except json.JSONDecodeError as exc:
            raise ValueError(f"--meta must be valid JSON: {exc}") from exc
    return metadata


async def _run(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return 1

    metadata = _build_metadata(args, file_path)
    doc_id = metadata.get("id") or f"cli-{file_path.stem}"
    actor_id = "cli_operator"

    if args.mode == "server":
        from mahoun.integration import IngestionOrchestrator, ServerIngestionError

        try:
            result = IngestionOrchestrator(
                mode="server",
                server_url=args.server_url,
            ).ingest_file(
                file_path,
                title=metadata.get("title", file_path.stem),
                doc_type=metadata.get("doc_type", "law"),
                law_id=metadata.get("law_id"),
                source=metadata.get("source", str(file_path)),
                metadata=metadata,
            )
        except ServerIngestionError as exc:
            print(f"\n❌ Server ingestion failed: {exc}")
            return 2

        print("\n" + "=" * 60)
        print("📊 Server Ingestion Report")
        print("=" * 60)
        print(f"Document ID:    {result.doc_id}")
        print(f"Status:         ✅ {result.status.upper()}")
        print(f"Graph nodes:    {result.graph_nodes_created}")
        print(f"Chunks:         {result.chunks_created}")
        print(f"Embeddings:     {result.embeddings_created}")
        print("=" * 60)
        return 0

    print("\n" + "=" * 60)
    print("🛡️  Governed Ingestion CLI")
    print("=" * 60)
    print(f"File:           {file_path.name}")
    print(f"Size:           {file_path.stat().st_size / 1024:.2f} KB")
    print(f"Document ID:    {doc_id}")
    print("-" * 60)

    # Imports are deferred to inside _run so the CLI's argument parsing
    # and --help output work even when the runtime stack is unreachable.
    from mahoun.core.governance.governance_context import (
        GovernanceContextManager,
    )
    from mahoun.core.governance.ingestion_runtime import (
        GovernedIngestionRuntime,
        IngestionAbortedError,
    )
    from mahoun.core.governance.ingestion_execution_gate import (
        IngestionExecutionGate,
        IngestionExecutionRequest,
    )
    from mahoun.graph.neo4j.connection import get_connection
    from mahoun.ingestion_adapters.registry import registered_adapter_object_types

    print("🔧 Initializing governed runtime (audit sink + context + session)...")
    _wire_audit_sink_once()

    connection = get_connection()

    try:
        with IngestionExecutionGate.enter(
            IngestionExecutionRequest(
                source=str(file_path),
                author_id=actor_id,
                correlation_id=doc_id,
                adapter_name="UnifiedTextIngestionCLI",
            )
        ):
            text = _read_text_file(file_path)
            async with GovernanceContextManager.active_context(
                correlation_id=doc_id,
                execution_mode="STRICT",
                actor_id=actor_id,
            ):
                with connection.governed_session(
                    correlation_id=doc_id,
                    actor_id=actor_id,
                ) as session:
                    # The CLI is a production materialization entry point.
                    # Keep label authorization mandatory even when this
                    # text-only compatibility path emits no semantic facts.
                    runtime = GovernedIngestionRuntime(
                        session=session,
                        allowed_object_types_by_adapter=(
                            registered_adapter_object_types()
                        ),
                        enforce_label_policy=True,
                    )
                    result = runtime.ingest_document_atomic(
                        doc_id=doc_id,
                        text=text,
                        metadata=metadata,
                        author_id=actor_id,
                    )
    except IngestionAbortedError as exc:
        print(f"\n❌ Ingestion aborted (governance failure): {exc}")
        logger.exception("Ingestion aborted")
        return 2
    except Exception as exc:
        print(f"\n❌ Fatal Error: {exc}")
        logger.exception("CLI failed")
        return 1

    print("\n" + "=" * 60)
    print("📊 Ingestion Report")
    print("=" * 60)
    print(f"Document ID:    {result['doc_id']}")
    print(f"Status:         ✅ {result['status'].upper()}")
    print(f"Receipts:       {len(result['receipts'])}")
    for rid in result["receipts"]:
        print(f"  • {rid}")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Governed Document Ingestion (canonical: GovernedIngestionRuntime)"
    )
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to a UTF-8 .txt document. PDF/DOCX must use the HTTP API.",
    )
    parser.add_argument(
        "--meta",
        type=str,
        help='Optional metadata JSON, e.g. \'{"title": "Contract 42"}\'.',
    )
    parser.add_argument(
        "--mode",
        choices=("local", "server"),
        default=os.getenv("MAHOUN_INGEST_MODE", "local"),
        help="Use the local governed runtime or route through the running API server.",
    )
    parser.add_argument(
        "--server-url",
        default=os.getenv("MAHOUN_API_URL", "http://127.0.0.1:8080"),
        help="Base URL used when --mode=server.",
    )
    args = parser.parse_args()
    _configure_logging()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
