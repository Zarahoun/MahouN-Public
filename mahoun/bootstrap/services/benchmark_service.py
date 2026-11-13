"""
Benchmark Service for Model Performance Profiling

Extracted from: mahoun/bootstrap/executors/ai_ml_components.py (lines 763-779, 1097-1108)
Responsibility: Profile model performance metrics (latency, throughput, memory)
               for capacity planning and SLA validation.

Architecture:
- Multi-iteration benchmarking with warmup
- Statistical analysis (mean, median, p95, p99)
- Resource tracking (CPU, RAM, GPU)
- Async/await for non-blocking operations
"""

import asyncio
import logging
import psutil
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class BenchmarkMetric(str, Enum):
    """Benchmark metric types"""
    LATENCY = "latency"         # Time per inference
    THROUGHPUT = "throughput"   # Inferences per second
    MEMORY = "memory"           # Memory usage
    GPU_MEMORY = "gpu_memory"   # GPU memory usage


@dataclass
class BenchmarkConfig:
    """Benchmark configuration"""
    warmup_iterations: int = 5
    measurement_iterations: int = 20
    timeout_seconds: float = 300.0
    collect_memory_metrics: bool = True
    collect_gpu_metrics: bool = True


@dataclass
class BenchmarkMetrics:
    """Statistical benchmark results"""
    mean: float
    median: float
    p95: float
    p99: float
    min: float
    max: float
    stddev: float
    samples: List[float] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """Comprehensive benchmark result"""
    model_name: str
    latency_ms: BenchmarkMetrics
    throughput_per_sec: float
    memory_mb: Optional[BenchmarkMetrics]
    gpu_memory_mb: Optional[BenchmarkMetrics]
    total_iterations: int
    duration_seconds: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class BenchmarkService:
    """
    Production-grade model benchmarking service
    
    Features:
    - Multi-iteration profiling with warmup
    - Statistical analysis (mean, median, percentiles)
    - Resource tracking (CPU, RAM, GPU)
    - Async/await for non-blocking operations
    - Comprehensive result reporting
    
    Example:
        service = BenchmarkService(
            config=BenchmarkConfig(
                warmup_iterations=5,
                measurement_iterations=20
            )
        )
        
        result = await service.benchmark_model(
            model_name="embedding-model",
            model=embedding_model,
            inference_func=lambda m: m.encode("test input"),
            metadata={"model_size_mb": 420}
        )
        
        print(f"Latency: {result.latency_ms.mean:.2f}ms (p95: {result.latency_ms.p95:.2f}ms)")
        print(f"Throughput: {result.throughput_per_sec:.1f} inferences/sec")
    """
    
    def __init__(self, config: Optional[BenchmarkConfig] = None):
        self.config = config or BenchmarkConfig()
    
    async def benchmark_model(
        self,
        model_name: str,
        model: Any,
        inference_func: Callable[[Any], Any],
        sample_input: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> BenchmarkResult:
        """
        Benchmark model with comprehensive profiling
        
        Args:
            model_name: Human-readable model identifier
            model: The model instance to benchmark
            inference_func: Function to run inference (receives model as argument)
            sample_input: Optional input for inference (uses default if None)
            metadata: Additional context
        
        Returns:
            BenchmarkResult with statistical analysis and resource metrics
        """
        logger.info(
            f"Benchmarking model '{model_name}' "
            f"(warmup={self.config.warmup_iterations}, "
            f"iterations={self.config.measurement_iterations})"
        )
        
        start_time = datetime.utcnow()
        
        # Default sample input
        if sample_input is None:
            sample_input = "test"
        
        # 1. Warmup phase (don't measure these)
        logger.info(f"Warmup phase: {self.config.warmup_iterations} iterations")
        for i in range(self.config.warmup_iterations):
            try:
                _ = await self._run_inference(inference_func, model, sample_input)
            except Exception as e:
                logger.warning(f"Warmup iteration {i+1} failed: {e}")
        
        # 2. Measurement phase
        logger.info(f"Measurement phase: {self.config.measurement_iterations} iterations")
        latency_samples: List[float] = []
        memory_samples: List[float] = []
        gpu_memory_samples: List[float] = []
        
        for i in range(self.config.measurement_iterations):
            try:
                # Measure latency
                inference_start = datetime.utcnow()
                
                # Measure memory before
                memory_before = self._get_memory_mb() if self.config.collect_memory_metrics else None
                gpu_memory_before = self._get_gpu_memory_mb() if self.config.collect_gpu_metrics else None
                
                # Run inference
                _ = await asyncio.wait_for(
                    self._run_inference(inference_func, model, sample_input),
                    timeout=self.config.timeout_seconds
                )
                
                # Measure metrics after
                latency_ms = (datetime.utcnow() - inference_start).total_seconds() * 1000
                latency_samples.append(latency_ms)
                
                if self.config.collect_memory_metrics and memory_before is not None:
                    memory_after = self._get_memory_mb()
                    memory_samples.append(memory_after - memory_before)
                
                if self.config.collect_gpu_metrics and gpu_memory_before is not None:
                    gpu_memory_after = self._get_gpu_memory_mb()
                    if gpu_memory_after is not None:
                        gpu_memory_samples.append(gpu_memory_after - gpu_memory_before)
                
            except asyncio.TimeoutError:
                logger.error(
                    f"Iteration {i+1} timeout (>{self.config.timeout_seconds}s)"
                )
                continue
            except Exception as e:
                logger.error(f"Iteration {i+1} failed: {e}")
                continue
        
        # 3. Statistical analysis
        if not latency_samples:
            raise RuntimeError(
                f"Benchmark failed: no successful iterations for model '{model_name}'"
            )
        
        latency_metrics = self._calculate_metrics(latency_samples)
        memory_metrics = self._calculate_metrics(memory_samples) if memory_samples else None
        gpu_memory_metrics = self._calculate_metrics(gpu_memory_samples) if gpu_memory_samples else None
        
        # Calculate throughput (inferences per second)
        mean_latency_seconds = latency_metrics.mean / 1000
        throughput_per_sec = 1.0 / mean_latency_seconds if mean_latency_seconds > 0 else 0.0
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"Benchmark complete for '{model_name}': "
            f"latency={latency_metrics.mean:.2f}ms (p95={latency_metrics.p95:.2f}ms), "
            f"throughput={throughput_per_sec:.1f}/sec, "
            f"iterations={len(latency_samples)}, "
            f"duration={duration:.1f}s"
        )
        
        return BenchmarkResult(
            model_name=model_name,
            latency_ms=latency_metrics,
            throughput_per_sec=throughput_per_sec,
            memory_mb=memory_metrics,
            gpu_memory_mb=gpu_memory_metrics,
            total_iterations=len(latency_samples),
            duration_seconds=duration,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )
    
    async def _run_inference(
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
    
    def _calculate_metrics(self, samples: List[float]) -> BenchmarkMetrics:
        """Calculate statistical metrics from samples"""
        if not samples:
            return BenchmarkMetrics(
                mean=0.0, median=0.0, p95=0.0, p99=0.0,
                min=0.0, max=0.0, stddev=0.0, samples=[]
            )
        
        sorted_samples = sorted(samples)
        
        return BenchmarkMetrics(
            mean=statistics.mean(samples),
            median=statistics.median(samples),
            p95=self._percentile(sorted_samples, 95),
            p99=self._percentile(sorted_samples, 99),
            min=min(samples),
            max=max(samples),
            stddev=statistics.stdev(samples) if len(samples) > 1 else 0.0,
            samples=samples
        )
    
    def _percentile(self, sorted_samples: List[float], percentile: int) -> float:
        """Calculate percentile from sorted samples"""
        if not sorted_samples:
            return 0.0
        
        index = int((percentile / 100) * len(sorted_samples))
        # Clamp to valid range
        index = max(0, min(index, len(sorted_samples) - 1))
        return sorted_samples[index]
    
    def _get_memory_mb(self) -> float:
        """Get current process memory usage in MB"""
        return psutil.Process().memory_info().rss / (1024 * 1024)
    
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
