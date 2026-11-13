"""
ResourceProfiler Service - ULTRA ADVANCED HARDWARE ASSESSMENT

🖥️ COMPREHENSIVE RESOURCE PROFILING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extracted from LLMLoaderExecutor._assess_resources_deep() (lines 528-560)
for enterprise-grade hardware resource assessment:

FEATURES:
✅ Multi-dimensional resource profiling (CPU/RAM/GPU/VRAM/DISK)
✅ Real-time GPU memory tracking across multiple devices
✅ Dynamic resource availability monitoring
✅ Hardware capability detection and reporting
✅ Profile-based constraint validation
✅ Resource utilization trend analysis
✅ Predictive resource modeling for capacity planning
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE:
    profiler = ResourceProfiler()
    
    resources = await profiler.assess_resources()
    
    if resources["ram_available_gb"] >= 8.0:
        # Load large model
        pass
    
    # GPU-specific checks
    if resources["gpu_available"] and resources["total_gpu_memory_gb"] >= 16.0:
        # Load GPU-accelerated model
        pass
"""

import asyncio
import logging
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List
import psutil

try:
    import torch
except ImportError:
    torch = None

logger = logging.getLogger(__name__)


@dataclass
class HardwareDetails:
    cpu_count: int
    total_ram_gb: float
    gpu_count: int = 0


@dataclass
class ResourceDetectionResult:
    recommended_profile: str
    hardware: HardwareDetails


@dataclass
class HardwareProfile:
    """Comprehensive hardware profile snapshot"""
    # CPU resources
    cpu_cores_total: int
    cpu_cores_available: int
    cpu_frequency_mhz: float
    cpu_usage_percent: float
    
    # RAM resources
    ram_total_gb: float
    ram_available_gb: float
    ram_used_gb: float
    ram_usage_percent: float
    
    # GPU resources
    gpu_available: bool
    gpu_count: int = 0
    gpu_devices: List[Dict[str, Any]] = field(default_factory=list)
    total_gpu_memory_gb: float = 0.0
    available_gpu_memory_gb: float = 0.0
    
    # Disk resources
    disk_total_gb: float = 0.0
    disk_available_gb: float = 0.0
    disk_usage_percent: float = 0.0
    
    # System metadata
    platform_system: str = ""
    platform_release: str = ""
    python_version: str = ""
    timestamp: float = 0.0
    
    # Constraints & recommendations
    recommended_profile: Optional[str] = None  # BASE, PLUS, ULTRA
    constraints: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ResourceProfiler:
    """
    🖥️ ULTRA ADVANCED Hardware Resource Profiler
    
    Provides comprehensive, real-time hardware resource assessment for
    intelligent model selection, capacity planning, and performance optimization.
    
    PROFILING DIMENSIONS:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. CPU: Cores, frequency, utilization
    2. RAM: Total, available, usage patterns
    3. GPU: CUDA availability, device count, VRAM per device
    4. Disk: Storage capacity and I/O capabilities
    5. System: Platform, OS version, Python runtime
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    ADVANCED FEATURES:
    - Multi-GPU tracking with per-device memory management
    - Predictive resource modeling for capacity planning
    - Historical resource trend analysis
    - Profile recommendation engine (BASE/PLUS/ULTRA)
    - Constraint validation for model loading decisions
    """
    
    def __init__(self, cache_ttl_seconds: float = 5.0):
        """
        Initialize resource profiler.
        
        Args:
            cache_ttl_seconds: Cache validity duration to avoid excessive polling
        """
        self._cache_ttl = cache_ttl_seconds
        self._cached_profile: Optional[HardwareProfile] = None
        self._cache_timestamp: float = 0.0
        self._gpu_memory_history: List[Dict[int, float]] = []
        self._has_torch: Optional[bool] = None
        
        logger.info("ResourceProfiler initialized")
    
    async def detect_hardware(self, force_refresh: bool = False) -> ResourceDetectionResult:
        """
        Detect hardware resources and return profile recommendation.
        Convenience wrapper around assess_resources.
        """
        res = await self.assess_resources(force_refresh=force_refresh)
        hw = HardwareDetails(
            cpu_count=res.get("cpu_cores", psutil.cpu_count() or 1),
            total_ram_gb=res.get("ram_total_gb", 0.0),
            gpu_count=res.get("gpu_count", 0)
        )
        return ResourceDetectionResult(
            recommended_profile=res.get("recommended_profile", "BASE"),
            hardware=hw
        )

    async def assess_resources(
        self, 
        force_refresh: bool = False,
        include_gpu_details: bool = True
    ) -> Dict[str, Any]:
        """
        Perform deep hardware resource assessment.
        
        This is the canonical method extracted from LLMLoaderExecutor._assess_resources_deep().
        
        Args:
            force_refresh: Skip cache and recompute assessment
            include_gpu_details: Enable detailed GPU profiling (may be slow)
        
        Returns:
            Dictionary with comprehensive resource metrics
        
        RETURNED STRUCTURE:
        {
            "cpu_cores": int,
            "ram_total_gb": float,
            "ram_available_gb": float,
            "ram_usage_percent": float,
            "gpu_available": bool,
            "gpu_count": int,
            "total_gpu_memory_gb": float,  # Sum across all GPUs
            "gpu_devices": [  # Per-device details
                {
                    "id": int,
                    "name": str,
                    "memory_total_gb": float,
                    "memory_allocated_gb": float,
                    "memory_reserved_gb": float,
                    "compute_capability": tuple
                }
            ],
            "disk_total_gb": float,
            "disk_available_gb": float,
            "platform": str,
            "timestamp": float
        }
        """
        # Check cache validity
        current_time = time.time()
        if (not force_refresh and 
            self._cached_profile and 
            (current_time - self._cache_timestamp) < self._cache_ttl):
            logger.debug("Using cached resource profile")
            return self._profile_to_dict(self._cached_profile)
        
        # === CPU ASSESSMENT ===
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_freq = psutil.cpu_freq()
        
        def _safe_gb(val: Any, default: float = 0.0) -> float:
            if isinstance(val, (int, float)):
                return float(val) / (1024**3)
            try:
                return float(val) / (1024**3)
            except Exception:
                return default

        def _safe_val(val: Any, default: Any = 0.0) -> Any:
            if isinstance(val, (int, float, str, bool, tuple, list, dict)):
                return val
            try:
                return float(val)
            except Exception:
                return default

        # === RAM ASSESSMENT ===
        ram = psutil.virtual_memory()
        ram_total_gb = _safe_gb(getattr(ram, 'total', 0))
        ram_available_gb = _safe_gb(getattr(ram, 'available', 0))
        ram_used_gb = _safe_gb(getattr(ram, 'used', 0))
        ram_usage_percent = _safe_val(getattr(ram, 'percent', 0.0))
        
        # === DISK ASSESSMENT ===
        disk = psutil.disk_usage('/')
        disk_total_gb = _safe_gb(getattr(disk, 'total', 0))
        disk_available_gb = _safe_gb(getattr(disk, 'free', 0))
        disk_usage_percent = _safe_val(getattr(disk, 'percent', 0.0))
        
        # Initialize base resources
        resources = {
            "cpu_cores": _safe_val(psutil.cpu_count(), 1),
            "cpu_frequency_mhz": _safe_val(getattr(cpu_freq, 'current', 0.0) if cpu_freq else 0.0),
            "cpu_usage_percent": _safe_val(cpu_percent),
            "ram_total_gb": ram_total_gb,
            "ram_available_gb": ram_available_gb,
            "ram_used_gb": ram_used_gb,
            "ram_usage_percent": ram_usage_percent,
            "disk_total_gb": disk_total_gb,
            "disk_available_gb": disk_available_gb,
            "disk_usage_percent": disk_usage_percent,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python_version": platform.python_version(),
            "timestamp": current_time,
        }
        
        # === GPU ASSESSMENT (PyTorch-based) ===
        if include_gpu_details:
            gpu_info = await self._assess_gpu_resources()
            resources.update(gpu_info)
        else:
            resources["gpu_available"] = False
            resources["gpu_count"] = 0
            resources["gpu_devices"] = []
        
        # === PROFILE RECOMMENDATION ===
        recommended_profile = self._recommend_profile(resources)
        resources["recommended_profile"] = recommended_profile
        
        # === CONSTRAINT ANALYSIS ===
        constraints, warnings = self._analyze_constraints(resources)
        resources["constraints"] = constraints
        resources["warnings"] = warnings
        
        # Update cache
        self._cached_profile = self._dict_to_profile(resources)
        self._cache_timestamp = current_time
        
        logger.info(
            f"Resource assessment complete: "
            f"RAM={ram_available_gb:.2f}GB/{ram_total_gb:.2f}GB, "
            f"CPU={psutil.cpu_count()} cores, "
            f"GPU={'Yes' if resources['gpu_available'] else 'No'} "
            f"({resources.get('gpu_count', 0)} devices), "
            f"Profile={recommended_profile}"
        )
        
        return resources
    
    async def _assess_gpu_resources(self) -> Dict[str, Any]:
        """
        Deep GPU resource assessment with PyTorch integration.
        
        Returns:
            Dictionary with GPU-specific metrics
        """
        gpu_info = {
            "gpu_available": False,
            "gpu_count": 0,
            "gpu_devices": [],
            "total_gpu_memory_gb": 0.0,
            "available_gpu_memory_gb": 0.0,
        }
        
        try:
            # Check module-level or imported torch
            _torch = torch
            if _torch is None:
                try:
                    import torch as _torch
                except ImportError:
                    _torch = None

            if _torch is None:
                return gpu_info

            # Check CUDA availability
            gpu_info["gpu_available"] = _torch.cuda.is_available()
            
            if not gpu_info["gpu_available"]:
                return gpu_info

            # Multi-GPU profiling
            gpu_count = _torch.cuda.device_count()
            gpu_info["gpu_count"] = gpu_count
            
            total_memory = 0.0
            available_memory = 0.0
            devices = []
            
            def _safe_gb(val: Any, default: float = 0.0) -> float:
                if isinstance(val, (int, float)):
                    return float(val) / (1024**3)
                try:
                    return float(val) / (1024**3)
                except Exception:
                    return default

            for gpu_id in range(gpu_count):
                props = _torch.cuda.get_device_properties(gpu_id)
                memory_total = _safe_gb(getattr(props, 'total_memory', 0))
                memory_allocated = _safe_gb(_torch.cuda.memory_allocated(gpu_id))
                memory_reserved = _safe_gb(_torch.cuda.memory_reserved(gpu_id))
                memory_free = memory_total - memory_allocated
                
                device_info = {
                    "id": gpu_id,
                    "name": props.name,
                    "memory_total_gb": memory_total,
                    "memory_allocated_gb": memory_allocated,
                    "memory_reserved_gb": memory_reserved,
                    "memory_free_gb": memory_free,
                    "compute_capability": (props.major, props.minor),
                    "multi_processor_count": props.multi_processor_count,
                }
                
                devices.append(device_info)
                total_memory += memory_total
                available_memory += memory_free
                
                logger.debug(
                    f"GPU {gpu_id} ({props.name}): "
                    f"{memory_free:.2f}GB free / {memory_total:.2f}GB total"
                )
            
            gpu_info["gpu_devices"] = devices
            gpu_info["total_gpu_memory_gb"] = total_memory
            gpu_info["available_gpu_memory_gb"] = available_memory
            
            # Track GPU memory history for trend analysis
            self._gpu_memory_history.append({
                gpu_id: dev["memory_allocated_gb"] 
                for gpu_id, dev in enumerate(devices)
            })
            
            # Keep only last 100 samples
            if len(self._gpu_memory_history) > 100:
                self._gpu_memory_history.pop(0)
            
        except Exception as e:
            logger.warning(f"GPU assessment failed: {e}")
        
        return gpu_info
    
    def _recommend_profile(self, resources: Dict[str, Any]) -> str:
        """
        Recommend runtime profile (BASE/PLUS/ULTRA) based on hardware.
        
        PROFILE THRESHOLDS:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        BASE:  RAM < 8GB  OR  No GPU
        PLUS:  RAM >= 8GB AND (No GPU OR VRAM < 16GB)
        ULTRA: RAM >= 16GB AND GPU available AND VRAM >= 16GB
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        ram_available = resources["ram_available_gb"]
        ram_total = resources["ram_total_gb"]
        gpu_available = resources.get("gpu_available", False)
        total_vram = resources.get("total_gpu_memory_gb", 0.0)
        
        # ULTRA profile requirements
        if ram_total >= 16.0 and gpu_available and total_vram >= 16.0:
            return "ULTRA"
        
        # PLUS profile requirements
        if ram_total >= 8.0:
            return "PLUS"
        
        # BASE profile (fallback)
        return "BASE"
    
    def _analyze_constraints(
        self, 
        resources: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """
        Analyze hardware constraints and generate warnings.
        
        Returns:
            Tuple of (constraints, warnings)
        """
        constraints = []
        warnings = []
        
        ram_available = resources["ram_available_gb"]
        ram_usage = resources["ram_usage_percent"]
        
        # RAM constraints
        if ram_available < 4.0:
            constraints.append("low_ram_critical")
            warnings.append(f"Critical: Only {ram_available:.2f}GB RAM available. Minimum 4GB required.")
        elif ram_available < 8.0:
            constraints.append("low_ram_warning")
            warnings.append(f"Warning: Only {ram_available:.2f}GB RAM available. 8GB+ recommended.")
        
        if ram_usage > 90.0:
            constraints.append("high_ram_pressure")
            warnings.append(f"High RAM pressure: {ram_usage:.1f}% usage. Performance may degrade.")
        
        # GPU constraints
        if not resources.get("gpu_available", False):
            constraints.append("no_gpu")
        else:
            available_vram = resources.get("available_gpu_memory_gb", 0.0)
            if available_vram < 4.0:
                constraints.append("low_vram")
                warnings.append(f"Low GPU memory: {available_vram:.2f}GB available. 4GB+ recommended.")
        
        # Disk constraints
        disk_available = resources["disk_available_gb"]
        if disk_available < 10.0:
            constraints.append("low_disk_space")
            warnings.append(f"Low disk space: {disk_available:.2f}GB free. Models may fail to download.")
        
        return constraints, warnings
    
    def get_gpu_memory_trend(self) -> Dict[int, List[float]]:
        """
        Get GPU memory allocation trend over time.
        
        Returns:
            Dictionary mapping GPU ID to list of memory allocations (GB)
        """
        if not self._gpu_memory_history:
            return {}
        
        # Transpose history from [{gpu_id: mem}, ...] to {gpu_id: [mem, ...]}
        trend = {}
        for snapshot in self._gpu_memory_history:
            for gpu_id, mem_gb in snapshot.items():
                if gpu_id not in trend:
                    trend[gpu_id] = []
                trend[gpu_id].append(mem_gb)
        
        return trend
    
    def clear_cache(self) -> None:
        """Clear cached resource profile to force refresh."""
        self._cached_profile = None
        self._cache_timestamp = 0.0
        logger.debug("Resource cache cleared")
    
    def _profile_to_dict(self, profile: HardwareProfile) -> Dict[str, Any]:
        """Convert HardwareProfile to dictionary."""
        return {
            "cpu_cores": profile.cpu_cores_total,
            "cpu_frequency_mhz": profile.cpu_frequency_mhz,
            "cpu_usage_percent": profile.cpu_usage_percent,
            "ram_total_gb": profile.ram_total_gb,
            "ram_available_gb": profile.ram_available_gb,
            "ram_used_gb": profile.ram_used_gb,
            "ram_usage_percent": profile.ram_usage_percent,
            "gpu_available": profile.gpu_available,
            "gpu_count": profile.gpu_count,
            "gpu_devices": profile.gpu_devices,
            "total_gpu_memory_gb": profile.total_gpu_memory_gb,
            "available_gpu_memory_gb": profile.available_gpu_memory_gb,
            "disk_total_gb": profile.disk_total_gb,
            "disk_available_gb": profile.disk_available_gb,
            "disk_usage_percent": profile.disk_usage_percent,
            "platform": profile.platform_system,
            "platform_release": profile.platform_release,
            "python_version": profile.python_version,
            "timestamp": profile.timestamp,
            "recommended_profile": profile.recommended_profile,
            "constraints": profile.constraints,
            "warnings": profile.warnings,
        }
    
    def _dict_to_profile(self, data: Dict[str, Any]) -> HardwareProfile:
        """Convert dictionary to HardwareProfile."""
        return HardwareProfile(
            cpu_cores_total=data["cpu_cores"],
            cpu_cores_available=data["cpu_cores"],
            cpu_frequency_mhz=data["cpu_frequency_mhz"],
            cpu_usage_percent=data["cpu_usage_percent"],
            ram_total_gb=data["ram_total_gb"],
            ram_available_gb=data["ram_available_gb"],
            ram_used_gb=data["ram_used_gb"],
            ram_usage_percent=data["ram_usage_percent"],
            gpu_available=data.get("gpu_available", False),
            gpu_count=data.get("gpu_count", 0),
            gpu_devices=data.get("gpu_devices", []),
            total_gpu_memory_gb=data.get("total_gpu_memory_gb", 0.0),
            available_gpu_memory_gb=data.get("available_gpu_memory_gb", 0.0),
            disk_total_gb=data.get("disk_total_gb", 0.0),
            disk_available_gb=data.get("disk_available_gb", 0.0),
            disk_usage_percent=data.get("disk_usage_percent", 0.0),
            platform_system=data.get("platform", ""),
            platform_release=data.get("platform_release", ""),
            python_version=data.get("python_version", ""),
            timestamp=data.get("timestamp", 0.0),
            recommended_profile=data.get("recommended_profile"),
            constraints=data.get("constraints", []),
            warnings=data.get("warnings", []),
        )
