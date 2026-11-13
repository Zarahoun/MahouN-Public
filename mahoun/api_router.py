# MAHOUN Observability API Router
"""
FastAPI router for observability endpoints.
"""

from fastapi import APIRouter, Response
from typing import Any, Dict

from .metrics import get_metrics_collector
from .metrics.health import get_health_system
from .config import get_observability_config

router = APIRouter(prefix="/internal", tags=["observability"])

config = get_observability_config()


@router.get("/health")
async def internal_health() -> Dict[str, Any]:
    """
    Internal health endpoint.

    Returns:
        Comprehensive health report including:
        - uptime
        - CPU/RAM usage
        - vector & graph engine status
        - last agent failures
        - pending tasks count
    """
    health_system = get_health_system()
    report = await health_system.check_health()

    return {
        "overall_healthy": report.overall_healthy,
        "uptime_seconds": report.uptime_seconds,
        "cpu_percent": report.cpu_percent,
        "memory_bytes": report.memory_bytes,
        "components": {
            name: {
                "healthy": comp.healthy,
                "message": comp.message,
                "details": comp.details,
                "last_check": comp.last_check,
            }
            for name, comp in report.components.items()
        },
        "last_agent_failures": health_system.get_last_failures(limit=5),
        "pending_tasks_count": health_system.get_pending_tasks_count(),
        "metrics_summary": report.metrics_summary,
        "timestamp": report.timestamp,
    }


@router.get("/metrics")
async def get_metrics() -> Response:
    """
    Get all metrics in Prometheus format.
    Includes both core system metrics and legal-aware telemetry.

    Returns:
        Prometheus-formatted metrics text
    """
    if not config.metrics_enabled:
        return Response(content="# Metrics disabled", media_type="text/plain")

    collector = get_metrics_collector()
    # The collector will now output both System & Legal metrics (from legal_monitor)
    return Response(
        content=collector.to_prometheus(), media_type="text/plain; version=0.0.4"
    )


@router.get("/metrics/json")
async def get_metrics_json() -> Dict[str, Any]:
    """
    Get all metrics as JSON.

    Returns:
        Metrics as dictionary
    """
    if not config.metrics_enabled:
        return {"error": "Metrics disabled"}

    collector = get_metrics_collector()
    return collector.get_all_metrics()
