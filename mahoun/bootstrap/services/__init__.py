"""
Bootstrap Services Package

Extracted services from monolithic executors for:
- Testability: Each service can be tested in isolation
- Reusability: Services can be used across different executors
- Maintainability: Smaller, focused classes easier to understand

Services:
- IntegrityVerifier: SHA256 verification
- ResourceProfiler: Hardware assessment
- ModelResolver: Profile-based model selection
- ModelLoader: Load with retry + circuit breaker
- ModelHealthChecker: Health monitoring with baseline comparison
- BenchmarkService: Performance profiling
- RollbackManager: Transaction cleanup
"""

from mahoun.bootstrap.services.integrity_verifier import IntegrityVerifier
from mahoun.bootstrap.services.resource_profiler import ResourceProfiler
from mahoun.bootstrap.services.model_resolver import ModelResolver
from mahoun.bootstrap.services.model_loader import (
    ModelLoader,
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerConfig,
    RetryConfig,
    LoadResult
)
from mahoun.bootstrap.services.model_health_checker import (
    ModelHealthChecker,
    HealthStatus,
    HealthCheckConfig,
    HealthCheckResult,
    InferenceMetrics
)
from mahoun.bootstrap.services.benchmark_service import (
    BenchmarkService,
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkMetrics,
    BenchmarkMetric
)
from mahoun.bootstrap.services.rollback_manager import (
    RollbackManager,
    RollbackStatus,
    RollbackResult,
    ResourceType,
    ResourceHandle,
    Checkpoint,
    cleanup_model,
    cleanup_file,
    cleanup_directory,
    cleanup_connection
)
from mahoun.bootstrap.services.service_container import (
    ServiceContainer,
    ServiceConfig,
    ServiceRegistry,
    create_service_container
)

__all__ = [
    # IntegrityVerifier
    "IntegrityVerifier",
    
    # ResourceProfiler
    "ResourceProfiler",
    
    # ModelResolver
    "ModelResolver",
    
    # ModelLoader
    "ModelLoader",
    "CircuitBreaker",
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "RetryConfig",
    "LoadResult",
    
    # ModelHealthChecker
    "ModelHealthChecker",
    "HealthStatus",
    "HealthCheckConfig",
    "HealthCheckResult",
    "InferenceMetrics",
    
    # BenchmarkService
    "BenchmarkService",
    "BenchmarkConfig",
    "BenchmarkResult",
    "BenchmarkMetrics",
    "BenchmarkMetric",
    
    # RollbackManager
    "RollbackManager",
    "RollbackStatus",
    "RollbackResult",
    "ResourceType",
    "ResourceHandle",
    "Checkpoint",
    "cleanup_model",
    "cleanup_file",
    "cleanup_directory",
    "cleanup_connection",
    
    # ServiceContainer
    "ServiceContainer",
    "ServiceConfig",
    "ServiceRegistry",
    "create_service_container",
]
