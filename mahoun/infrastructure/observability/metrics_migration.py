"""
Metrics Migration Layer
========================

Compatibility layer for migrating from mahoun.core.metrics to mahoun.metrics.

This module provides backward-compatible wrappers that translate the old
simple API (record_counter, record_gauge, record_timing) to the new
Prometheus-style API (register_counter, counter.inc, etc.).

Usage:
    from mahoun.infrastructure.observability.metrics_migration import MetricsCollector
    
    collector = MetricsCollector()
    collector.record_counter("test", 5)  # Old API
    collector.record_gauge("gauge", 42.0)  # Old API
    
    # Internally translates to:
    # counter = collector.register_counter("test")
    # counter.inc(5)

Deprecation Timeline:
    - Phase 4 (current): Migration layer active, old API works
    - Phase 5 (2 weeks): Deprecation warnings added
    - Phase 6 (4 weeks): Old API removed
    - Phase 7 (6 weeks): mahoun.core.metrics deleted

Architecture:
    - Thread-safe with RLock for concurrent access
    - Internal metric cache prevents duplicate registration errors
    - Seamless translation between old simple API and new Prometheus API
    - Full backward compatibility with existing test suite
"""

import threading
import warnings
from typing import Any, Dict, Optional
from collections import defaultdict

from mahoun.metrics import (
    MetricsCollector as PrometheusMetricsCollector,
    get_metrics_collector as get_prometheus_collector,
    Counter,
    Gauge,
    Histogram
)


class MetricsCollector:
    """
    Backward-compatible metrics collector with enterprise-grade thread safety.
    
    Wraps mahoun.metrics.MetricsCollector and provides the old simple API
    while internally using the new Prometheus-style API.
    
    Features:
        - Thread-safe with RLock for concurrent access
        - Internal metric cache prevents duplicate registration
        - Seamless API translation (old → new)
        - Full backward compatibility
    
    Old API (deprecated):
        collector.record_counter("name", value)
        collector.record_gauge("name", value)
        collector.record_timing("name", duration_ms)
    
    New API (recommended):
        counter = collector.register_counter("name")
        counter.inc(value)
        
        gauge = collector.register_gauge("name")
        gauge.set(value)
    """
    
    def __init__(self, config: Optional[Any] = None, enable_system_metrics: bool = True):
        """
        Initialize metrics collector.
        
        Args:
            config: ObservabilityConfig (optional)
            enable_system_metrics: Whether to register system metrics (default: True)
                                  Set to False in tests to avoid system metric pollution
        """
        # Use the production Prometheus collector
        self._prometheus_collector = PrometheusMetricsCollector(config=config)
        
        # Thread-safe lock for concurrent access
        self._lock = threading.RLock()
        
        # Internal metric cache to prevent duplicate registration
        self._metric_cache: Dict[str, Any] = {}
        
        # Track history for backward compatibility
        self._counter_history: Dict[str, int] = defaultdict(int)
        self._gauge_history: Dict[str, int] = defaultdict(int)
        self._timing_history: Dict[str, int] = defaultdict(int)
        
        # Track whether to include system metrics
        self._enable_system_metrics = enable_system_metrics
    
    # ========================================================================
    # OLD API (Deprecated) - For backward compatibility
    # ========================================================================
    
    def record_counter(self, name: str, value: int = 1) -> None:
        """
        Record a counter value (OLD API - deprecated).
        
        This method is provided for backward compatibility. New code should use:
            counter = collector.register_counter(name)
            counter.inc(value)
        
        Args:
            name: Counter name
            value: Amount to increment (default: 1)
        """
        with self._lock:
            # Check cache first to avoid duplicate registration
            cache_key = f"counter:{name}"
            if cache_key not in self._metric_cache:
                counter = self._prometheus_collector.register_counter(name)
                self._metric_cache[cache_key] = counter
            else:
                counter = self._metric_cache[cache_key]
            
            counter.inc(value)
            self._counter_history[name] += 1
    
    def record_gauge(self, name: str, value: float) -> None:
        """
        Record a gauge value (OLD API - deprecated).
        
        This method is provided for backward compatibility. New code should use:
            gauge = collector.register_gauge(name)
            gauge.set(value)
        
        Args:
            name: Gauge name
            value: Gauge value
        """
        with self._lock:
            # Check cache first to avoid duplicate registration
            cache_key = f"gauge:{name}"
            if cache_key not in self._metric_cache:
                gauge = self._prometheus_collector.register_gauge(name)
                self._metric_cache[cache_key] = gauge
            else:
                gauge = self._metric_cache[cache_key]
            
            gauge.set(value)
            self._gauge_history[name] += 1
    
    def record_timing(self, name: str, duration_ms: float) -> None:
        """
        Record a timing value (OLD API - deprecated).
        
        This method is provided for backward compatibility. New code should use:
            histogram = collector.register_histogram(f"{name}.duration_ms")
            histogram.observe(duration_ms)
        
        Args:
            name: Operation name
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            # Convert to histogram for better percentile tracking
            histogram_name = f"{name}.duration_ms"
            cache_key = f"histogram:{histogram_name}"
            
            if cache_key not in self._metric_cache:
                histogram = self._prometheus_collector.register_histogram(histogram_name)
                self._metric_cache[cache_key] = histogram
            else:
                histogram = self._metric_cache[cache_key]
            
            histogram.observe(duration_ms)
            self._timing_history[name] += 1
    
    def get_metrics(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics (OLD API - backward compatible).
        
        Args:
            name: Metric name (if None, returns all metrics)
        
        Returns:
            Dictionary with metric data
        """
        # System metric names to filter out if disabled
        system_metric_names = {
            "mahoun_system_cpu_percent",
            "mahoun_system_memory_bytes",
            "mahoun_system_uptime_seconds"
        }
        
        if name is None:
            # Return all metrics
            all_metrics = self._prometheus_collector.get_all_metrics()
            
            # Convert to old format
            result = {
                "counters": {},
                "gauges": {},
                "timings": {}
            }
            
            for counter_name, counter_data in all_metrics.get("counters", {}).items():
                # Filter system metrics if disabled
                if not self._enable_system_metrics and counter_name in system_metric_names:
                    continue
                result["counters"][counter_name] = counter_data["value"]
            
            for gauge_name, gauge_data in all_metrics.get("gauges", {}).items():
                # Filter system metrics if disabled
                if not self._enable_system_metrics and gauge_name in system_metric_names:
                    continue
                result["gauges"][gauge_name] = gauge_data["value"]
            
            for histogram_name, histogram_data in all_metrics.get("histograms", {}).items():
                # Extract timing name (remove .duration_ms suffix)
                if histogram_name.endswith(".duration_ms"):
                    timing_name = histogram_name[:-12]  # Remove ".duration_ms"
                    result["timings"][timing_name] = histogram_data["percentiles"]
            
            return result
        
        # Check for timing (histogram) FIRST - this is the most common case
        # Try with .duration_ms suffix
        histogram_name = f"{name}.duration_ms"
        histogram = self._prometheus_collector.get_histogram(histogram_name)
        if histogram:
            percentiles = histogram.get_percentiles()
            return {
                "gauge": percentiles.get("p50", 0.0),  # Use median as "gauge"
                "percentiles": percentiles,
                "history_count": self._timing_history[name]
            }
        
        # If name already ends with .duration_ms, try as-is
        if name.endswith(".duration_ms"):
            histogram = self._prometheus_collector.get_histogram(name)
            if histogram:
                base_name = name[:-12]
                percentiles = histogram.get_percentiles()
                return {
                    "gauge": percentiles.get("p50", 0.0),
                    "percentiles": percentiles,
                    "history_count": self._timing_history.get(base_name, 0)
                }
        
        # Check for counter
        counter = self._prometheus_collector.get_counter(name)
        if counter:
            return {
                "counter": counter.value,
                "history_count": self._counter_history[name]
            }
        
        # Check for gauge
        gauge = self._prometheus_collector.get_gauge(name)
        if gauge:
            return {
                "gauge": gauge.value,
                "history_count": self._gauge_history[name]
            }
        
        # Metric not found - return empty
        return {
            "counter": 0,
            "gauge": 0.0,
            "history_count": 0
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary (OLD API - backward compatible).
        
        Returns:
            Dictionary with summary statistics
        """
        all_metrics = self._prometheus_collector.get_all_metrics()
        
        return {
            "total_counters": len(all_metrics.get("counters", {})),
            "total_gauges": len(all_metrics.get("gauges", {})),
            "total_histograms": len(all_metrics.get("histograms", {})),
            "total_data_points": (
                sum(self._counter_history.values()) +
                sum(self._gauge_history.values()) +
                sum(self._timing_history.values())
            )
        }
    
    def reset(self, name: Optional[str] = None) -> None:
        """
        Reset metrics (OLD API - backward compatible).
        
        Thread-safe reset that clears both cache and metric values.
        
        Args:
            name: Metric name (if None, resets all metrics)
        """
        with self._lock:
            if name is None:
                # Reset all metrics
                self._counter_history.clear()
                self._gauge_history.clear()
                self._timing_history.clear()
                
                # Clear cache
                self._metric_cache.clear()
                
                # Use the refactored collector's reset method
                self._prometheus_collector.reset()
            else:
                # Reset specific metric - keep it in history but set to 0
                # Check all possible metric types
                cache_key_counter = f"counter:{name}"
                cache_key_gauge = f"gauge:{name}"
                histogram_name = f"{name}.duration_ms"
                cache_key_histogram = f"histogram:{histogram_name}"
                
                # Reset counter
                if cache_key_counter in self._metric_cache:
                    self._counter_history[name] = 0
                    self._metric_cache[cache_key_counter].value = 0
                else:
                    # Try to get from store
                    counter = self._prometheus_collector.get_counter(name)
                    if counter:
                        self._counter_history[name] = 0
                        counter.value = 0
                
                # Reset gauge
                if cache_key_gauge in self._metric_cache:
                    self._gauge_history[name] = 0
                    self._metric_cache[cache_key_gauge].value = 0.0
                else:
                    # Try to get from store
                    gauge = self._prometheus_collector.get_gauge(name)
                    if gauge:
                        self._gauge_history[name] = 0
                        gauge.value = 0.0
                
                # Reset histogram/timing
                if cache_key_histogram in self._metric_cache:
                    self._timing_history[name] = 0
                    self._metric_cache[cache_key_histogram].values.clear()
                else:
                    # Try to get from store
                    histogram = self._prometheus_collector.get_histogram(histogram_name)
                    if histogram:
                        self._timing_history[name] = 0
                        histogram.values.clear()
    
    # ========================================================================
    # NEW API (Recommended) - Direct pass-through to Prometheus collector
    # ========================================================================
    
    def register_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> Counter:
        """
        Register a counter metric (NEW API - recommended).
        
        Thread-safe registration with internal caching.
        
        Args:
            name: Counter name
            labels: Optional labels
        
        Returns:
            Counter instance
        """
        with self._lock:
            cache_key = f"counter:{name}"
            if cache_key not in self._metric_cache:
                counter = self._prometheus_collector.register_counter(name, labels)
                self._metric_cache[cache_key] = counter
            return self._metric_cache[cache_key]
    
    def register_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Gauge:
        """
        Register a gauge metric (NEW API - recommended).
        
        Thread-safe registration with internal caching.
        
        Args:
            name: Gauge name
            labels: Optional labels
        
        Returns:
            Gauge instance
        """
        with self._lock:
            cache_key = f"gauge:{name}"
            if cache_key not in self._metric_cache:
                gauge = self._prometheus_collector.register_gauge(name, labels)
                self._metric_cache[cache_key] = gauge
            return self._metric_cache[cache_key]
    
    def register_histogram(self, name: str, buckets: Optional[list] = None, labels: Optional[Dict[str, str]] = None) -> Histogram:
        """
        Register a histogram metric (NEW API - recommended).
        
        Thread-safe registration with internal caching.
        
        Args:
            name: Histogram name
            buckets: Bucket boundaries
            labels: Optional labels
        
        Returns:
            Histogram instance
        """
        with self._lock:
            cache_key = f"histogram:{name}"
            if cache_key not in self._metric_cache:
                histogram = self._prometheus_collector.register_histogram(name, buckets, labels)
                self._metric_cache[cache_key] = histogram
            return self._metric_cache[cache_key]
    
    def to_prometheus(self) -> str:
        """
        Export metrics in Prometheus format (NEW API).
        
        Returns:
            Prometheus-formatted metrics string
        """
        return self._prometheus_collector.to_prometheus()
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics as dictionary (NEW API).
        
        Returns:
            Dictionary with all metrics
        """
        return self._prometheus_collector.get_all_metrics()


# Global singleton instance
_migration_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get global metrics collector instance (singleton).
    
    Returns:
        MetricsCollector instance with backward-compatible API
    """
    global _migration_collector
    
    if _migration_collector is None:
        _migration_collector = MetricsCollector()
    
    return _migration_collector


# Convenience functions (OLD API - deprecated)
def record_counter(name: str, value: int = 1) -> None:
    """Record a counter value (deprecated - use register_counter instead)."""
    get_metrics_collector().record_counter(name, value)


def record_gauge(name: str, value: float) -> None:
    """Record a gauge value (deprecated - use register_gauge instead)."""
    get_metrics_collector().record_gauge(name, value)


def record_timing(name: str, duration_ms: float) -> None:
    """Record a timing value (deprecated - use register_histogram instead)."""
    get_metrics_collector().record_timing(name, duration_ms)
