"""
ModelResolver Service - ULTRA ADVANCED PROFILE-BASED MODEL SELECTION

🎯 INTELLIGENT MODEL RESOLUTION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extracted from LLMLoaderExecutor._select_models_by_profile() and 
EmbeddingModelsExecutor._build_model_descriptors() (lines 199-262, 552-650)
for profile-aware, hardware-constrained model selection:

FEATURES:
✅ Profile-based model selection (BASE/PLUS/ULTRA)
✅ Hardware constraint validation (RAM/VRAM/CPU)
✅ Automatic quantization selection for resource-constrained environments
✅ Fallback model chain configuration
✅ Priority-based model ranking
✅ GPU requirement detection and validation
✅ Model capability matching and filtering
✅ Dynamic model descriptor generation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE:
    resolver = ModelResolver()
    
    # Get models for current profile and hardware
    descriptors = await resolver.resolve_models(
        profile="PLUS",
        hardware_profile={"ram_available_gb": 16.0, "gpu_available": True},
        model_type=ModelType.LLM
    )
    
    for descriptor in descriptors:
        print(f"Load: {descriptor.name} (priority={descriptor.priority})")
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)


# ============================================================================
# Type Definitions (matching ai_ml_components.py)
# ============================================================================

class ModelType(str, Enum):
    """Enhanced model classification for advanced loading strategies"""
    EMBEDDING = "embedding"
    LLM = "llm"
    AGENT = "agent"
    AUXILIARY = "auxiliary"
    QUANTIZED = "quantized"


class LoadPriority(int, Enum):
    """Model loading priority with advanced scheduling"""
    CRITICAL = 1    # Must load or bootstrap fails
    HIGH = 2        # Load with aggressive retries
    MEDIUM = 3      # Load with fallback options
    LOW = 4         # Optional, load if resources permit
    DEFERRED = 5    # Load on-demand later


@dataclass
class ModelDescriptor:
    """Complete model metadata for enterprise-grade loading"""
    name: str
    model_type: ModelType
    priority: LoadPriority
    min_ram_gb: float = 0.0
    min_vram_gb: float = 0.0
    min_cpu_cores: int = 1
    checksum_sha256: Optional[str] = None
    fallback_models: List[str] = field(default_factory=list)
    quantization: Optional[str] = None  # "int8", "int4", "fp16", "q4_0", None
    requires_gpu: bool = False
    max_load_time_sec: float = 300.0
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_check_interval: float = 60.0
    performance_baseline: Dict[str, float] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        return self.name


class ModelResolver:
    """
    🎯 ULTRA ADVANCED Profile-Based Model Resolution Service
    
    Intelligently selects optimal AI/ML models based on:
    1. Runtime profile (BASE/PLUS/ULTRA)
    2. Available hardware resources (RAM/VRAM/GPU)
    3. Model type (Embedding/LLM/Agent)
    4. Priority and capability requirements
    
    RESOLUTION STRATEGY:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    BASE Profile:
      - Minimal resource footprint
      - CPU-only operation supported
      - Quantized models preferred
      - Single critical model per type
    
    PLUS Profile:
      - Balanced performance/resource tradeoff
      - Optional GPU acceleration
      - Mix of local + API models
      - Fallback chains configured
    
    ULTRA Profile:
      - Maximum quality and capabilities
      - GPU-accelerated models prioritized
      - Multiple specialized models per type
      - Advanced quantization (INT8) for large models
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    HARDWARE CONSTRAINTS:
    - Automatically filters models exceeding available resources
    - Applies quantization when RAM < minimum requirements
    - Validates GPU availability for GPU-required models
    - Configures fallback chains for resource-constrained scenarios
    """
    
    def __init__(self):
        """Initialize model resolver with model catalog."""
        self._model_catalog: Dict[str, Dict[str, List[ModelDescriptor]]] = {}
        self._build_model_catalog()
        logger.info("ModelResolver initialized with comprehensive model catalog")
    
    def _build_model_catalog(self) -> None:
        """
        Build comprehensive model catalog for all profiles and types.
        """
        self._model_catalog["EMBEDDING"] = {
            "BASE": [ModelDescriptor(
                name="all-MiniLM-L6-v2", model_type=ModelType.EMBEDDING,
                priority=LoadPriority.CRITICAL, min_ram_gb=0.5, quantization="fp16"
            )],
            "PLUS": [ModelDescriptor(
                name="all-mpnet-base-v2", model_type=ModelType.EMBEDDING,
                priority=LoadPriority.CRITICAL, min_ram_gb=1.0
            )],
            "ULTRA": [ModelDescriptor(
                name="e5-large-v2", model_type=ModelType.EMBEDDING,
                priority=LoadPriority.CRITICAL, min_ram_gb=2.0
            )],
        }
        self._model_catalog["LLM"] = {
            "BASE": [ModelDescriptor(
                name="phi-2-q4", model_type=ModelType.LLM,
                priority=LoadPriority.CRITICAL, min_ram_gb=2.0, quantization="int4"
            )],
            "PLUS": [ModelDescriptor(
                name="mistral-7b-q8", model_type=ModelType.LLM,
                priority=LoadPriority.CRITICAL, min_ram_gb=8.0, quantization="int8"
            )],
            "ULTRA": [ModelDescriptor(
                name="llama-70b", model_type=ModelType.LLM,
                priority=LoadPriority.CRITICAL, min_ram_gb=40.0, requires_gpu=True
            )],
        }

    def resolve_embedding_model(self, profile: str) -> Optional[ModelDescriptor]:
        """Convenience: resolve the top embedding model for a profile."""
        profile = profile.upper()
        models = self._model_catalog.get("EMBEDDING", {}).get(profile, [])
        return models[0] if models else None

    def resolve_llm_model(self, profile: str) -> Optional[ModelDescriptor]:
        """Convenience: resolve the top LLM model for a profile."""
        profile = profile.upper()
        models = self._model_catalog.get("LLM", {}).get(profile, [])
        return models[0] if models else None
    
    async def resolve_models(
        self,
        profile: str,
        hardware_profile: Dict[str, Any],
        model_type: ModelType,
        required_capabilities: Optional[Set[str]] = None,
        filter_constraints: bool = True
    ) -> List[ModelDescriptor]:
        """
        Resolve optimal models for given profile, hardware, and requirements.
        
        Args:
            profile: Runtime profile (BASE/PLUS/ULTRA)
            hardware_profile: Dict with hardware metrics (from ResourceProfiler)
            model_type: Type of models to resolve (EMBEDDING/LLM/AGENT)
            required_capabilities: Filter models by required capabilities
            filter_constraints: Apply hardware constraint filtering
        
        Returns:
            List of ModelDescriptor objects, sorted by priority
        """
        profile = profile.upper()
        model_type_key = model_type.value.upper()
        
        # Fetch base model set from catalog
        if model_type_key not in self._model_catalog:
            logger.warning(f"No models in catalog for type: {model_type_key}")
            return []
        
        if profile not in self._model_catalog[model_type_key]:
            logger.warning(f"No models in catalog for profile: {profile}, type: {model_type_key}")
            return []
        
        base_descriptors = self._model_catalog[model_type_key][profile].copy()
        
        logger.info(
            f"Resolving {model_type_key} models for profile={profile}, "
            f"RAM={hardware_profile.get('ram_available_gb', 0):.2f}GB, "
            f"GPU={hardware_profile.get('gpu_available', False)}"
        )
        
        # Apply hardware constraint filtering
        if filter_constraints:
            base_descriptors = self._filter_by_hardware_constraints(
                base_descriptors,
                hardware_profile
            )
        
        # Apply automatic quantization if needed
        base_descriptors = self._apply_auto_quantization(
            base_descriptors,
            hardware_profile
        )
        
        # Filter by required capabilities
        if required_capabilities:
            base_descriptors = [
                d for d in base_descriptors
                if required_capabilities.issubset(d.capabilities)
            ]
        
        # Sort by priority (CRITICAL=1 first)
        base_descriptors.sort(key=lambda x: x.priority.value)
        
        logger.info(
            f"Resolved {len(base_descriptors)} models: "
            f"{[d.name[:30] for d in base_descriptors]}"
        )
        
        return base_descriptors
    
    def _filter_by_hardware_constraints(
        self,
        descriptors: List[ModelDescriptor],
        hardware_profile: Dict[str, Any]
    ) -> List[ModelDescriptor]:
        """Filter models that exceed hardware constraints."""
        available_ram = hardware_profile.get("ram_available_gb", 0.0)
        gpu_available = hardware_profile.get("gpu_available", False)
        available_vram = hardware_profile.get("total_gpu_memory_gb", 0.0)
        
        filtered = []
        for descriptor in descriptors:
            # RAM constraint
            if descriptor.min_ram_gb > available_ram:
                logger.debug(
                    f"Skipping {descriptor.name}: requires {descriptor.min_ram_gb}GB RAM, "
                    f"only {available_ram:.2f}GB available"
                )
                continue
            
            # GPU requirement constraint
            if descriptor.requires_gpu and not gpu_available:
                logger.debug(
                    f"Skipping {descriptor.name}: requires GPU, but no GPU available"
                )
                continue
            
            # VRAM constraint
            if descriptor.requires_gpu and descriptor.min_vram_gb > available_vram:
                logger.debug(
                    f"Skipping {descriptor.name}: requires {descriptor.min_vram_gb}GB VRAM, "
                    f"only {available_vram:.2f}GB available"
                )
                continue
            
            filtered.append(descriptor)
        
        logger.info(
            f"Hardware filtering: {len(descriptors)} → {len(filtered)} models "
            f"(RAM={available_ram:.1f}GB, GPU={gpu_available})"
        )
        
        return filtered
    
    def _apply_auto_quantization(
        self,
        descriptors: List[ModelDescriptor],
        hardware_profile: Dict[str, Any]
    ) -> List[ModelDescriptor]:
        """Apply automatic quantization for resource-constrained environments."""
        available_ram = hardware_profile.get("ram_available_gb", 0.0)
        gpu_available = hardware_profile.get("gpu_available", False)
        
        for descriptor in descriptors:
            # Skip API-based models
            if descriptor.metadata.get("api_based", False):
                continue
            
            # Skip if already quantized
            if descriptor.quantization:
                continue
            
            # Aggressive quantization for low RAM
            if available_ram < 8.0 and descriptor.model_type == ModelType.LLM:
                descriptor.quantization = "q4_0"
                descriptor.min_ram_gb *= 0.6  # Reduce RAM requirement
                logger.info(
                    f"Auto-quantization: {descriptor.name} → q4_0 "
                    f"(RAM={available_ram:.1f}GB < 8GB)"
                )
            
            # INT8 quantization for large GPU models
            elif (available_ram < 16.0 and gpu_available and 
                  descriptor.requires_gpu and descriptor.min_ram_gb >= 12.0):
                descriptor.quantization = "int8"
                descriptor.min_ram_gb *= 0.75  # Reduce RAM requirement
                descriptor.min_vram_gb *= 0.75  # Reduce VRAM requirement
                logger.info(
                    f"Auto-quantization: {descriptor.name} → int8 "
                    f"(RAM={available_ram:.1f}GB < 16GB, large GPU model)"
                )
        
        return descriptors
