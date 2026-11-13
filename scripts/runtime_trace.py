#!/usr/bin/env python3
"""
Runtime trace for constitutional stabilization.

Proves the live execution path reaches real runtime components rather than only
importing modules:

API -> Kernel -> Retrieval -> Graph -> Reasoning -> Audit
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TraceStep:
    name: str
    status: str
    details: dict[str, Any]


def _route_snapshot(app) -> dict[str, Any]:
    routes = {getattr(route, "path", None) for route in app.routes}
    required = {
        "search": "/v1/search/verdicts",
        "reasoning_generate": "/api/v1/reasoning/generate-verdict",
        "reasoning_verify": "/api/v1/reasoning/verify-verdict",
        "reasoning_ledger": "/api/v1/reasoning/query-ledger",
        "policy_current": "/api/v1/policy/current",
        "policy_list": "/api/v1/policy/list",
        "health": "/health",
    }
    return {
        "route_count": len(routes),
        "required_routes": required,
        "missing_routes": {
            name: path for name, path in required.items() if path not in routes
        },
    }


async def build_trace() -> list[TraceStep]:
    steps: list[TraceStep] = []

    try:
        from api.main import app
        from api.routers.system import collect_system_health
        from mahoun.core.governance.governance_context import GovernanceContextManager
        from mahoun.core.governance import KernelMutationBoundary
        from mahoun.ledger.blockchain import ImmutableLedger
        from mahoun.reasoning.reasoning_chain import ReasoningChain
        from mahoun.graph.graph_query_service import GraphQueryService
        from services.search.legal_search_service import LegalSearchService
    except Exception as exc:
        for name in ["api", "kernel", "retrieval", "graph", "reasoning", "audit", "system_health"]:
            steps.append(
                TraceStep(
                    name=name,
                    status="failed",
                    details={"import_error": repr(exc)},
                )
            )
        return steps

    api_details = _route_snapshot(app)
    api_status = "ok" if not api_details["missing_routes"] else "failed"
    steps.append(TraceStep(name="api", status=api_status, details=api_details))

    async with GovernanceContextManager.active_context(
        correlation_id="runtime-trace",
        actor_id="constitutional-stabilization",
    ) as ctx:
        query_type = KernelMutationBoundary.classify_query("MATCH (n) RETURN n LIMIT 1")
        kernel_details = {
            "context_id": ctx.context_id,
            "correlation_id": ctx.correlation_id,
            "actor_id": ctx.actor_id,
            "query_type": getattr(query_type, "value", str(query_type)),
        }
    steps.append(TraceStep(name="kernel", status="ok", details=kernel_details))

    retrieval_service = LegalSearchService()
    try:
        await retrieval_service._ensure_initialized()
        vector_manager = await retrieval_service._get_vector_manager()
        graph_ops = await retrieval_service._get_graph_ops()
        retrieval_status = "ok"
        retrieval_details = {
            "initialized": True,
            "vector_store_ready": vector_manager is not None,
            "graph_service_ready": graph_ops is not None,
            "stats": retrieval_service.get_stats(),
        }
    except Exception as exc:
        retrieval_status = "failed"
        retrieval_details = {"initialized": False, "error": repr(exc)}
    steps.append(TraceStep(name="retrieval", status=retrieval_status, details=retrieval_details))

    try:
        graph_service = GraphQueryService()
        graph_health = graph_service.health_check()
        graph_status = "ok" if graph_health.get("status") == "healthy" else "degraded"
        steps.append(TraceStep(name="graph", status=graph_status, details=graph_health))
    except Exception as exc:
        steps.append(
            TraceStep(
                name="graph",
                status="failed",
                details={"error": repr(exc)},
            )
        )

    try:
        chain = ReasoningChain()
        await chain.initialize()
        reasoning_details = {
            "initialized": True,
            "nli_available": chain.nli_available,
            "citation_available": chain.citation_available,
            "uncertainty_available": chain.uncertainty_available,
        }
        reasoning_status = (
            "ok"
            if any(
                [
                    chain.nli_available,
                    chain.citation_available,
                    chain.uncertainty_available,
                ]
            )
            else "degraded"
        )
    except Exception as exc:
        reasoning_status = "failed"
        reasoning_details = {"initialized": False, "error": repr(exc)}
    steps.append(TraceStep(name="reasoning", status=reasoning_status, details=reasoning_details))

    try:
        ledger_path = os.getenv("MAHOUN_LEDGER_PATH", "./data/ledger.json")
        ledger = ImmutableLedger(storage_path=ledger_path)
        ledger_dir = Path(ledger_path).parent
        ledger_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=ledger_dir, prefix=".runtime_trace_", delete=True) as handle:
            handle.write(b"probe")
            handle.flush()
        audit_details = {
            "ledger_path": ledger_path,
            "chain_length": len(ledger.chain),
            "integrity": ledger.verify_integrity(),
        }
        audit_status = "ok" if audit_details["integrity"] else "failed"
    except Exception as exc:
        audit_status = "failed"
        audit_details = {"error": repr(exc)}
    steps.append(TraceStep(name="audit", status=audit_status, details=audit_details))

    system_health = await collect_system_health()
    overall_status = system_health.get("status", "unknown")
    steps.append(
        TraceStep(
            name="system_health",
            status=overall_status,
            details=system_health,
        )
    )

    return steps


async def _main(json_output: bool) -> int:
    with contextlib.redirect_stdout(sys.stderr):
        steps = await build_trace()
    payload = {"steps": [asdict(step) for step in steps]}

    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for step in payload["steps"]:
            print(f"[{step['status']}] {step['name']}")
            print(json.dumps(step["details"], ensure_ascii=False, indent=2))

    failed = [step for step in steps if step.status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trace the live constitutional runtime path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(json_output=args.json)))
