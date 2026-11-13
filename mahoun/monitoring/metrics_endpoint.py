"""
Prometheus Metrics Endpoint
===========================
FastAPI endpoint for exposing legal monitoring metrics to Prometheus.

This module provides HTTP endpoints for Prometheus to scrape metrics
from the legal-aware monitoring system.

Usage:
    from mahoun.monitoring.metrics_endpoint import metrics_router

    # Add to FastAPI app
    app.include_router(metrics_router)

    # Health check at: GET /health/legal-monitoring
    # Legal Stats at: GET /stats/legal-monitoring
"""

import logging
from fastapi import APIRouter, Response
from typing import Dict, Any

from mahoun.monitoring.legal_metrics import legal_monitoring

logger = logging.getLogger(__name__)

# Create router
metrics_router = APIRouter(prefix="", tags=["monitoring"])


@metrics_router.get("/metrics", deprecated=True)
async def prometheus_metrics():
    """
    [DEPRECATED] Prometheus metrics endpoint
    This endpoint is deprecated. Use the unified /internal/metrics from api_router.py instead.
    """
    return Response(
        content="# This endpoint is deprecated. Use /internal/metrics instead.\n",
        media_type="text/plain",
        status_code=301,
    )


@metrics_router.get("/health/legal-monitoring")
async def legal_monitoring_health() -> Dict[str, Any]:
    """
    Legal monitoring health check endpoint

    Returns comprehensive health status of the legal monitoring system.

    Returns:
        Health status dictionary
    """
    try:
        health_status = await legal_monitoring.health_check()
        return health_status
    except Exception as e:
        logger.error(f"Error checking legal monitoring health: {e}")
        return {"status": "unhealthy", "error": str(e)}


@metrics_router.get("/stats/legal-monitoring")
async def legal_monitoring_stats() -> Dict[str, Any]:
    """
    Legal monitoring statistics endpoint

    Returns comprehensive statistics from the legal monitoring system.

    Returns:
        Statistics dictionary
    """
    try:
        stats = legal_monitoring.get_comprehensive_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting legal monitoring stats: {e}")
        return {"error": str(e)}


@metrics_router.post("/monitoring/reset")
async def reset_legal_monitoring() -> Dict[str, str]:
    """
    Reset legal monitoring metrics

    WARNING: This will clear all collected metrics. Use with caution.

    Returns:
        Success message
    """
    try:
        legal_monitoring.reset()
        return {
            "status": "success",
            "message": "Legal monitoring metrics reset successfully",
        }
    except Exception as e:
        logger.error(f"Error resetting legal monitoring: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# Integration Helper
# ============================================================================


def register_metrics_endpoint(app):
    """
    Register metrics endpoint with FastAPI app

    Args:
        app: FastAPI application instance
    """
    app.include_router(metrics_router)
    logger.info("Legal monitoring metrics endpoint registered at /metrics")
