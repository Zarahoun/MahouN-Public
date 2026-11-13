"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   MAHOUN AI RUNTIME - PROMETHEUS METRICS                     ║
║                                                                              ║
║  Classification: NEXUS-CLASS OBSERVABILITY / PRODUCTION-GRADE                ║
║  Purpose: Comprehensive Prometheus metrics for AI runtime monitoring        ║
║                                                                              ║
║  Features:                                                                   ║
║  ✓ Model availability and performance tracking                              ║
║  ✓ Resource utilization monitoring (CPU, memory, disk)                      ║
║  ✓ Component health status gauges                                           ║
║  ✓ Inference latency and throughput metrics                                 ║
║  ✓ Air-gap compliance verification                                          ║
║  ✓ Governance validation metrics                                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info
from typing import Optional


# ============================================================================
# INFO METRICS - Static Information
# ============================================================================

ai_runtime_info = Info(
    "mahoun_ai_runtime_info",
    "AI Runtime version and configuration information"
)

# ============================================================================
# HEALTH STATUS METRICS
# ============================================================================

ai_component_health_status = Gauge(
    "mahoun_ai_component_health_status",
    "Health status of AI runtime components (0=unknown, 1=healthy, 2=degraded, 3=unhealthy)",
    ["component"]
)

ai_runtime_up = Gauge(
    "mahoun_ai_runtime_up",
    "AI runtime service availability (1=up, 0=down)"
)

ai_runtime_uptime_seconds = Gauge(
    "mahoun_ai_runtime_uptime_seconds",
    "AI runtime uptime in seconds"
)

# ============================================================================
# MODEL METRICS
# ============================================================================

ai_models_available_total = Gauge(
    "mahoun_ai_models_available_total",
    "Total number of available GGUF models"
)

ai_models_loaded_total = Gauge(
    "mahoun_ai_models_loaded_total",
    "Number of currently loaded models in memory"
)

ai_model_size_bytes = Gauge(
    "mahoun_ai_model_size_bytes",
    "Size of loaded model in bytes",
    ["model_name"]
)

ai_model_load_time_seconds = Histogram(
    "mahoun_ai_model_load_time_seconds",
    "Time taken to load a model",
    ["model_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

ai_model_load_failures_total = Counter(
    "mahoun_ai_model_load_failures_total",
    "Total number of model loading failures",
    ["model_name", "reason"]
)

# ============================================================================
# INFERENCE METRICS
# ============================================================================

ai_inference_requests_total = Counter(
    "mahoun_ai_inference_requests_total",
    "Total number of AI inference requests",
    ["model_name", "status"]
)

ai_inference_duration_seconds = Histogram(
    "mahoun_ai_inference_duration_seconds",
    "Time taken for AI inference",
    ["model_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

ai_inference_tokens_generated_total = Counter(
    "mahoun_ai_inference_tokens_generated_total",
    "Total number of tokens generated",
    ["model_name"]
)

ai_inference_prompt_tokens_total = Counter(
    "mahoun_ai_inference_prompt_tokens_total",
    "Total number of prompt tokens processed",
    ["model_name"]
)

ai_inference_tokens_per_second = Gauge(
    "mahoun_ai_inference_tokens_per_second",
    "Current tokens per second throughput",
    ["model_name"]
)

# ============================================================================
# EMBEDDING SERVICE METRICS
# ============================================================================

ai_embedding_requests_total = Counter(
    "mahoun_ai_embedding_requests_total",
    "Total number of embedding generation requests",
    ["model_name", "status"]
)

ai_embedding_duration_seconds = Histogram(
    "mahoun_ai_embedding_duration_seconds",
    "Time taken to generate embeddings",
    ["model_name"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

ai_embedding_models_available = Gauge(
    "mahoun_ai_embedding_models_available",
    "Number of available embedding models"
)

ai_embedding_cache_hits_total = Counter(
    "mahoun_ai_embedding_cache_hits_total",
    "Total number of embedding cache hits"
)

ai_embedding_cache_misses_total = Counter(
    "mahoun_ai_embedding_cache_misses_total",
    "Total number of embedding cache misses"
)

# ============================================================================
# RESOURCE UTILIZATION METRICS
# ============================================================================

ai_runtime_memory_usage_bytes = Gauge(
    "mahoun_ai_runtime_memory_usage_bytes",
    "Current memory usage in bytes"
)

ai_runtime_memory_available_bytes = Gauge(
    "mahoun_ai_runtime_memory_available_bytes",
    "Available memory in bytes"
)

ai_runtime_memory_percent = Gauge(
    "mahoun_ai_runtime_memory_percent",
    "Memory usage percentage"
)

ai_runtime_cpu_usage_percent = Gauge(
    "mahoun_ai_runtime_cpu_usage_percent",
    "CPU usage percentage"
)

ai_runtime_disk_usage_bytes = Gauge(
    "mahoun_ai_runtime_disk_usage_bytes",
    "Disk usage in bytes for AI runtime data"
)

ai_runtime_disk_available_bytes = Gauge(
    "mahoun_ai_runtime_disk_available_bytes",
    "Available disk space in bytes"
)

ai_runtime_disk_percent = Gauge(
    "mahoun_ai_runtime_disk_percent",
    "Disk usage percentage"
)

ai_runtime_cache_size_bytes = Gauge(
    "mahoun_ai_runtime_cache_size_bytes",
    "Size of runtime cache in bytes"
)

# ============================================================================
# GOVERNANCE & COMPLIANCE METRICS
# ============================================================================

ai_governance_validations_total = Counter(
    "mahoun_ai_governance_validations_total",
    "Total number of governance validations performed",
    ["result"]  # pass, fail, error
)

ai_governance_validation_duration_seconds = Histogram(
    "mahoun_ai_governance_validation_duration_seconds",
    "Time taken for governance validation",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

ai_governance_violations_total = Counter(
    "mahoun_ai_governance_violations_total",
    "Total number of governance violations detected",
    ["violation_type", "severity"]
)

ai_governance_fortress_validator_up = Gauge(
    "mahoun_ai_governance_fortress_validator_up",
    "FortressValidator availability (1=up, 0=down)"
)

# ============================================================================
# AIR-GAP COMPLIANCE METRICS
# ============================================================================

ai_airgap_compliance_status = Gauge(
    "mahoun_ai_airgap_compliance_status",
    "Air-gap compliance status (1=compliant, 0=non-compliant)"
)

ai_airgap_network_isolation_status = Gauge(
    "mahoun_ai_airgap_network_isolation_status",
    "Network isolation status (1=isolated, 0=not-isolated)"
)

ai_airgap_offline_env_configured = Gauge(
    "mahoun_ai_airgap_offline_env_configured",
    "Offline environment variables configured correctly (1=yes, 0=no)"
)

ai_airgap_network_call_attempts_total = Counter(
    "mahoun_ai_airgap_network_call_attempts_total",
    "Total number of blocked network call attempts",
    ["component", "destination"]
)

# ============================================================================
# HEALTH CHECK METRICS
# ============================================================================

ai_health_check_duration_seconds = Histogram(
    "mahoun_ai_health_check_duration_seconds",
    "Time taken for health check execution",
    ["check_type"],  # comprehensive, readiness, liveness
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

ai_health_check_failures_total = Counter(
    "mahoun_ai_health_check_failures_total",
    "Total number of health check failures",
    ["component"]
)

ai_readiness_status = Gauge(
    "mahoun_ai_readiness_status",
    "Kubernetes readiness status (1=ready, 0=not-ready)"
)

ai_liveness_status = Gauge(
    "mahoun_ai_liveness_status",
    "Kubernetes liveness status (1=alive, 0=dead)"
)

# ============================================================================
# HELPER FUNCTIONS - Simplified Metric Recording
# ============================================================================

def record_component_health(component: str, status: str) -> None:
    """
    Record component health status.
    
    Args:
        component: Component name (model_runtime, embedding_service, etc.)
        status: Health status (healthy, degraded, unhealthy, unknown)
    """
    status_map = {
        "unknown": 0,
        "healthy": 1,
        "degraded": 2,
        "unhealthy": 3
    }
    ai_component_health_status.labels(component=component).set(
        status_map.get(status.lower(), 0)
    )


def record_model_load(model_name: str, duration: float, success: bool, reason: Optional[str] = None) -> None:
    """Record model loading metrics."""
    ai_model_load_time_seconds.labels(model_name=model_name).observe(duration)
    if not success:
        ai_model_load_failures_total.labels(
            model_name=model_name,
            reason=reason or "unknown"
        ).inc()


def record_inference(model_name: str, duration: float, tokens_generated: int, 
                     prompt_tokens: int, success: bool = True) -> None:
    """Record inference metrics."""
    status = "success" if success else "failure"
    ai_inference_requests_total.labels(model_name=model_name, status=status).inc()
    ai_inference_duration_seconds.labels(model_name=model_name).observe(duration)
    
    if success:
        ai_inference_tokens_generated_total.labels(model_name=model_name).inc(tokens_generated)
        ai_inference_prompt_tokens_total.labels(model_name=model_name).inc(prompt_tokens)
        
        # Calculate and record tokens per second
        if duration > 0:
            tps = tokens_generated / duration
            ai_inference_tokens_per_second.labels(model_name=model_name).set(tps)


def record_embedding_request(model_name: str, duration: float, success: bool = True,
                             cache_hit: bool = False) -> None:
    """Record embedding generation metrics."""
    status = "success" if success else "failure"
    ai_embedding_requests_total.labels(model_name=model_name, status=status).inc()
    ai_embedding_duration_seconds.labels(model_name=model_name).observe(duration)
    
    if cache_hit:
        ai_embedding_cache_hits_total.inc()
    else:
        ai_embedding_cache_misses_total.inc()


def record_governance_validation(result: str, duration: float, 
                                 violation_type: Optional[str] = None,
                                 severity: Optional[str] = None) -> None:
    """Record governance validation metrics."""
    ai_governance_validations_total.labels(result=result).inc()
    ai_governance_validation_duration_seconds.observe(duration)
    
    if result == "fail" and violation_type:
        ai_governance_violations_total.labels(
            violation_type=violation_type,
            severity=severity or "unknown"
        ).inc()


def record_system_metrics(cpu_percent: float, memory_used_bytes: float,
                          memory_available_bytes: float, memory_percent: float,
                          disk_used_bytes: float, disk_available_bytes: float,
                          disk_percent: float, cache_size_bytes: float) -> None:
    """Record system resource metrics."""
    ai_runtime_cpu_usage_percent.set(cpu_percent)
    ai_runtime_memory_usage_bytes.set(memory_used_bytes)
    ai_runtime_memory_available_bytes.set(memory_available_bytes)
    ai_runtime_memory_percent.set(memory_percent)
    ai_runtime_disk_usage_bytes.set(disk_used_bytes)
    ai_runtime_disk_available_bytes.set(disk_available_bytes)
    ai_runtime_disk_percent.set(disk_percent)
    ai_runtime_cache_size_bytes.set(cache_size_bytes)


def record_airgap_status(compliant: bool, network_isolated: bool, env_configured: bool) -> None:
    """Record air-gap compliance status."""
    ai_airgap_compliance_status.set(1 if compliant else 0)
    ai_airgap_network_isolation_status.set(1 if network_isolated else 0)
    ai_airgap_offline_env_configured.set(1 if env_configured else 0)


def record_health_check(check_type: str, duration: float, component: Optional[str] = None,
                        failed: bool = False) -> None:
    """Record health check metrics."""
    ai_health_check_duration_seconds.labels(check_type=check_type).observe(duration)
    if failed and component:
        ai_health_check_failures_total.labels(component=component).inc()


def initialize_ai_runtime_metrics(version: str = "2.0.0-NEXUS", 
                                  deployment_profile: str = "DESKTOP_MINIMAL") -> None:
    """
    Initialize AI runtime metrics with static information.
    
    Args:
        version: AI runtime version
        deployment_profile: Deployment profile (DESKTOP_MINIMAL or ENTERPRISE_FULL)
    """
    ai_runtime_info.info({
        "version": version,
        "deployment_profile": deployment_profile,
        "component": "ai_runtime"
    })
    
    # Set initial service status
    ai_runtime_up.set(1)
    ai_liveness_status.set(1)
    
    # Initialize FortressValidator status
    try:
        from mahoun.core.fortress_validator import FortressValidator
        ai_governance_fortress_validator_up.set(1)
    except ImportError:
        ai_governance_fortress_validator_up.set(0)


__all__ = [
    # Info metrics
    "ai_runtime_info",
    
    # Health status
    "ai_component_health_status",
    "ai_runtime_up",
    "ai_runtime_uptime_seconds",
    
    # Model metrics
    "ai_models_available_total",
    "ai_models_loaded_total",
    "ai_model_size_bytes",
    "ai_model_load_time_seconds",
    "ai_model_load_failures_total",
    
    # Inference metrics
    "ai_inference_requests_total",
    "ai_inference_duration_seconds",
    "ai_inference_tokens_generated_total",
    "ai_inference_prompt_tokens_total",
    "ai_inference_tokens_per_second",
    
    # Embedding metrics
    "ai_embedding_requests_total",
    "ai_embedding_duration_seconds",
    "ai_embedding_models_available",
    "ai_embedding_cache_hits_total",
    "ai_embedding_cache_misses_total",
    
    # Resource metrics
    "ai_runtime_memory_usage_bytes",
    "ai_runtime_memory_available_bytes",
    "ai_runtime_memory_percent",
    "ai_runtime_cpu_usage_percent",
    "ai_runtime_disk_usage_bytes",
    "ai_runtime_disk_available_bytes",
    "ai_runtime_disk_percent",
    "ai_runtime_cache_size_bytes",
    
    # Governance metrics
    "ai_governance_validations_total",
    "ai_governance_validation_duration_seconds",
    "ai_governance_violations_total",
    "ai_governance_fortress_validator_up",
    
    # Air-gap metrics
    "ai_airgap_compliance_status",
    "ai_airgap_network_isolation_status",
    "ai_airgap_offline_env_configured",
    "ai_airgap_network_call_attempts_total",
    
    # Health check metrics
    "ai_health_check_duration_seconds",
    "ai_health_check_failures_total",
    "ai_readiness_status",
    "ai_liveness_status",
    
    # Helper functions
    "record_component_health",
    "record_model_load",
    "record_inference",
    "record_embedding_request",
    "record_governance_validation",
    "record_system_metrics",
    "record_airgap_status",
    "record_health_check",
    "initialize_ai_runtime_metrics",
]
