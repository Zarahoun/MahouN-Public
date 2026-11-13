# MAHOUN Profiler — Lightweight Internal Profiler
"""
Production-grade profiler for MAHOUN with flamegraph support.
"""

import asyncio
import functools
import json
import logging
import os
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
import threading

from ..config import get_observability_config

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ProfileResult:
    """Result of a profiling operation."""
    name: str
    cpu_time: float  # CPU time in seconds
    wall_time: float  # Wall clock time in seconds
    memory_delta: int  # Memory delta in bytes
    memory_peak: int  # Peak memory in bytes
    call_count: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_flamegraph_format(self) -> Dict[str, Any]:
        """Convert to flamegraph-compatible format."""
        return {
            "name": self.name,
            "value": int(self.cpu_time * 1_000_000),  # microseconds
            "children": []
        }


class ProfilerContext:
    """Context manager for profiling."""
    
    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize profiler context.
        
        Args:
            name: Operation name
            metadata: Additional metadata
        """
        self.name = name
        self.metadata = metadata or {}
        self.start_cpu = None
        self.start_wall = None
        self.start_memory = None
        self.snapshot_start = None
        self.result: Optional[ProfileResult] = None
        self._profiler = get_profiler()
    
    def __enter__(self):
        """Start profiling."""
        if not self._profiler.config.profiler_enabled:
            return self
        
        # Start CPU time tracking
        self.start_cpu = time.process_time()
        self.start_wall = time.time()
        
        # Start memory tracking
        if tracemalloc.is_tracing():
            self.snapshot_start = tracemalloc.take_snapshot()
        else:
            tracemalloc.start()
            self.snapshot_start = tracemalloc.take_snapshot()
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop profiling and record result."""
        if not self._profiler.config.profiler_enabled:
            return
        
        # Calculate times
        cpu_time = time.process_time() - self.start_cpu
        wall_time = time.time() - self.start_wall
        
        # Calculate memory
        snapshot_end = tracemalloc.take_snapshot()
        top_stats = snapshot_end.compare_to(self.snapshot_start, 'lineno')
        
        memory_delta = sum(stat.size_diff for stat in top_stats)
        memory_peak = sum(stat.size for stat in top_stats[:10])
        
        # Create result
        self.result = ProfileResult(
            name=self.name,
            cpu_time=cpu_time,
            wall_time=wall_time,
            memory_delta=memory_delta,
            memory_peak=memory_peak,
            metadata={**self.metadata, "exception": str(exc_type) if exc_type else None}
        )
        
        # Record in profiler
        self._profiler.record(self.result)
        
        return False  # Don't suppress exceptions


class Profiler:
    """
    Main profiler class.
    
    Thread-safe profiler that collects and analyzes performance data.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize profiler.
        
        Args:
            config: ObservabilityConfig (default: from get_observability_config)
        """
        from ..config import ObservabilityConfig, get_observability_config
        
        self.config = config or get_observability_config()
        self._results: List[ProfileResult] = []
        self._lock = threading.RLock()
        self._slow_operations: List[ProfileResult] = []
        self._slow_threshold: float = 1.0  # 1 second
        
        # Initialize tracemalloc if enabled
        if self.config.profiler_enabled and not tracemalloc.is_tracing():
            tracemalloc.start()
    
    def record(self, result: ProfileResult) -> None:
        """
        Record a profiling result.
        
        Args:
            result: ProfileResult to record
        """
        if not self.config.profiler_enabled:
            return
        
        with self._lock:
            self._results.append(result)
            
            # Track slow operations
            if result.wall_time >= self._slow_threshold:
                self._slow_operations.append(result)
                logger.warning(
                    f"Slow operation detected: {result.name} took {result.wall_time:.3f}s"
                )
            
            # Auto-save if results exceed threshold
            if len(self._results) >= 100:
                self._auto_save()
    
    def _auto_save(self) -> None:
        """Auto-save results to disk."""
        try:
            self.save_results()
            with self._lock:
                self._results.clear()  # Clear after save
        except Exception as e:
            logger.error(f"Failed to auto-save profiler results: {e}")
    
    def save_results(self, filename: Optional[str] = None) -> None:
        """
        Save profiling results to disk.
        
        Args:
            filename: Optional filename (default: auto-generated)
        """
        if not self.config.profiler_enabled:
            return
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"profile_{timestamp}.json"
        
        filepath = self.config.profiler_dir / filename
        
        with self._lock:
            results_data = [r.to_dict() for r in self._results]
            flamegraph_data = [r.to_flamegraph_format() for r in self._results]
        
        # Save regular results
        with open(filepath, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        # Save flamegraph format
        flamegraph_path = filepath.with_suffix('.flamegraph.json')
        with open(flamegraph_path, 'w') as f:
            json.dump(flamegraph_data, f, indent=2)
        
        logger.info(f"Profiler results saved to {filepath}")
    
    def get_slow_operations(self, limit: int = 10) -> List[ProfileResult]:
        """
        Get top slow operations.
        
        Args:
            limit: Number of operations to return
            
        Returns:
            List of slowest ProfileResults
        """
        with self._lock:
            sorted_ops = sorted(
                self._slow_operations,
                key=lambda x: x.wall_time,
                reverse=True
            )
            return sorted_ops[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get profiler statistics."""
        with self._lock:
            if not self._results:
                return {
                    "total_operations": 0,
                    "slow_operations": 0,
                    "avg_wall_time": 0.0,
                    "avg_cpu_time": 0.0,
                    "total_memory_delta": 0
                }
            
            total_ops = len(self._results)
            total_wall = sum(r.wall_time for r in self._results)
            total_cpu = sum(r.cpu_time for r in self._results)
            total_memory = sum(r.memory_delta for r in self._results)
            
            return {
                "total_operations": total_ops,
                "slow_operations": len(self._slow_operations),
                "avg_wall_time": total_wall / total_ops if total_ops > 0 else 0.0,
                "avg_cpu_time": total_cpu / total_ops if total_ops > 0 else 0.0,
                "total_memory_delta": total_memory,
                "slow_threshold": self._slow_threshold
            }
    
    def clear(self) -> None:
        """Clear all recorded results."""
        with self._lock:
            self._results.clear()
            self._slow_operations.clear()


# Global profiler instance
_profiler_instance: Optional[Profiler] = None
_profiler_lock = threading.Lock()


def get_profiler() -> Profiler:
    """Get global profiler instance (singleton)."""
    global _profiler_instance
    
    if _profiler_instance is None:
        with _profiler_lock:
            if _profiler_instance is None:
                _profiler_instance = Profiler()
    
    return _profiler_instance


def mahoun_profile(
    name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Decorator for profiling functions/methods.
    
    Usage:
        @mahoun_profile(name="my_operation")
        async def my_function():
            ...
    
    Args:
        name: Operation name (default: function name)
        metadata: Additional metadata
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = name or f"{func.__module__}.{func.__name__}"
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                with ProfilerContext(op_name, metadata):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                with ProfilerContext(op_name, metadata):
                    return func(*args, **kwargs)
            return sync_wrapper
    
    return decorator
