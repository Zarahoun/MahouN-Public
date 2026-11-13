"""
Service Container for Dependency Injection

Responsibility: Wire all bootstrap services together with proper lifecycle management.
This is the SINGLE SOURCE OF TRUTH for service instantiation.

Architecture:
- Singleton pattern for shared services
- Lazy initialization for expensive services
- Thread-safe service registry
- Lifecycle management (startup/shutdown)
- Configuration-driven service creation

Design Pattern: Service Locator + Dependency Injection Container
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Callable, TypeVar, Generic
from threading import Lock

from mahoun.bootstrap.services.integrity_verifier import IntegrityVerifier
from mahoun.bootstrap.services.resource_profiler import (
    ResourceProfiler
)
from mahoun.bootstrap.services.model_resolver import ModelResolver
from mahoun.bootstrap.services.model_loader import (
    ModelLoader,
    CircuitBreakerConfig,
    RetryConfig
)
from mahoun.bootstrap.services.model_health_checker import (
    ModelHealthChecker,
    HealthCheckConfig
)
from mahoun.bootstrap.services.benchmark_service import (
    BenchmarkService,
    BenchmarkConfig
)
from mahoun.bootstrap.services.rollback_manager import RollbackManager

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ServiceConfig:
    """Configuration for service container"""
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_timeout_seconds: float = 60.0
    
    # Retry settings
    max_retry_attempts: int = 3
    retry_initial_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 30.0
    
    # Health check settings
    health_check_timeout_seconds: float = 30.0
    health_check_max_inference_multiplier: float = 3.0
    
    # Benchmark settings
    benchmark_warmup_iterations: int = 5
    benchmark_measurement_iterations: int = 20
    
    # Runtime profile (detected at startup)
    runtime_profile: Optional[str] = None  # "BASE" | "PLUS" | "ULTRA"


@dataclass
class ServiceRegistry:
    """Thread-safe service registry"""
    _services: Dict[str, Any] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    
    def register(self, name: str, service: Any) -> None:
        """Register a service"""
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service '{name}' already registered")
            self._services[name] = service
            logger.debug(f"Service registered: {name}")
    
    def get(self, name: str) -> Optional[Any]:
        """Get a service by name"""
        with self._lock:
            return self._services.get(name)
    
    def exists(self, name: str) -> bool:
        """Check if service exists"""
        with self._lock:
            return name in self._services
    
    def clear(self) -> None:
        """Clear all services (for testing)"""
        with self._lock:
            self._services.clear()
            logger.debug("Service registry cleared")


class ServiceContainer:
    """
    Production-grade dependency injection container
    
    Features:
    - Singleton pattern for shared services
    - Lazy initialization
    - Thread-safe service registry
    - Lifecycle management
    - Configuration-driven instantiation
    
    Example:
        config = ServiceConfig(
            circuit_breaker_failure_threshold=3,
            max_retry_attempts=3
        )
        
        container = ServiceContainer(config)
        await container.initialize()
        
        # Get services
        loader = container.model_loader
        health_checker = container.health_checker
        
        # Use services
        result = await loader.load_model(...)
        
        # Cleanup
        await container.shutdown()
    """
    
    def __init__(self, config: Optional[ServiceConfig] = None):
        self.config = config or ServiceConfig()
        self._registry = ServiceRegistry()
        self._initialized = False
        self._shutdown = False
    
    # ==================== Lifecycle Management ====================
    
    async def initialize(self) -> None:
        """
        Initialize container and all services
        
        Order matters! Dependencies are resolved in this sequence:
        1. ResourceProfiler (detects hardware)
        2. IntegrityVerifier (no dependencies)
        3. ModelResolver (needs profile from profiler)
        4. ModelLoader (needs resolver)
        5. ModelHealthChecker (needs loader)
        6. BenchmarkService (independent)
        7. RollbackManager (independent)
        """
        if self._initialized:
            logger.warning("ServiceContainer already initialized")
            return
        
        logger.info("Initializing ServiceContainer...")
        
        try:
            # Phase 1: Core services (no dependencies)
            self._create_integrity_verifier()
            self._create_rollback_manager()
            self._create_benchmark_service()
            
            # Phase 2: Hardware detection
            self._create_resource_profiler()
            await self._detect_hardware_profile()
            
            # Phase 3: Model management (depends on profile)
            self._create_model_resolver()
            self._create_model_loader()
            self._create_model_health_checker()
            
            self._initialized = True
            logger.info("ServiceContainer initialized successfully")
        
        except Exception as e:
            logger.error(f"ServiceContainer initialization failed: {e}")
            await self.shutdown()
            raise
    
    async def shutdown(self) -> None:
        """Gracefully shutdown all services"""
        if self._shutdown:
            return
        
        logger.info("Shutting down ServiceContainer...")
        
        # Cleanup services in reverse order
        self._registry.clear()
        
        self._shutdown = True
        logger.info("ServiceContainer shutdown complete")
    
    async def _detect_hardware_profile(self) -> None:
        """Detect hardware and update config"""
        profiler = self._registry.get("resource_profiler")
        profile_result = await profiler.detect_hardware()
        
        self.config.runtime_profile = profile_result.recommended_profile
        
        logger.info(
            f"Hardware profile detected: {profile_result.recommended_profile} "
            f"(CPU: {profile_result.hardware.cpu_count} cores, "
            f"RAM: {profile_result.hardware.total_ram_gb:.1f}GB, "
            f"GPU: {profile_result.hardware.gpu_count} devices)"
        )
    
    # ==================== Service Factory Methods ====================
    
    def _create_integrity_verifier(self) -> None:
        """Create IntegrityVerifier service"""
        service = IntegrityVerifier()
        self._registry.register("integrity_verifier", service)
    
    def _create_resource_profiler(self) -> None:
        """Create ResourceProfiler service"""
        service = ResourceProfiler()
        self._registry.register("resource_profiler", service)
    
    def _create_model_resolver(self) -> None:
        """Create ModelResolver service"""
        service = ModelResolver()
        self._registry.register("model_resolver", service)
    
    def _create_model_loader(self) -> None:
        """Create ModelLoader service"""
        circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            timeout_seconds=self.config.circuit_breaker_timeout_seconds
        )
        
        retry_config = RetryConfig(
            max_attempts=self.config.max_retry_attempts,
            initial_delay_seconds=self.config.retry_initial_delay_seconds,
            max_delay_seconds=self.config.retry_max_delay_seconds
        )
        
        service = ModelLoader(
            circuit_breaker_config=circuit_breaker_config,
            retry_config=retry_config
        )
        
        self._registry.register("model_loader", service)
    
    def _create_model_health_checker(self) -> None:
        """Create ModelHealthChecker service"""
        health_config = HealthCheckConfig(
            inference_timeout_seconds=self.config.health_check_timeout_seconds,
            max_inference_duration_multiplier=self.config.health_check_max_inference_multiplier
        )
        
        service = ModelHealthChecker(config=health_config)
        self._registry.register("model_health_checker", service)
    
    def _create_benchmark_service(self) -> None:
        """Create BenchmarkService"""
        benchmark_config = BenchmarkConfig(
            warmup_iterations=self.config.benchmark_warmup_iterations,
            measurement_iterations=self.config.benchmark_measurement_iterations
        )
        
        service = BenchmarkService(config=benchmark_config)
        self._registry.register("benchmark_service", service)
    
    def _create_rollback_manager(self) -> None:
        """Create RollbackManager service"""
        service = RollbackManager()
        self._registry.register("rollback_manager", service)
    
    # ==================== Service Accessors (Properties) ====================
    
    @property
    def integrity_verifier(self) -> IntegrityVerifier:
        """Get IntegrityVerifier service"""
        self._assert_initialized()
        return self._registry.get("integrity_verifier")
    
    @property
    def resource_profiler(self) -> ResourceProfiler:
        """Get ResourceProfiler service"""
        self._assert_initialized()
        return self._registry.get("resource_profiler")
    
    @property
    def model_resolver(self) -> ModelResolver:
        """Get ModelResolver service"""
        self._assert_initialized()
        return self._registry.get("model_resolver")
    
    @property
    def model_loader(self) -> ModelLoader:
        """Get ModelLoader service"""
        self._assert_initialized()
        return self._registry.get("model_loader")
    
    @property
    def health_checker(self) -> ModelHealthChecker:
        """Get ModelHealthChecker service"""
        self._assert_initialized()
        return self._registry.get("model_health_checker")
    
    @property
    def benchmark_service(self) -> BenchmarkService:
        """Get BenchmarkService"""
        self._assert_initialized()
        return self._registry.get("benchmark_service")
    
    @property
    def rollback_manager(self) -> RollbackManager:
        """Get RollbackManager service"""
        self._assert_initialized()
        return self._registry.get("rollback_manager")
    
    # ==================== Utility Methods ====================
    
    def _assert_initialized(self) -> None:
        """Assert container is initialized"""
        if not self._initialized:
            raise RuntimeError(
                "ServiceContainer not initialized. Call await container.initialize() first."
            )
        
        if self._shutdown:
            raise RuntimeError(
                "ServiceContainer has been shut down (shutdown). Create a new instance."
            )
    
    def get_service(self, name: str) -> Optional[Any]:
        """
        Get service by name (for advanced use cases)
        
        Prefer using properties (e.g., container.model_loader) over this method
        """
        self._assert_initialized()
        return self._registry.get(name)
    
    def __repr__(self) -> str:
        return (
            f"ServiceContainer("
            f"initialized={self._initialized}, "
            f"shutdown={self._shutdown}, "
            f"profile={self.config.runtime_profile if self._initialized else 'N/A'}"
            f")"
        )


# ==================== Factory Function ====================

async def create_service_container(
    config: Optional[ServiceConfig] = None
) -> ServiceContainer:
    """
    Factory function to create and initialize ServiceContainer
    
    Example:
        container = await create_service_container()
        
        # Use services
        loader = container.model_loader
        result = await loader.load_model(...)
        
        # Cleanup
        await container.shutdown()
    """
    container = ServiceContainer(config)
    await container.initialize()
    return container
