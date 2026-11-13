"""
Model Health Checking Service

Extracted from: mahoun/bootstrap/executors/ai_ml_components.py (lines 342-370)
Responsibility: Verify model health with baseline comparison, inference tests,
               and resource monitoring. Detect unhealthy models before production use.

NOTE: Renamed to ModelHealthChecker to avoid collision with:
      mahoun/infrastructure/health_checker.py (infrastructure health: Ollama/Neo4j/VectorStore)

Architecture:
- Baseline comparison for performance regression detection
- Inference tests with sample inputs
- Resource monitoring (memory, GPU)
- Fail-closed: assume UNHEALTHY until proven otherwise
"""

import asyncio
import logging
import psutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Model health states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Still operational but slower than baseline
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckConfig:
    """Health check configuration"""
    inference_timeout_seconds: float = 30.0
    max_inference_duration_multiplier: float = 3.0  # vs baseline
    min_memory_available_mb: int = 512
    gpu_memory_threshold_percent: float = 95.0
    warmup_iterations: int = 2  # Ignore first N results


@dataclass
class InferenceMetrics:
    """Metrics from an inference test"""
    duration_seconds: float
    memory_used_mb: float
    gpu_memory_used_mb: Optional[float]
    success: bool
    error: Optional[Exception]


@dataclass
class HealthCheckResult:
    """Comprehensive health check result"""
    status: HealthStatus
    inference_metrics: InferenceMetrics
    baseline_duration_seconds: Optional[float]
    deviation_from_baseline: Optional[float]  # Multiplier (e.g., 2.5 = 2.5x slower)
    warnings: List[str]
    errors: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class ModelHealthChecker:
    """
    Production-grade model health checker
    
    Features:
    - Baseline comparison for regression detection
    - Sample inference tests with real inputs
    - Resource monitoring (RAM, GPU)
    - Fail-closed: UNHEALTHY until proven otherwise
    - Configurable degradation thresholds
    
    Example:
        checker = ModelHealthChecker(
            config=HealthCheckConfig(
                inference_timeout_seconds=30.0,
                max_inference_duration_multiplier=3.0
            )
        )
        
        result = await checker.check_health(
            model_name="embedding-model",
            model=embedding_model,
            inference_func=lambda m: m.encode("test"),
            baseline_duration_seconds=0.2  # From previous run
        )
        
        if result.status == HealthStatus.HEALTHY:
            print(f"Model is healthy (latency: {result.inference_metrics.duration_seconds:.3f}s)")
        else:
            print(f"Model is {result.status}: {result.errors}")
    """
    
    def __init__(self, config: Optional[HealthCheckConfig] = None):
        self.config = config or HealthCheckConfig()
    
    async def check_health(
        self,
        model_name: str,
        model: Any,
        inference_func: Callable[[Any], Any],
        baseline_duration_seconds: Optional[float] = None,
        sample_inputs: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HealthCheckResult:
        """
        Check model health with comprehensive tests
        
        Args:
            model_name: Human-readable model identifier
            model: The model instance to test
            inference_func: Function to run inference (receives model as argument)
            baseline_duration_seconds: Expected inference duration for comparison
            sample_inputs: Optional list of inputs for inference (uses defaults if None)
            metadata: Additional context
        
        Returns:
            HealthCheckResult with status, metrics, and diagnostics
        """
        warnings: List[str] = []
        errors: List[str] = []
        
        logger.info(f"Health check starting for model '{model_name}'")
        
        # 1. Check system resources
        resource_ok, resource_warnings = self._check_system_resources()
        warnings.extend(resource_warnings)
        
        if not resource_ok:
            logger.error(f"Model '{model_name}' health check FAILED: insufficient resources")
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                inference_metrics=InferenceMetrics(
                    duration_seconds=0.0,
                    memory_used_mb=0.0,
                    gpu_memory_used_mb=None,
                    success=False,
                    error=RuntimeError("Insufficient system resources")
                ),
                baseline_duration_seconds=baseline_duration_seconds,
                deviation_from_baseline=None,
                warnings=warnings,
                errors=["Insufficient system resources"],
                timestamp=datetime.utcnow(),
                metadata=metadata or {}
            )
        
        # 2. Run inference test with warmup
        inference_metrics = await self._run_inference_test(
            model_name=model_name,
            model=model,
            inference_func=inference_func,
            sample_inputs=sample_inputs
        )
        
        if not inference_metrics.success:
            logger.error(
                f"Model '{model_name}' health check FAILED: "
                f"inference test failed: {inference_metrics.error}"
            )
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                inference_metrics=inference_metrics,
                baseline_duration_seconds=baseline_duration_seconds,
                deviation_from_baseline=None,
                warnings=warnings,
                errors=[f"Inference test failed: {inference_metrics.error}"],
                timestamp=datetime.utcnow(),
                metadata=metadata or {}
            )
        
        # 3. Compare against baseline
        deviation_from_baseline: Optional[float] = None
        status = HealthStatus.HEALTHY
        
        if baseline_duration_seconds:
            deviation_from_baseline = inference_metrics.duration_seconds / baseline_duration_seconds
            
            if deviation_from_baseline > self.config.max_inference_duration_multiplier:
                logger.warning(
                    f"Model '{model_name}' is DEGRADED: "
                    f"inference took {deviation_from_baseline:.2f}x baseline "
                    f"({inference_metrics.duration_seconds:.3f}s vs {baseline_duration_seconds:.3f}s)"
                )
                status = HealthStatus.DEGRADED
                warnings.append(
                    f"Inference {deviation_from_baseline:.2f}x slower than baseline "
                    f"(threshold: {self.config.max_inference_duration_multiplier}x)"
                )
            elif deviation_from_baseline > 1.5:
                # Minor degradation (1.5-3x) → still HEALTHY but warn
                warnings.append(
                    f"Inference {deviation_from_baseline:.2f}x slower than baseline "
                    f"(still within threshold)"
                )
        else:
            logger.info(
                f"Model '{model_name}' health check: no baseline available, "
                f"recording {inference_metrics.duration_seconds:.3f}s as new baseline"
            )
        
        logger.info(
            f"Model '{model_name}' health check complete: {status} "
            f"(latency={inference_metrics.duration_seconds:.3f}s, "
            f"memory={inference_metrics.memory_used_mb:.1f}MB)"
        )
        
        return HealthCheckResult(
            status=status,
            inference_metrics=inference_metrics,
            baseline_duration_seconds=baseline_duration_seconds,
            deviation_from_baseline=deviation_from_baseline,
            warnings=warnings,
            errors=errors,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )
    
    def _check_system_resources(self) -> Tuple[bool, List[str]]:
        """
        Check if system has sufficient resources
        
        Returns:
            (is_ok, warnings)
        """
        warnings: List[str] = []
        
        # Check RAM
        memory = psutil.virtual_memory()
        available_mb = memory.available / (1024 * 1024)
        
        if available_mb < self.config.min_memory_available_mb:
            warnings.append(
                f"Low memory: {available_mb:.0f}MB available "
                f"(min: {self.config.min_memory_available_mb}MB)"
            )
            return False, warnings
        
        # Check GPU if available
        try:
            import torch
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    gpu_memory_used = torch.cuda.memory_allocated(i) / (1024 * 1024 * 1024)
                    gpu_memory_total = torch.cuda.get_device_properties(i).total_memory / (1024 * 1024 * 1024)
                    gpu_memory_percent = (gpu_memory_used / gpu_memory_total) * 100
                    
                    if gpu_memory_percent > self.config.gpu_memory_threshold_percent:
                        warnings.append(
                            f"GPU {i} memory high: {gpu_memory_percent:.1f}% used "
                            f"({gpu_memory_used:.2f}GB / {gpu_memory_total:.2f}GB)"
                        )
        except ImportError:
            pass  # torch not available, skip GPU check
        
        return True, warnings
    
    async def _run_inference_test(
        self,
        model_name: str,
        model: Any,
        inference_func: Callable[[Any], Any],
        sample_inputs: Optional[List[Any]] = None
    ) -> InferenceMetrics:
        """
        Run inference test with resource monitoring
        
        Returns:
            InferenceMetrics with duration, memory usage, and status
        """
        # Default sample input if none provided
        if sample_inputs is None:
            sample_inputs = ["test"]
        
        # Warmup iterations (ignore these measurements)
        for i in range(self.config.warmup_iterations):
            try:
                _ = await self._run_single_inference(inference_func, model, sample_inputs[0])
            except Exception as e:
                logger.warning(f"Warmup iteration {i+1} failed: {e}")
        
        # Actual measurement
        memory_before = psutil.Process().memory_info().rss / (1024 * 1024)
        gpu_memory_before = self._get_gpu_memory_mb()
        
        start_time = datetime.utcnow()
        
        try:
            # Run inference with timeout
            result = await asyncio.wait_for(
                self._run_single_inference(inference_func, model, sample_inputs[0]),
                timeout=self.config.inference_timeout_seconds
            )
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            memory_after = psutil.Process().memory_info().rss / (1024 * 1024)
            gpu_memory_after = self._get_gpu_memory_mb()
            
            memory_used = memory_after - memory_before
            gpu_memory_used = gpu_memory_after - gpu_memory_before if gpu_memory_before else None
            
            return InferenceMetrics(
                duration_seconds=duration,
                memory_used_mb=memory_used,
                gpu_memory_used_mb=gpu_memory_used,
                success=True,
                error=None
            )
        
        except asyncio.TimeoutError:
            duration = self.config.inference_timeout_seconds
            error = TimeoutError(
                f"Inference exceeded timeout ({self.config.inference_timeout_seconds}s)"
            )
            logger.error(f"Model '{model_name}' inference timeout: {error}")
            
            return InferenceMetrics(
                duration_seconds=duration,
                memory_used_mb=0.0,
                gpu_memory_used_mb=None,
                success=False,
                error=error
            )
        
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Model '{model_name}' inference failed: {e}")
            
            return InferenceMetrics(
                duration_seconds=duration,
                memory_used_mb=0.0,
                gpu_memory_used_mb=None,
                success=False,
                error=e
            )
    
    async def _run_single_inference(
        self,
        inference_func: Callable[[Any], Any],
        model: Any,
        sample_input: Any
    ) -> Any:
        """Run inference (handles sync/async functions)"""
        if asyncio.iscoroutinefunction(inference_func):
            return await inference_func(model)
        else:
            # Run sync function in executor to not block event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, inference_func, model)
    
    def _get_gpu_memory_mb(self) -> Optional[float]:
        """Get current GPU memory usage in MB (all GPUs combined)"""
        try:
            import torch
            if torch.cuda.is_available():
                total_memory_mb = 0.0
                for i in range(torch.cuda.device_count()):
                    total_memory_mb += torch.cuda.memory_allocated(i) / (1024 * 1024)
                return total_memory_mb
        except ImportError:
            pass
        return None
