"""
Uncertainty Estimation Module
============================

Advanced uncertainty quantification for legal AI.

Components:
- GaussianProcessUncertainty: Production-grade GP with true epistemic/aleatoric separation
- GPConfig: Configuration for GP models
- UncertaintyEstimate: Structured uncertainty output for legal context
"""

from typing import Any, Optional

# Primary Implementation (Internally V2)
from .gaussian_process import (
    GaussianProcessUncertainty,
    GPConfig,
    UncertaintyEstimate,
    CalibrationMetrics,
    KernelType,
    UncertaintyType,
)

# Alias for backward compatibility (Deprecated)
# TODO: Remove in next major version
GaussianProcessUncertaintyV2 = GaussianProcessUncertainty

__all__ = [
    "GaussianProcessUncertainty",
    "GaussianProcessUncertaintyV2",
    "GPConfig",
    "UncertaintyEstimate",
    "CalibrationMetrics",
    "KernelType",
    "UncertaintyType",
]
