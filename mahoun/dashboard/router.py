# MAHOUN Dashboard Router
"""
FastAPI router for observability dashboard.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
from typing import Any, Dict

from ..config import get_observability_config
from ..metrics import get_metrics_collector
from ..tracing import get_tracer
from ..profiler import get_profiler
from ..metrics.health import get_health_system

router = APIRouter(prefix="/internal/dashboard", tags=["dashboard"])

config = get_observability_config()


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request) -> HTMLResponse:
    """Dashboard home page."""
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    
    if not template_path.exists():
        # Return simple HTML if template doesn't exist
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>MAHOUN Observability Dashboard</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-100 p-8">
            <div class="max-w-7xl mx-auto">
                <h1 class="text-3xl font-bold mb-8">MAHOUN Observability Dashboard</h1>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h2 class="text-xl font-semibold mb-4">Metrics</h2>
                        <div id="metrics"></div>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h2 class="text-xl font-semibold mb-4">Traces</h2>
                        <div id="traces"></div>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h2 class="text-xl font-semibold mb-4">Health</h2>
                        <div id="health"></div>
                    </div>
                </div>
            </div>
            <script>
                async function loadData() {
                    const [metrics, traces, health] = await Promise.all([
                        fetch('/internal/dashboard/api/metrics').then(r => r.json()),
                        fetch('/internal/dashboard/api/traces').then(r => r.json()),
                        fetch('/internal/dashboard/api/health').then(r => r.json())
                    ]);
                    document.getElementById('metrics').innerHTML = JSON.stringify(metrics, null, 2);
                    document.getElementById('traces').innerHTML = JSON.stringify(traces, null, 2);
                    document.getElementById('health').innerHTML = JSON.stringify(health, null, 2);
                }
                loadData();
                setInterval(loadData, 5000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
    
    with open(template_path) as f:
        return HTMLResponse(content=f.read())


@router.get("/api/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Get metrics data."""
    if not config.metrics_enabled:
        return {"error": "Metrics disabled"}
    
    collector = get_metrics_collector()
    return collector.get_all_metrics()


@router.get("/api/traces")
async def get_traces(limit: int = 10) -> Dict[str, Any]:
    """Get recent traces."""
    if not config.tracing_enabled:
        return {"error": "Tracing disabled"}
    
    tracer = get_tracer()
    traces = tracer.get_recent_traces(limit=limit)
    
    return {
        "traces": [trace.to_dict() for trace in traces],
        "count": len(traces)
    }


@router.get("/api/health")
async def get_health() -> Dict[str, Any]:
    """Get health status."""
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
                "details": comp.details
            }
            for name, comp in report.components.items()
        },
        "metrics_summary": report.metrics_summary
    }


@router.get("/api/profiler")
async def get_profiler_stats() -> Dict[str, Any]:
    """Get profiler statistics."""
    if not config.profiler_enabled:
        return {"error": "Profiler disabled"}
    
    profiler = get_profiler()
    stats = profiler.get_stats()
    slow_ops = profiler.get_slow_operations(limit=10)
    
    return {
        "stats": stats,
        "slow_operations": [op.to_dict() for op in slow_ops]
    }


@router.get("/api/agent-latency")
async def get_agent_latency() -> Dict[str, Any]:
    """Get agent latency leaderboard."""
    collector = get_metrics_collector()
    all_metrics = collector.get_all_metrics()
    
    # Extract agent latency metrics
    agent_metrics: Dict[str, Any] = {}
    for name, histogram in all_metrics.get("histograms", {}).items():
        if "agent" in name.lower() and "latency" in name.lower():
            agent_metrics[name] = histogram
    
    # Sort by p95 latency
    sorted_agents = sorted(
        agent_metrics.items(),
        key=lambda x: x[1].get("percentiles", {}).get("p95", 0.0),
        reverse=True
    )
    
    return {
        "agents": [
            {
                "name": name,
                "p95_latency_ms": metrics.get("percentiles", {}).get("p95", 0.0) * 1000,
                "p99_latency_ms": metrics.get("percentiles", {}).get("p99", 0.0) * 1000,
                "count": metrics.get("count", 0)
            }
            for name, metrics in sorted_agents
        ]
    }

