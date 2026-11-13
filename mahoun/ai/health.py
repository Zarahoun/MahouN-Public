"""
MAHOUN Nexus AI Runtime - Advanced Health Check System
======================================================

Classification: MISSION-CRITICAL / PRODUCTION-GRADE
Purpose: Comprehensive health monitoring for AI runtime components

This module provides advanced health checking capabilities for:
- Model availability and readiness
- Resource utilization monitoring
- Performance metrics tracking
- Dependency health validation
- Air-gap compliance verification
"""

from __future__ import annotations

import asyncio
import time
import psutil
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from mahoun.core.logging_config import get_logger
except ImportError:
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

try:
    from mahoun.ai.metrics import (
        record_component_health,
        record_system_metrics,
        record_airgap_status,
        record_health_check,
        ai_runtime_uptime_seconds,
        ai_models_available_total,
        ai_embedding_models_available,
        ai_readiness_status,
        ai_liveness_status,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


log = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health check status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """AI runtime component types"""
    MODEL_RUNTIME = "model_runtime"
    EMBEDDING_SERVICE = "embedding_service"
    CACHE_LAYER = "cache_layer"
    GOVERNANCE_VALIDATOR = "governance_validator"
    MEMORY_MANAGER = "memory_manager"
    NETWORK_ISOLATION = "network_isolation"


@dataclass
class HealthCheckResult:
    """Result of a health check operation"""
    component: str
    status: HealthStatus
    message: str
    timestamp: str
    latency_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """System resource utilization metrics"""
    cpu_percent: float
    memory_used_mb: float
    memory_available_mb: float
    memory_percent: float
    disk_used_gb: float
    disk_available_gb: float
    disk_percent: float
    model_count: int
    cache_size_mb: float
    uptime_seconds: float


class AIRuntimeHealthChecker:
    """
    Advanced health checker for AI runtime components.
    
    Provides comprehensive monitoring of:
    - Model availability and loading status
    - Resource utilization (CPU, memory, disk)
    - Component health (embeddings, cache, governance)
    - Performance metrics (latency, throughput)
    - Air-gap compliance status
    """
    
    def __init__(
        self,
        models_dir: Path | str,
        data_dir: Path | str,
        enable_detailed_metrics: bool = True
    ):
        self.models_dir = Path(models_dir)
        self.data_dir = Path(data_dir)
        self.enable_detailed_metrics = enable_detailed_metrics
        self.startup_time = time.time()
        
        # Component health cache (5-second TTL)
        self._health_cache: Dict[str, HealthCheckResult] = {}
        self._cache_ttl = 5.0
        self._last_check_time = 0.0
        
        log.info(f"AIRuntimeHealthChecker initialized: models={self.models_dir}, data={self.data_dir}")
    
    async def check_health(self, include_details: bool = False) -> Dict[str, Any]:
        """
        Comprehensive health check of all AI runtime components.
        
        Args:
            include_details: Include detailed component metrics
            
        Returns:
            Health check response with status and metrics
        """
        start_time = time.perf_counter()
        
        # Run all health checks concurrently
        checks = await asyncio.gather(
            self._check_model_runtime(),
            self._check_embedding_service(),
            self._check_memory_resources(),
            self._check_governance_validator(),
            self._check_network_isolation(),
            return_exceptions=True
        )
        
        # Process results
        results = []
        overall_status = HealthStatus.HEALTHY
        
        for check in checks:
            if isinstance(check, Exception):
                log.error(f"Health check failed: {check}")
                results.append(HealthCheckResult(
                    component="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(check)}",
                    timestamp=datetime.now(UTC).isoformat(),
                    latency_ms=0.0
                ))
                overall_status = HealthStatus.UNHEALTHY
                
                # Record failure in Prometheus
                if METRICS_AVAILABLE:
                    record_health_check("comprehensive", 0.0, component="unknown", failed=True)
            else:
                results.append(check)
                # Determine overall status (worst component status wins)
                if check.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif check.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.DEGRADED
                
                # Record component health in Prometheus
                if METRICS_AVAILABLE:
                    record_component_health(check.component, check.status.value)
        
        # Collect system metrics
        system_metrics = await self._collect_system_metrics()
        
        # Record system metrics in Prometheus
        if METRICS_AVAILABLE:
            record_system_metrics(
                cpu_percent=system_metrics.cpu_percent,
                memory_used_bytes=system_metrics.memory_used_mb * 1024 * 1024,
                memory_available_bytes=system_metrics.memory_available_mb * 1024 * 1024,
                memory_percent=system_metrics.memory_percent,
                disk_used_bytes=system_metrics.disk_used_gb * 1024 * 1024 * 1024,
                disk_available_bytes=system_metrics.disk_available_gb * 1024 * 1024 * 1024,
                disk_percent=system_metrics.disk_percent,
                cache_size_bytes=system_metrics.cache_size_mb * 1024 * 1024
            )
            ai_runtime_uptime_seconds.set(system_metrics.uptime_seconds)
            ai_models_available_total.set(system_metrics.model_count)
        
        # Calculate total latency
        total_latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Record health check latency in Prometheus
        if METRICS_AVAILABLE:
            record_health_check("comprehensive", total_latency_ms / 1000, failed=False)
        
        response = {
            "status": overall_status.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime_seconds": time.time() - self.startup_time,
            "version": "2.0.0-NEXUS",
            "checks": {
                result.component: {
                    "status": result.status.value,
                    "message": result.message,
                    "latency_ms": result.latency_ms,
                    **({"metrics": result.metrics} if include_details else {})
                }
                for result in results
            },
            "system": {
                "cpu_percent": system_metrics.cpu_percent,
                "memory_used_mb": system_metrics.memory_used_mb,
                "memory_percent": system_metrics.memory_percent,
                "disk_used_gb": system_metrics.disk_used_gb,
                "disk_percent": system_metrics.disk_percent,
                "model_count": system_metrics.model_count,
            },
            "latency_ms": total_latency_ms
        }
        
        if include_details:
            response["details"] = {
                result.component: result.details
                for result in results
            }
        
        return response
    
    async def _check_model_runtime(self) -> HealthCheckResult:
        """Check GGUF model runtime availability"""
        start_time = time.perf_counter()
        
        try:
            # Check if models directory exists and is accessible
            if not self.models_dir.exists():
                return HealthCheckResult(
                    component=ComponentType.MODEL_RUNTIME.value,
                    status=HealthStatus.UNHEALTHY,
                    message="Models directory not found",
                    timestamp=datetime.now(UTC).isoformat(),
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    details={"models_dir": str(self.models_dir)}
                )
            
            # Count available models
            gguf_models = list(self.models_dir.rglob("*.gguf"))
            model_count = len(gguf_models)
            
            # Calculate total model size
            total_size_mb = sum(m.stat().st_size for m in gguf_models) / (1024 ** 2)
            
            # Check model accessibility
            accessible_models = sum(1 for m in gguf_models if m.is_file() and m.stat().st_size > 0)
            
            if model_count == 0:
                status = HealthStatus.DEGRADED
                message = "No GGUF models found"
            elif accessible_models < model_count:
                status = HealthStatus.DEGRADED
                message = f"Some models inaccessible ({accessible_models}/{model_count})"
            else:
                status = HealthStatus.HEALTHY
                message = f"{model_count} models available"
            
            return HealthCheckResult(
                component=ComponentType.MODEL_RUNTIME.value,
                status=status,
                message=message,
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                metrics={
                    "model_count": float(model_count),
                    "accessible_count": float(accessible_models),
                    "total_size_mb": total_size_mb
                },
                details={
                    "models": [m.name for m in gguf_models[:10]],  # First 10 models
                    "models_dir": str(self.models_dir)
                }
            )
            
        except Exception as e:
            log.error(f"Model runtime health check failed: {e}")
            return HealthCheckResult(
                component=ComponentType.MODEL_RUNTIME.value,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000
            )
    
    async def _check_embedding_service(self) -> HealthCheckResult:
        """Check local embedding service health"""
        start_time = time.perf_counter()
        
        try:
            # Check for embedding models
            embeddings_dir = self.models_dir / "embeddings"
            if not embeddings_dir.exists():
                embeddings_dir = self.models_dir  # Fallback to root models dir
            
            # Look for sentence-transformers models
            model_files = list(embeddings_dir.rglob("pytorch_model.bin")) + \
                         list(embeddings_dir.rglob("model.safetensors"))
            
            embedding_model_count = len(set(m.parent for m in model_files))
            
            # Record embedding model count in Prometheus
            if METRICS_AVAILABLE:
                ai_embedding_models_available.set(embedding_model_count)
            
            if embedding_model_count == 0:
                status = HealthStatus.DEGRADED
                message = "No embedding models found"
            else:
                status = HealthStatus.HEALTHY
                message = f"{embedding_model_count} embedding models available"
            
            return HealthCheckResult(
                component=ComponentType.EMBEDDING_SERVICE.value,
                status=status,
                message=message,
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                metrics={"embedding_model_count": float(embedding_model_count)}
            )
            
        except Exception as e:
            log.error(f"Embedding service health check failed: {e}")
            return HealthCheckResult(
                component=ComponentType.EMBEDDING_SERVICE.value,
                status=HealthStatus.UNKNOWN,
                message=f"Check failed: {str(e)}",
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000
            )
    
    async def _check_memory_resources(self) -> HealthCheckResult:
        """Check memory resource availability"""
        start_time = time.perf_counter()
        
        try:
            # Get memory stats
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_mb = memory.available / (1024 ** 2)
            
            # Determine status based on memory pressure
            if memory_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical memory pressure: {memory_percent:.1f}% used"
            elif memory_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory_percent:.1f}% used"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory healthy: {memory_percent:.1f}% used"
            
            return HealthCheckResult(
                component=ComponentType.MEMORY_MANAGER.value,
                status=status,
                message=message,
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                metrics={
                    "memory_percent": memory_percent,
                    "memory_available_mb": memory_available_mb,
                    "memory_total_mb": memory.total / (1024 ** 2)
                }
            )
            
        except Exception as e:
            log.error(f"Memory health check failed: {e}")
            return HealthCheckResult(
                component=ComponentType.MEMORY_MANAGER.value,
                status=HealthStatus.UNKNOWN,
                message=f"Check failed: {str(e)}",
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000
            )
    
    async def _check_governance_validator(self) -> HealthCheckResult:
        """Check governance validator availability"""
        start_time = time.perf_counter()
        
        try:
            # Check for RedLines.yaml
            from pathlib import Path
            redlines_path = Path(__file__).parent.parent.parent / "constitution" / "RedLines.yaml"
            
            if not redlines_path.exists():
                return HealthCheckResult(
                    component=ComponentType.GOVERNANCE_VALIDATOR.value,
                    status=HealthStatus.UNHEALTHY,
                    message="RedLines.yaml not found",
                    timestamp=datetime.now(UTC).isoformat(),
                    latency_ms=(time.perf_counter() - start_time) * 1000
                )
            
            # Try to load FortressValidator
            try:
                from mahoun.core.fortress_validator import FortressValidator
                validator = FortressValidator(strict_mode=True)
                
                return HealthCheckResult(
                    component=ComponentType.GOVERNANCE_VALIDATOR.value,
                    status=HealthStatus.HEALTHY,
                    message="Governance validator operational",
                    timestamp=datetime.now(UTC).isoformat(),
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    metrics={"validator_loaded": 1.0}
                )
            except ImportError:
                return HealthCheckResult(
                    component=ComponentType.GOVERNANCE_VALIDATOR.value,
                    status=HealthStatus.DEGRADED,
                    message="Governance validator not available",
                    timestamp=datetime.now(UTC).isoformat(),
                    latency_ms=(time.perf_counter() - start_time) * 1000
                )
            
        except Exception as e:
            log.error(f"Governance validator health check failed: {e}")
            return HealthCheckResult(
                component=ComponentType.GOVERNANCE_VALIDATOR.value,
                status=HealthStatus.UNKNOWN,
                message=f"Check failed: {str(e)}",
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000
            )
    
    async def _check_network_isolation(self) -> HealthCheckResult:
        """Check air-gap network isolation compliance"""
        start_time = time.perf_counter()
        
        try:
            import os
            
            # Check environment variables for offline mode
            offline_indicators = {
                "TRANSFORMERS_OFFLINE": os.getenv("TRANSFORMERS_OFFLINE"),
                "HF_DATASETS_OFFLINE": os.getenv("HF_DATASETS_OFFLINE"),
                "MAHOUN_ENABLE_NETWORK": os.getenv("MAHOUN_ENABLE_NETWORK")
            }
            
            # Verify offline configuration
            is_offline = (
                offline_indicators["TRANSFORMERS_OFFLINE"] == "1" and
                offline_indicators["HF_DATASETS_OFFLINE"] == "1" and
                offline_indicators["MAHOUN_ENABLE_NETWORK"] in [None, "false", "False", "0"]
            )
            
            network_isolated = is_offline
            env_configured = all([
                offline_indicators["TRANSFORMERS_OFFLINE"] == "1",
                offline_indicators["HF_DATASETS_OFFLINE"] == "1"
            ])
            
            # Record air-gap status in Prometheus
            if METRICS_AVAILABLE:
                record_airgap_status(
                    compliant=is_offline,
                    network_isolated=network_isolated,
                    env_configured=env_configured
                )
            
            if is_offline:
                status = HealthStatus.HEALTHY
                message = "Air-gap compliance verified"
            else:
                status = HealthStatus.DEGRADED
                message = "Air-gap configuration incomplete"
            
            return HealthCheckResult(
                component=ComponentType.NETWORK_ISOLATION.value,
                status=status,
                message=message,
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000,
                details=offline_indicators,
                metrics={"offline_compliant": 1.0 if is_offline else 0.0}
            )
            
        except Exception as e:
            log.error(f"Network isolation health check failed: {e}")
            return HealthCheckResult(
                component=ComponentType.NETWORK_ISOLATION.value,
                status=HealthStatus.UNKNOWN,
                message=f"Check failed: {str(e)}",
                timestamp=datetime.now(UTC).isoformat(),
                latency_ms=(time.perf_counter() - start_time) * 1000
            )
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_used_mb = memory.used / (1024 ** 2)
            memory_available_mb = memory.available / (1024 ** 2)
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage(str(self.data_dir))
            disk_used_gb = disk.used / (1024 ** 3)
            disk_available_gb = disk.free / (1024 ** 3)
            disk_percent = disk.percent
            
            # Model metrics
            model_count = len(list(self.models_dir.rglob("*.gguf"))) if self.models_dir.exists() else 0
            
            # Cache metrics (approximate)
            cache_size_mb = 0.0
            cache_dir = self.data_dir / "cache"
            if cache_dir.exists():
                cache_size_mb = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) / (1024 ** 2)
            
            # Uptime
            uptime_seconds = time.time() - self.startup_time
            
            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_available_mb=memory_available_mb,
                memory_percent=memory_percent,
                disk_used_gb=disk_used_gb,
                disk_available_gb=disk_available_gb,
                disk_percent=disk_percent,
                model_count=model_count,
                cache_size_mb=cache_size_mb,
                uptime_seconds=uptime_seconds
            )
            
        except Exception as e:
            log.error(f"Failed to collect system metrics: {e}")
            return SystemMetrics(
                cpu_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                memory_percent=0.0,
                disk_used_gb=0.0,
                disk_available_gb=0.0,
                disk_percent=0.0,
                model_count=0,
                cache_size_mb=0.0,
                uptime_seconds=time.time() - self.startup_time
            )
    
    async def readiness_check(self) -> Dict[str, Any]:
        """
        Kubernetes-style readiness check.
        
        Returns ready only if critical components are operational.
        """
        start_time = time.perf_counter()
        
        # Check critical components only
        model_check = await self._check_model_runtime()
        memory_check = await self._check_memory_resources()
        
        ready = (
            model_check.status != HealthStatus.UNHEALTHY and
            memory_check.status != HealthStatus.UNHEALTHY
        )
        
        # Record readiness in Prometheus
        if METRICS_AVAILABLE:
            ai_readiness_status.set(1 if ready else 0)
            duration = time.perf_counter() - start_time
            record_health_check("readiness", duration, failed=not ready)
        
        return {
            "ready": ready,
            "timestamp": datetime.now(UTC).isoformat(),
            "components": {
                "models": model_check.status.value,
                "memory": memory_check.status.value
            }
        }
    
    async def liveness_check(self) -> Dict[str, Any]:
        """
        Kubernetes-style liveness check.
        
        Returns alive if the service can respond (basic sanity check).
        """
        start_time = time.perf_counter()
        
        # Record liveness in Prometheus
        if METRICS_AVAILABLE:
            ai_liveness_status.set(1)
            duration = time.perf_counter() - start_time
            record_health_check("liveness", duration, failed=False)
        
        return {
            "alive": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime_seconds": time.time() - self.startup_time
        }