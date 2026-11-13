# Observability Configuration — MAHOUN
"""
Configuration for MAHOUN Observability Toolkit.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ObservabilityConfig:
    """
    Configuration for observability features.
    
    Attributes:
        enabled: Enable/disable observability (default: True)
        profiler_enabled: Enable profiler (default: True)
        tracing_enabled: Enable distributed tracing (default: True)
        metrics_enabled: Enable metrics collection (default: True)
        dashboard_enabled: Enable dashboard (default: True)
        runtime_dir: Directory for runtime data (profiles, traces)
        profiler_dir: Directory for profiler logs
        traces_dir: Directory for trace files
        sample_rate: Sampling rate for traces (0.0-1.0, default: 1.0)
    """
    enabled: bool = True
    profiler_enabled: bool = True
    tracing_enabled: bool = True
    metrics_enabled: bool = True
    dashboard_enabled: bool = True
    
    runtime_dir: Path = field(default_factory=lambda: Path("runtime"))
    profiler_dir: Path = field(default_factory=lambda: Path("runtime/profiler"))
    traces_dir: Path = field(default_factory=lambda: Path("runtime/traces"))
    
    sample_rate: float = 1.0  # 100% sampling by default
    
    def __post_init__(self):
        """Ensure directories exist."""
        if self.enabled:
            self.profiler_dir.mkdir(parents=True, exist_ok=True)
            self.traces_dir.mkdir(parents=True, exist_ok=True)


def get_observability_config() -> ObservabilityConfig:
    """
    Get observability configuration from environment or defaults.
    
    Environment Variables:
        MAHOUN_OBSERVABILITY_ENABLED: Enable/disable (default: True)
        MAHOUN_PROFILER_ENABLED: Enable profiler (default: True)
        MAHOUN_TRACING_ENABLED: Enable tracing (default: True)
        MAHOUN_METRICS_ENABLED: Enable metrics (default: True)
        MAHOUN_DASHBOARD_ENABLED: Enable dashboard (default: True)
        MAHOUN_RUNTIME_DIR: Runtime directory (default: runtime)
        MAHOUN_SAMPLE_RATE: Sampling rate 0.0-1.0 (default: 1.0)
    
    Returns:
        ObservabilityConfig instance
    """
    enabled = os.getenv("MAHOUN_OBSERVABILITY_ENABLED", "true").lower() == "true"
    
    if not enabled:
        return ObservabilityConfig(enabled=False)
    
    return ObservabilityConfig(
        enabled=True,
        profiler_enabled=os.getenv("MAHOUN_PROFILER_ENABLED", "true").lower() == "true",
        tracing_enabled=os.getenv("MAHOUN_TRACING_ENABLED", "true").lower() == "true",
        metrics_enabled=os.getenv("MAHOUN_METRICS_ENABLED", "true").lower() == "true",
        dashboard_enabled=os.getenv("MAHOUN_DASHBOARD_ENABLED", "true").lower() == "true",
        runtime_dir=Path(os.getenv("MAHOUN_RUNTIME_DIR", "runtime")),
        sample_rate=float(os.getenv("MAHOUN_SAMPLE_RATE", "1.0"))
    )

