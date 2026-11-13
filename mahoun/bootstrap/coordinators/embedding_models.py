"""
EmbeddingModelsCoordinator - Thin Orchestration Layer

Responsibility: Coordinate embedding model loading using injected services.
This coordinator contains ZERO business logic — only orchestration!

Architecture:
- All business logic delegated to services
- Services injected via ServiceContainer
- Coordinator = thin orchestration glue
- Total lines: ~200 (vs 1592 in old executor)

Services Used:
- IntegrityVerifier: Verify model checksums
- ResourceProfiler: Detect hardware capabilities
- ModelResolver: Select appropriate model for profile
- ModelLoader: Load model with retry + circuit breaker
- ModelHealthChecker: Verify model health after load
- BenchmarkService: Profile model performance
- RollbackManager: Cleanup on failure
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from mahoun.bootstrap.manager import (
    BootstrapPhaseExecutor,
    BootstrapContext,
    PhaseResult,
    BootstrapException,
)
from mahoun.bootstrap.services import (
    ServiceContainer,
    IntegrityVerifier,
    ResourceProfiler,
    ModelResolver,
    ModelLoader,
    ModelHealthChecker,
    BenchmarkService,
    RollbackManager,
    ResourceType,
    HealthStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingLoadResult:
    """Result of embedding model load operation"""
    success: bool
    model: Optional[Any]
    model_name: str
    profile: str
    load_duration_seconds: float
    health_status: Optional[HealthStatus]
    benchmark_latency_ms: Optional[float]
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmbeddingModelsCoordinator(BootstrapPhaseExecutor):
    """
    Thin coordinator for embedding model loading
    
    This is a PURE ORCHESTRATOR — all business logic is in services!
    
    Workflow:
    1. Create rollback checkpoint
    2. Detect hardware profile
    3. Resolve model spec for profile
    4. Verify model integrity
    5. Load model with retry
    6. Health check loaded model
    7. Benchmark performance
    8. Register in context
    9. Rollback on any failure
    
    Example:
        container = await create_service_container()
        
        coordinator = EmbeddingModelsCoordinator(container)
        result = await coordinator.execute(context)
        
        if result.success:
            print(f"Embedding model loaded: {result.data['model_name']}")
    """
    
    def __init__(self, service_container: ServiceContainer):
        """
        Initialize coordinator with service container
        
        Args:
            service_container: DI container with all services
        """
        self.container = service_container
        self._phase_name = "embedding_models"
    
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        """
        Execute embedding model loading orchestration
        
        This method is PURE ORCHESTRATION — delegates everything to services!
        
        Args:
            context: Bootstrap context
        
        Returns:
            PhaseResult with success status and loaded model info
        """
        start_time = datetime.utcnow()
        checkpoint_id = f"embedding_load_{int(start_time.timestamp())}"
        
        logger.info("Starting embedding model loading orchestration")
        
        try:
            # Step 1: Create rollback checkpoint
            checkpoint = self.container.rollback_manager.create_checkpoint(
                checkpoint_id=checkpoint_id,
                metadata={"phase": "embedding_models", "profile": context.runtime_profile}
            )
            
            # Step 2: Detect hardware profile (already done by container, but verify)
            profile = context.runtime_profile
            logger.info(f"Using runtime profile: {profile}")
            
            # Step 3: Resolve model spec for profile
            model_spec = self.container.model_resolver.resolve_embedding_model(
                profile=profile
            )
            logger.info(
                f"Resolved embedding model: {model_spec.model_name} "
                f"(size: {model_spec.size_mb}MB, "
                f"requires: {model_spec.min_ram_gb}GB RAM)"
            )
            
            # Step 4: Verify model integrity (if checksum provided)
            if model_spec.checksum_sha256:
                integrity_result = await self.container.integrity_verifier.verify_model(
                    model_name=model_spec.model_name,
                    expected_checksum=model_spec.checksum_sha256,
                    model_path=model_spec.model_path
                )
                
                if not integrity_result.is_valid:
                    raise BootstrapException(
                        f"Integrity check failed for {model_spec.model_name}: "
                        f"{integrity_result.error_message}"
                    )
                
                logger.info(f"Integrity verified: {model_spec.model_name}")
            
            # Step 5: Load model with retry + circuit breaker
            load_result = await self.container.model_loader.load_model(
                model_name=model_spec.model_name,
                loader_func=self._create_embedding_loader(model_spec),
                metadata={
                    "profile": profile,
                    "size_mb": model_spec.size_mb,
                    "phase": "embedding_models"
                }
            )
            
            if not load_result.success:
                raise BootstrapException(
                    f"Failed to load embedding model after {load_result.attempts} attempts: "
                    f"{load_result.error}"
                )
            
            model = load_result.model
            logger.info(
                f"Model loaded successfully: {model_spec.model_name} "
                f"(duration: {load_result.duration_seconds:.2f}s, "
                f"attempts: {load_result.attempts})"
            )
            
            # Step 6: Register cleanup handler
            self.container.rollback_manager.register_resource(
                checkpoint_id=checkpoint_id,
                resource_type=ResourceType.MODEL,
                identifier=model_spec.model_name,
                cleanup_func=lambda: self._cleanup_model(model),
                metadata={"model_type": "embedding"}
            )
            
            # Step 7: Health check
            health_result = await self.container.health_checker.check_health(
                model_name=model_spec.model_name,
                model=model,
                inference_func=lambda m: self._test_inference(m),
                baseline_duration_seconds=model_spec.baseline_latency_ms / 1000 if model_spec.baseline_latency_ms else None
            )
            
            if health_result.status == HealthStatus.UNHEALTHY:
                logger.error(
                    f"Health check failed: {health_result.errors}"
                )
                await self.container.rollback_manager.rollback(checkpoint_id)
                raise BootstrapException(
                    f"Model health check failed: {health_result.errors}"
                )
            
            if health_result.status == HealthStatus.DEGRADED:
                logger.warning(
                    f"Model is degraded: {health_result.warnings}"
                )
            
            logger.info(
                f"Health check passed: {health_result.status.value} "
                f"(latency: {health_result.inference_metrics.duration_seconds:.3f}s)"
            )
            
            # Step 8: Benchmark performance (optional, skip if slow)
            benchmark_result = None
            if context.config.get("enable_benchmarking", True):
                try:
                    benchmark_result = await asyncio.wait_for(
                        self.container.benchmark_service.benchmark_model(
                            model_name=model_spec.model_name,
                            model=model,
                            inference_func=lambda m: self._test_inference(m),
                            sample_input="test legal document text",
                            metadata={"profile": profile}
                        ),
                        timeout=60.0  # 1 minute max
                    )
                    
                    logger.info(
                        f"Benchmark complete: "
                        f"latency={benchmark_result.latency_ms.mean:.2f}ms "
                        f"(p95={benchmark_result.latency_ms.p95:.2f}ms), "
                        f"throughput={benchmark_result.throughput_per_sec:.1f}/sec"
                    )
                except asyncio.TimeoutError:
                    logger.warning("Benchmark timeout, skipping")
            
            # Step 9: Register in context
            context.shared_state["embedding_model"] = model
            context.shared_state["embedding_model_name"] = model_spec.model_name
            context.shared_state["embedding_model_profile"] = profile
            
            # Step 10: Remove checkpoint (no rollback needed)
            self.container.rollback_manager.remove_checkpoint(checkpoint_id)
            
            # Success!
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=True,
                phase_name=self._phase_name,
                duration_seconds=duration,
                data={
                    "model_name": model_spec.model_name,
                    "profile": profile,
                    "health_status": health_result.status.value,
                    "load_duration": load_result.duration_seconds,
                    "benchmark_latency_ms": benchmark_result.latency_ms.mean if benchmark_result else None,
                    "benchmark_p95_ms": benchmark_result.latency_ms.p95 if benchmark_result else None,
                    "throughput_per_sec": benchmark_result.throughput_per_sec if benchmark_result else None,
                },
                metadata={
                    "model_size_mb": model_spec.size_mb,
                    "load_attempts": load_result.attempts,
                    "circuit_breaker_state": load_result.circuit_breaker_state.value,
                }
            )
        
        except Exception as e:
            logger.error(f"Embedding model loading failed: {e}", exc_info=True)
            
            # Rollback on failure
            try:
                rollback_result = await self.container.rollback_manager.rollback(
                    checkpoint_id=checkpoint_id,
                    ignore_errors=True
                )
                logger.info(
                    f"Rollback complete: {rollback_result.resources_cleaned} resources cleaned"
                )
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=False,
                phase_name=self._phase_name,
                duration_seconds=duration,
                error=str(e),
                data={},
                metadata={"checkpoint_id": checkpoint_id}
            )
    
    # ==================== Helper Methods ====================
    
    def _create_embedding_loader(self, model_spec):
        """
        Create loader function for embedding model
        
        This wraps the actual model loading logic
        """
        async def loader():
            # Lazy import to avoid circular dependencies
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading SentenceTransformer: {model_spec.model_name}")
            
            # Load model
            model = SentenceTransformer(model_spec.model_name)
            
            return model
        
        return loader
    
    def _test_inference(self, model):
        """Run a test inference for health check"""
        # Simple test inference
        test_text = "test document for embedding"
        embedding = model.encode(test_text)
        return embedding
    
    async def _cleanup_model(self, model):
        """Cleanup model resources"""
        try:
            # Attempt to free GPU memory
            if hasattr(model, 'to'):
                model.to('cpu')
            
            # Delete model
            del model
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clear CUDA cache if available
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            
            logger.debug("Model cleanup complete")
        except Exception as e:
            logger.warning(f"Model cleanup error: {e}")

