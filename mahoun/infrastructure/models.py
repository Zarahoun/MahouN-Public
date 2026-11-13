#!/usr/bin/env python3
"""
Deployment Profile Data Model - G-0 FREEZE CANDIDATE

This module defines deployment profiles that ensure the same codebase
can operate across different resource environments (Desktop Minimal vs
Enterprise Full) with environment-driven configuration.

CRITICAL: This data model MUST be frozen before first GGUF integration
to ensure consistent deployment semantics across all environments.

Version: 1.0.0-rc1 (Release Candidate - Pre-G-0)
Freeze Status: PENDING (Must freeze before Task A.2 implementation)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import os


class ProfileType(Enum):
    """Supported deployment profile types"""

    DESKTOP_MINIMAL = "desktop_minimal"
    ENTERPRISE_FULL = "enterprise_full"
    CUSTOM = "custom"


class ResourceUnit(Enum):
    """Units for resource measurements"""

    BYTES = "bytes"
    MEGABYTES = "MB"
    GIGABYTES = "GB"
    COUNT = "count"
    PERCENT = "percent"


@dataclass(frozen=True)
class ResourceLimits:
    """
    Resource limits configuration

    G-0 FREEZE CANDIDATE: This structure must remain stable
    """

    max_memory_gb: float  # Maximum RAM usage
    max_cpu_cores: int  # Maximum CPU cores
    max_concurrent_requests: int  # Maximum concurrent requests
    max_model_size_gb: float  # Maximum model file size
    max_context_window: int  # Maximum token context window
    max_graph_nodes: int  # Maximum knowledge graph nodes
    max_storage_gb: float  # Maximum storage usage

    # GPU Settings
    enable_gpu: bool = False  # Whether to use GPU acceleration
    max_gpu_memory_gb: Optional[float] = None  # Maximum GPU memory

    # Network Settings
    enable_network: bool = False  # Whether network access allowed
    max_network_bandwidth_mbps: Optional[float] = None  # Network bandwidth limit

    def __post_init__(self):
        """Validation for resource limits"""
        if self.max_memory_gb <= 0:
            raise ValueError("max_memory_gb must be positive")
        if self.max_cpu_cores <= 0:
            raise ValueError("max_cpu_cores must be positive")
        if self.max_concurrent_requests <= 0:
            raise ValueError("max_concurrent_requests must be positive")
        if self.max_model_size_gb <= 0:
            raise ValueError("max_model_size_gb must be positive")
        if self.max_context_window <= 0:
            raise ValueError("max_context_window must be positive")
        if self.max_graph_nodes <= 0:
            raise ValueError("max_graph_nodes must be positive")
        if self.max_storage_gb <= 0:
            raise ValueError("max_storage_gb must be positive")

        # GPU validation
        if self.enable_gpu and self.max_gpu_memory_gb is not None:
            if self.max_gpu_memory_gb <= 0:
                raise ValueError("max_gpu_memory_gb must be positive")

        # Network validation
        if self.enable_network and self.max_network_bandwidth_mbps is not None:
            if self.max_network_bandwidth_mbps <= 0:
                raise ValueError("max_network_bandwidth_mbps must be positive")

    def to_dict(self) -> Dict[str, Any]:
        """Convert limits to dictionary format"""
        return {
            "max_memory_gb": self.max_memory_gb,
            "max_cpu_cores": self.max_cpu_cores,
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_model_size_gb": self.max_model_size_gb,
            "max_context_window": self.max_context_window,
            "max_graph_nodes": self.max_graph_nodes,
            "max_storage_gb": self.max_storage_gb,
            "enable_gpu": self.enable_gpu,
            "max_gpu_memory_gb": self.max_gpu_memory_gb,
            "enable_network": self.enable_network,
            "max_network_bandwidth_mbps": self.max_network_bandwidth_mbps,
        }


@dataclass(frozen=True)
class PerformanceTargets:
    """
    Performance targets for deployment profile

    G-0 FREEZE CANDIDATE: This structure must remain stable
    """

    target_latency_ms: float  # Target response latency
    target_throughput_rps: float  # Target requests per second
    min_availability_percent: float  # Minimum availability target

    # Quality Targets
    min_confidence_score: float = 0.7  # Minimum AI confidence
    min_agreement_score: float = 0.85  # Minimum symbolic/neural agreement

    def __post_init__(self):
        """Validation for performance targets"""
        if self.target_latency_ms <= 0:
            raise ValueError("target_latency_ms must be positive")
        if self.target_throughput_rps <= 0:
            raise ValueError("target_throughput_rps must be positive")
        if not (0.0 <= self.min_availability_percent <= 100.0):
            raise ValueError("min_availability_percent must be 0-100")
        if not (0.0 <= self.min_confidence_score <= 1.0):
            raise ValueError("min_confidence_score must be 0.0-1.0")
        if not (0.0 <= self.min_agreement_score <= 1.0):
            raise ValueError("min_agreement_score must be 0.0-1.0")


@dataclass(frozen=True)
class DeploymentProfile:
    """
    Deployment Profile - G-0 FREEZE CANDIDATE

    This is the canonical deployment profile format that enables
    the same MAHOUN codebase to operate across different resource
    environments with environment-driven configuration.

    Design Principles:
    1. Single Codebase: Same code deploys to all profiles
    2. Environment-Driven: Profile selected via environment variables
    3. Resource-Aware: Enforces limits appropriate for environment
    4. Semantic Equivalence: Same reasoning quality across profiles
    5. Graceful Degradation: Adapts to resource constraints

    Contract Guarantees:
    - Semantic equivalence preserved across profiles
    - Resource limits enforced at runtime
    - Same API contracts regardless of profile
    - Performance targets matched to profile capabilities
    - Air-gap compliance maintained in all profiles
    """

    # Profile Identity
    profile_name: str  # Unique profile name
    profile_type: ProfileType  # Profile type
    profile_version: str  # Semantic version

    # Resource Configuration
    resource_limits: ResourceLimits  # Hard resource limits
    performance_targets: PerformanceTargets  # Performance expectations

    # Feature Flags
    enable_advanced_reasoning: bool = True  # Advanced reasoning features
    enable_graph_analytics: bool = True  # Graph analytics features
    enable_rag: bool = True  # RAG system features
    enable_monitoring: bool = True  # Monitoring and metrics

    # Model Configuration
    recommended_model_sizes: List[str] = field(default_factory=list)  # Recommended models
    max_embedding_dimensions: int = 384  # Maximum embedding dimensions

    # Metadata
    description: Optional[str] = None
    target_environment: Optional[str] = None  # "laptop", "workstation", "server", etc.
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """
        Comprehensive validation for deployment profiles
        """
        # Core field validation
        if not self.profile_name:
            raise ValueError("profile_name cannot be empty")
        if not self.profile_version:
            raise ValueError("profile_version cannot be empty")

        # Embedding dimensions validation
        if self.max_embedding_dimensions <= 0:
            raise ValueError("max_embedding_dimensions must be positive")

    def validate_model_compatibility(
        self, model_size_gb: float, model_memory_gb: float, model_context_window: int
    ) -> bool:
        """
        Check if model is compatible with this profile

        Args:
            model_size_gb: Model file size in GB
            model_memory_gb: Model memory requirements in GB
            model_context_window: Model context window size

        Returns:
            True if model is compatible with profile constraints
        """
        return (
            model_size_gb <= self.resource_limits.max_model_size_gb
            and model_memory_gb <= self.resource_limits.max_memory_gb
            and model_context_window <= self.resource_limits.max_context_window
        )

    def get_optimal_model_size(self, available_models: List[str]) -> Optional[str]:
        """
        Select optimal model size for this profile

        Args:
            available_models: List of available model identifiers

        Returns:
            Recommended model identifier or None
        """
        # Filter to recommended sizes
        compatible = [m for m in available_models if any(rec in m for rec in self.recommended_model_sizes)]

        if not compatible:
            return None

        # Return largest compatible model
        return compatible[-1] if compatible else None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert profile to dictionary for serialization

        Returns:
            Dictionary representation of profile
        """
        return {
            "profile_name": self.profile_name,
            "profile_type": self.profile_type.value,
            "profile_version": self.profile_version,
            "resource_limits": self.resource_limits.to_dict(),
            "performance_targets": {
                "target_latency_ms": self.performance_targets.target_latency_ms,
                "target_throughput_rps": self.performance_targets.target_throughput_rps,
                "min_availability_percent": self.performance_targets.min_availability_percent,
                "min_confidence_score": self.performance_targets.min_confidence_score,
                "min_agreement_score": self.performance_targets.min_agreement_score,
            },
            "enable_advanced_reasoning": self.enable_advanced_reasoning,
            "enable_graph_analytics": self.enable_graph_analytics,
            "enable_rag": self.enable_rag,
            "enable_monitoring": self.enable_monitoring,
            "recommended_model_sizes": self.recommended_model_sizes,
            "max_embedding_dimensions": self.max_embedding_dimensions,
            "description": self.description,
            "target_environment": self.target_environment,
            "metadata": self.metadata,
        }


# Standard Profile Definitions

DESKTOP_MINIMAL = DeploymentProfile(
    profile_name="desktop_minimal",
    profile_type=ProfileType.DESKTOP_MINIMAL,
    profile_version="1.0.0",
    resource_limits=ResourceLimits(
        max_memory_gb=4.0,
        max_cpu_cores=4,
        max_concurrent_requests=10,
        max_model_size_gb=4.0,
        max_context_window=4096,
        max_graph_nodes=100_000,
        max_storage_gb=50.0,
        enable_gpu=False,
        enable_network=False,  # Air-gap compliant
    ),
    performance_targets=PerformanceTargets(
        target_latency_ms=5000.0,  # 5 second target
        target_throughput_rps=2.0,  # 2 requests/second
        min_availability_percent=95.0,
        min_confidence_score=0.7,
        min_agreement_score=0.85,
    ),
    enable_advanced_reasoning=True,
    enable_graph_analytics=False,  # Disabled for resource constraints
    enable_rag=True,
    enable_monitoring=True,
    recommended_model_sizes=["1B", "3B"],  # 1-3B parameter models
    max_embedding_dimensions=384,  # bge-small dimensions
    description="Minimal desktop deployment for personal laptops and workstations",
    target_environment="laptop",
)


ENTERPRISE_FULL = DeploymentProfile(
    profile_name="enterprise_full",
    profile_type=ProfileType.ENTERPRISE_FULL,
    profile_version="1.0.0",
    resource_limits=ResourceLimits(
        max_memory_gb=32.0,
        max_cpu_cores=16,
        max_concurrent_requests=1000,
        max_model_size_gb=32.0,
        max_context_window=32768,
        max_graph_nodes=100_000_000,
        max_storage_gb=500.0,
        enable_gpu=True,
        max_gpu_memory_gb=24.0,
        enable_network=False,  # Still air-gap compliant
    ),
    performance_targets=PerformanceTargets(
        target_latency_ms=2000.0,  # 2 second target
        target_throughput_rps=100.0,  # 100 requests/second
        min_availability_percent=99.9,
        min_confidence_score=0.7,
        min_agreement_score=0.85,
    ),
    enable_advanced_reasoning=True,
    enable_graph_analytics=True,
    enable_rag=True,
    enable_monitoring=True,
    recommended_model_sizes=["7B", "13B", "32B", "70B"],  # Support large models
    max_embedding_dimensions=768,  # bge-base or larger
    description="Full enterprise deployment for dedicated servers and clusters",
    target_environment="server",
)


# Profile Management Functions


def load_profile_from_env() -> DeploymentProfile:
    """
    Load deployment profile based on environment variables

    Environment Variables:
        MAHOUN_DEPLOYMENT_PROFILE: Profile name ("desktop_minimal" | "enterprise_full")
        MAHOUN_PROFILE_OVERRIDE_*: Override specific settings

    Returns:
        Deployment profile instance
    """
    profile_name = os.getenv("MAHOUN_DEPLOYMENT_PROFILE", "desktop_minimal").lower()

    if profile_name == "desktop_minimal":
        return DESKTOP_MINIMAL
    elif profile_name == "enterprise_full":
        return ENTERPRISE_FULL
    else:
        raise ValueError(f"Unknown deployment profile: {profile_name}")


def validate_profile_compatibility(
    profile: DeploymentProfile, required_memory_gb: float, required_cpu_cores: int, required_model_size_gb: float
) -> bool:
    """
    Validate that requirements are compatible with profile

    Args:
        profile: Deployment profile to validate against
        required_memory_gb: Required memory in GB
        required_cpu_cores: Required CPU cores
        required_model_size_gb: Required model size in GB

    Returns:
        True if requirements are compatible
    """
    return (
        required_memory_gb <= profile.resource_limits.max_memory_gb
        and required_cpu_cores <= profile.resource_limits.max_cpu_cores
        and required_model_size_gb <= profile.resource_limits.max_model_size_gb
    )


def create_custom_profile(
    profile_name: str, resource_limits: ResourceLimits, performance_targets: PerformanceTargets, **kwargs
) -> DeploymentProfile:
    """
    Create custom deployment profile

    Args:
        profile_name: Unique profile name
        resource_limits: Resource limit configuration
        performance_targets: Performance target configuration
        **kwargs: Additional profile parameters

    Returns:
        Custom deployment profile
    """
    return DeploymentProfile(
        profile_name=profile_name,
        profile_type=ProfileType.CUSTOM,
        profile_version="1.0.0",
        resource_limits=resource_limits,
        performance_targets=performance_targets,
        **kwargs,
    )
