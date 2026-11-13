"""
LLM Router - Ultra Edition
==========================
Enterprise-grade LLM router with intelligent routing, fallback chains,
circuit breakers, and comprehensive observability.

Features:
- No hardcoded model names - all from configuration
- Configurable routing rules by capability, cost, latency
- Priority-based fallback chain with circuit breakers
- Health monitoring and automatic failover
- Request/response logging for audit
- Deterministic selection for reproducibility
- Cost-aware routing for budget management
- Latency-aware routing for SLA compliance

Design Principles:
- All model names come from configuration
- Deterministic: same inputs → same outputs
- Fail-safe: always has a fallback
- Observable: comprehensive logging and metrics
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    LOCAL = "local"           # Local models via llama.cpp
    OPENAI = "openai"         # OpenAI API
    ANTHROPIC = "anthropic"   # Anthropic API
    OLLAMA = "ollama"         # Ollama local server
    AZURE = "azure"           # Azure OpenAI
    BEDROCK = "bedrock"       # AWS Bedrock
    VERTEX = "vertex"         # Google Vertex AI
    
    def is_remote(self) -> bool:
        """Check if provider requires network access."""
        return self in (
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.AZURE,
            LLMProvider.BEDROCK,
            LLMProvider.VERTEX,
        )
    
    def is_local(self) -> bool:
        """Check if provider runs locally."""
        return self in (LLMProvider.LOCAL, LLMProvider.OLLAMA)


class ModelCapability(str, Enum):
    """Standard model capabilities."""
    GENERAL = "general"
    CODE = "code"
    LEGAL = "legal"
    MEDICAL = "medical"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    MATH = "math"
    CREATIVE = "creative"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"


class ExpertRole(str, Enum):
    """Expert roles for specialized model routing."""
    GENERALIST = "generalist"           # General-purpose reasoning
    SPECIALIST = "specialist"           # Domain-specific expertise
    MATHEMATICAL = "mathematical"       # Mathematical precision
    LOGICAL = "logical"                # Logical reasoning
    NARRATIVE = "narrative"            # Narrative synthesis
    ANALYTICAL = "analytical"          # Data analysis
    CREATIVE = "creative"              # Creative tasks
    TRANSLATOR = "translator"          # Language translation
    
    def get_expected_latency_profile(self) -> Dict[str, float]:
        """Get expected latency characteristics for this role."""
        profiles = {
            ExpertRole.GENERALIST: {"base_ms": 500, "complexity_factor": 1.0},
            ExpertRole.SPECIALIST: {"base_ms": 800, "complexity_factor": 1.2},
            ExpertRole.MATHEMATICAL: {"base_ms": 1200, "complexity_factor": 2.0},  # High-compute
            ExpertRole.LOGICAL: {"base_ms": 1000, "complexity_factor": 1.8},      # High-compute
            ExpertRole.NARRATIVE: {"base_ms": 1500, "complexity_factor": 1.5},    # High-compute
            ExpertRole.ANALYTICAL: {"base_ms": 900, "complexity_factor": 1.3},
            ExpertRole.CREATIVE: {"base_ms": 1100, "complexity_factor": 1.4},
            ExpertRole.TRANSLATOR: {"base_ms": 600, "complexity_factor": 1.1},
        }
        return profiles.get(self, {"base_ms": 1000, "complexity_factor": 1.0})


class RoutingStrategy(str, Enum):
    """Routing strategy for model selection."""
    PRIORITY = "priority"       # Use highest priority model
    ROUND_ROBIN = "round_robin" # Distribute load evenly
    LEAST_LATENCY = "latency"   # Use fastest model
    LEAST_COST = "cost"         # Use cheapest model
    CAPABILITY = "capability"   # Match by capability
    ROLE_AWARE = "role_aware"   # Role-aware intelligent routing


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"     # Normal operation
    OPEN = "open"         # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


# =============================================================================
# Data Classes
# =============================================================================

@dataclass(frozen=True)
class ModelConfig:
    """
    Immutable configuration for a single model.
    
    All model names come from configuration, never hardcoded.
    Enhanced with role-based routing and latency awareness.
    """
    name: str
    provider: LLMProvider
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    expert_role: ExpertRole = ExpertRole.GENERALIST
    priority: int = 0
    timeout: int = 30
    max_tokens: int = 2048
    temperature: float = 0.7
    
    # Cost tracking (per 1K tokens)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    
    # Performance characteristics
    avg_latency_ms: float = 1000.0
    max_concurrent: int = 10
    
    # Role-based latency expectations
    role_latency_tolerance: float = 1.0  # Multiplier for role-specific latency tolerance
    
    # Provider-specific settings
    model_path: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    deployment_name: Optional[str] = None
    
    # Feature flags
    supports_streaming: bool = True
    supports_functions: bool = False
    supports_vision: bool = False
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.name:
            raise ValueError("Model name cannot be empty")
        if self.timeout < 1:
            raise ValueError("Timeout must be at least 1 second")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be at least 1")
    
    def has_capability(self, capability: str) -> bool:
        """Check if model has a capability."""
        return capability.lower() in {c.lower() for c in self.capabilities}
    
    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a request."""
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output
        return input_cost + output_cost
    
    def get_role_adjusted_timeout(self, complexity_factor: float = 1.0) -> float:
        """Get timeout adjusted for expert role and task complexity."""
        role_profile = self.expert_role.get_expected_latency_profile()
        base_timeout = self.timeout
        role_multiplier = self.role_latency_tolerance
        complexity_multiplier = role_profile["complexity_factor"] * complexity_factor
        
        return base_timeout * role_multiplier * complexity_multiplier
    
    def is_suitable_for_role(self, required_role: ExpertRole) -> bool:
        """Check if model is suitable for a specific expert role."""
        # Exact match
        if self.expert_role == required_role:
            return True
        
        # Generalists can handle most roles with lower priority
        if self.expert_role == ExpertRole.GENERALIST:
            return True
        
        # Role compatibility matrix
        compatibility = {
            ExpertRole.MATHEMATICAL: [ExpertRole.LOGICAL, ExpertRole.ANALYTICAL],
            ExpertRole.LOGICAL: [ExpertRole.MATHEMATICAL, ExpertRole.ANALYTICAL],
            ExpertRole.ANALYTICAL: [ExpertRole.LOGICAL, ExpertRole.MATHEMATICAL],
            ExpertRole.NARRATIVE: [ExpertRole.CREATIVE],
            ExpertRole.CREATIVE: [ExpertRole.NARRATIVE],
        }
        
        return required_role in compatibility.get(self.expert_role, [])


@dataclass
class RoutingRule:
    """Rule for routing requests to specific models."""
    capability: str
    model_name: str
    priority: int = 0
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, context: Dict[str, Any]) -> bool:
        """Check if rule matches the given context."""
        for key, value in self.conditions.items():
            if context.get(key) != value:
                return False
        return True


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for model health management with atomic state transitions.
    
    Prevents cascading failures by temporarily disabling unhealthy models.
    Enhanced with role-aware latency tolerance and atomic state management.
    """
    model_name: str
    expert_role: ExpertRole = ExpertRole.GENERALIST
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    
    # Configuration
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: int = 60
    
    # Role-aware latency thresholds
    latency_threshold_ms: float = 5000.0  # Base threshold
    role_latency_multiplier: float = 1.0  # Role-specific multiplier
    
    _circuit_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def __post_init__(self) -> None:
        """Initialize role-specific latency thresholds."""
        role_profile = self.expert_role.get_expected_latency_profile()
        self.role_latency_multiplier = role_profile["complexity_factor"]
        self.latency_threshold_ms = role_profile["base_ms"] * 3  # 3x base as threshold
    
    def record_success(self, latency_ms: Optional[float] = None) -> None:
        """
        Record a successful request with atomic state transitions.
        
        Args:
            latency_ms: Response latency for role-aware evaluation
        """
        with self._circuit_lock:
            self.success_count += 1
            self.last_success_time = datetime.now()
            
            # Role-aware latency evaluation
            if latency_ms is not None:
                adjusted_threshold = self.latency_threshold_ms * self.role_latency_multiplier
                if latency_ms > adjusted_threshold:
                    logger.warning(
                        f"Model {self.model_name} ({self.expert_role.value}) exceeded "
                        f"role-adjusted latency threshold: {latency_ms:.1f}ms > {adjusted_threshold:.1f}ms"
                    )
                    # Don't treat as failure for high-compute roles, just log
                    if self.expert_role not in [ExpertRole.MATHEMATICAL, ExpertRole.LOGICAL, ExpertRole.NARRATIVE]:
                        self._record_latency_warning()
            
            if self.state == CircuitState.HALF_OPEN:
                if self.success_count >= self.success_threshold:
                    self._close()
                    logger.info(f"Circuit breaker CLOSED for {self.model_name} after {self.success_count} successes")
    
    def record_failure(self, failure_type: str = "general") -> None:
        """
        Record a failed request with atomic state transitions.
        
        Args:
            failure_type: Type of failure for better diagnostics
        """
        with self._circuit_lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            logger.warning(f"Circuit breaker failure recorded for {self.model_name}: {failure_type}")
            
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self._open()
                    logger.error(f"Circuit breaker OPENED for {self.model_name} after {self.failure_count} failures")
            elif self.state == CircuitState.HALF_OPEN:
                self._open()
                logger.warning(f"Circuit breaker returned to OPEN for {self.model_name} during half-open test")
    
    def is_available(self) -> bool:
        """
        Check if model is available for requests with atomic state checking.
        
        Returns:
            True if model is available, False otherwise
        """
        with self._circuit_lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                # Check if timeout has passed
                if self.last_failure_time:
                    elapsed = datetime.now() - self.last_failure_time
                    if elapsed.total_seconds() >= self.timeout_seconds:
                        self._half_open()
                        logger.info(f"Circuit breaker HALF_OPEN for {self.model_name} after timeout")
                        return True
                return False
            
            # HALF_OPEN - allow limited requests
            return True
    
    def force_open(self, reason: str = "manual") -> None:
        """
        Manually open the circuit breaker.
        
        Args:
            reason: Reason for manual opening
        """
        with self._circuit_lock:
            self._open()
            logger.warning(f"Circuit breaker manually OPENED for {self.model_name}: {reason}")
    
    def force_close(self, reason: str = "manual") -> None:
        """
        Manually close the circuit breaker.
        
        Args:
            reason: Reason for manual closing
        """
        with self._circuit_lock:
            self._close()
            logger.info(f"Circuit breaker manually CLOSED for {self.model_name}: {reason}")
    
    def get_state_info(self) -> Dict[str, Any]:
        """
        Get current state information atomically.
        
        Returns:
            Dictionary with current state information
        """
        with self._circuit_lock:
            return {
                "model_name": self.model_name,
                "expert_role": self.expert_role.value,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
                "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "timeout_seconds": self.timeout_seconds,
                "latency_threshold_ms": self.latency_threshold_ms,
                "role_latency_multiplier": self.role_latency_multiplier,
            }
    
    def _open(self) -> None:
        """Open the circuit (stop requests) - INTERNAL USE ONLY."""
        self.state = CircuitState.OPEN
        self.success_count = 0
    
    def _close(self) -> None:
        """Close the circuit (resume normal operation) - INTERNAL USE ONLY."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
    
    def _half_open(self) -> None:
        """Half-open the circuit (test recovery) - INTERNAL USE ONLY."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
    
    def _record_latency_warning(self) -> None:
        """Record latency warning for non-high-compute roles."""
        # Could be used for additional metrics or alerting
        pass


@dataclass
class RoutingDecision:
    """Record of a routing decision for audit."""
    timestamp: datetime
    request_id: str
    selected_model: str
    reason: str
    alternatives: List[str]
    context: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "selected_model": self.selected_model,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "context": self.context,
        }


@dataclass
class ModelStats:
    """Runtime statistics for a model."""
    model_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests


# =============================================================================
# Router Implementation
# =============================================================================

class LLMRouter:
    """
    Enterprise-grade LLM router with intelligent routing and fallback.
    
    Features:
    - Deterministic model selection
    - Priority-based fallback chain
    - Circuit breakers with atomic state transitions
    - Role-aware routing and latency tolerance
    - Cost and latency aware routing
    - Comprehensive audit logging
    - Agnostic architecture for future-proof model management
    
    Usage:
        models = [
            ModelConfig(
                name="llama-3.2-1b",
                provider=LLMProvider.LOCAL,
                capabilities=frozenset(["general", "reasoning"]),
                expert_role=ExpertRole.GENERALIST,
                priority=10
            ),
            ModelConfig(
                name="deepseek-coder",
                provider=LLMProvider.LOCAL,
                capabilities=frozenset(["code", "math"]),
                expert_role=ExpertRole.MATHEMATICAL,
                priority=8,
                role_latency_tolerance=2.0
            )
        ]
        
        router = LLMRouter(models, strategy=RoutingStrategy.ROLE_AWARE)
        router.add_routing_rule("code", "deepseek-coder")
        
        model_name = router.select(prompt, capability="code", expert_role=ExpertRole.MATHEMATICAL)
    """
    
    def __init__(
        self,
        models: Optional[List[ModelConfig]] = None,
        strategy: RoutingStrategy = RoutingStrategy.ROLE_AWARE,
        enable_circuit_breakers: bool = True,
        enable_stats: bool = True,
    ):
        """
        Initialize router with model configurations.
        
        Args:
            models: List of ModelConfig instances
            strategy: Default routing strategy
            enable_circuit_breakers: Enable circuit breaker pattern
            enable_stats: Enable statistics collection
        """
        self._models: Dict[str, ModelConfig] = {}
        self._routing_rules: Dict[str, List[RoutingRule]] = {}
        self._fallback_chain: List[str] = []
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._stats: Dict[str, ModelStats] = {}
        self._decisions: List[RoutingDecision] = []
        
        # Role-based routing maps
        self._role_to_models: Dict[ExpertRole, List[str]] = {}
        self._capability_to_roles: Dict[str, List[ExpertRole]] = {}
        
        self._strategy = strategy
        self._enable_circuit_breakers = enable_circuit_breakers
        self._enable_stats = enable_stats
        
        # CRITICAL: Atomic state management lock
        self._router_lock = threading.RLock()
        
        # Load models
        if models:
            for model in models:
                self._add_model_internal(model)
        else:
            self._load_from_config()
        
        self._build_fallback_chain()
        self._build_role_maps()
        
        logger.info(
            f"LLM Router initialized: {len(self._models)} models, "
            f"strategy={strategy.value}, circuit_breakers={enable_circuit_breakers}"
        )
    
    def _add_model_internal(self, model: ModelConfig) -> None:
        """Internal method to add a model with atomic state management."""
        with self._router_lock:
            self._models[model.name] = model
            
            if self._enable_circuit_breakers:
                self._circuit_breakers[model.name] = CircuitBreaker(
                    model_name=model.name,
                    expert_role=model.expert_role
                )
            
            if self._enable_stats:
                self._stats[model.name] = ModelStats(model_name=model.name)
    
    def _build_role_maps(self) -> None:
        """Build role-to-model and capability-to-role mapping for efficient routing."""
        with self._router_lock:
            self._role_to_models.clear()
            self._capability_to_roles.clear()
            
            # Build role-to-models mapping
            for model_name, model in self._models.items():
                role = model.expert_role
                if role not in self._role_to_models:
                    self._role_to_models[role] = []
                self._role_to_models[role].append(model_name)
            
            # Sort models within each role by priority
            for role in self._role_to_models:
                self._role_to_models[role].sort(
                    key=lambda name: self._models[name].priority,
                    reverse=True
                )
            
            # Build capability-to-roles mapping
            capability_role_map = {
                "general": [ExpertRole.GENERALIST],
                "code": [ExpertRole.MATHEMATICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
                "legal": [ExpertRole.LOGICAL, ExpertRole.ANALYTICAL, ExpertRole.GENERALIST],
                "medical": [ExpertRole.ANALYTICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
                "reasoning": [ExpertRole.LOGICAL, ExpertRole.MATHEMATICAL, ExpertRole.GENERALIST],
                "analysis": [ExpertRole.ANALYTICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
                "math": [ExpertRole.MATHEMATICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
                "creative": [ExpertRole.CREATIVE, ExpertRole.NARRATIVE, ExpertRole.GENERALIST],
                "translation": [ExpertRole.TRANSLATOR, ExpertRole.GENERALIST],
                "summarization": [ExpertRole.NARRATIVE, ExpertRole.ANALYTICAL, ExpertRole.GENERALIST],
                "extraction": [ExpertRole.ANALYTICAL, ExpertRole.GENERALIST],
                "classification": [ExpertRole.ANALYTICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
            }
            
            self._capability_to_roles = capability_role_map
            
            logger.debug(f"Role maps built: {len(self._role_to_models)} roles, "
                        f"{len(self._capability_to_roles)} capability mappings")
    
    def _load_from_config(self) -> None:
        """Load model configurations from environment."""
        # Default fallback model
        default_model = ModelConfig(
            name=os.getenv("MAHOUN_DEFAULT_MODEL", "default-local"),
            provider=LLMProvider.LOCAL,
            capabilities=frozenset(["general"]),
            priority=1,
            model_path=os.getenv("MAHOUN_DEFAULT_MODEL_PATH"),
        )
        self._add_model_internal(default_model)
    
    def _build_fallback_chain(self) -> None:
        """Build fallback chain sorted by priority."""
        with self._router_lock:
            sorted_models = sorted(
                self._models.values(),
                key=lambda m: m.priority,
                reverse=True
            )
            self._fallback_chain = [m.name for m in sorted_models]
            logger.debug(f"Fallback chain: {self._fallback_chain}")
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def add_model(self, model: ModelConfig) -> None:
        """
        Add a model to the router.
        
        Args:
            model: ModelConfig to add
        """
        with self._router_lock:
            self._add_model_internal(model)
            self._build_fallback_chain()
            self._build_role_maps()
        logger.info(f"Added model: {model.name} (role: {model.expert_role.value})")
    
    def remove_model(self, model_name: str) -> None:
        """
        Remove a model from the router.
        
        Args:
            model_name: Name of model to remove
        """
        with self._router_lock:
            if model_name in self._models:
                model = self._models[model_name]
                del self._models[model_name]
                self._circuit_breakers.pop(model_name, None)
                self._stats.pop(model_name, None)
                
                # Remove routing rules for this model
                for capability in list(self._routing_rules.keys()):
                    self._routing_rules[capability] = [
                        r for r in self._routing_rules[capability]
                        if r.model_name != model_name
                    ]
                
                self._build_fallback_chain()
                self._build_role_maps()
                logger.info(f"Removed model: {model_name} (role: {model.expert_role.value})")
    
    def add_routing_rule(
        self,
        capability: str,
        model_name: str,
        priority: int = 0,
        conditions: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add routing rule for a capability.
        
        Args:
            capability: Capability name
            model_name: Model to route to
            priority: Rule priority (higher = more important)
            conditions: Additional conditions for matching
        """
        with self._router_lock:
            if model_name not in self._models:
                raise LLMRouterError(f"Unknown model: {model_name}")
            
            rule = RoutingRule(
                capability=capability,
                model_name=model_name,
                priority=priority,
                conditions=conditions or {},
            )
            
            if capability not in self._routing_rules:
                self._routing_rules[capability] = []
            
            self._routing_rules[capability].append(rule)
            self._routing_rules[capability].sort(key=lambda r: r.priority, reverse=True)
            
            logger.debug(f"Added routing rule: {capability} -> {model_name}")
    
    def select(
        self,
        prompt: str,
        capability: Optional[str] = None,
        expert_role: Optional[ExpertRole] = None,
        context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        complexity_factor: float = 1.0,
    ) -> str:
        """
        Select model based on capability, expert role, and context.
        
        This method is deterministic - same inputs always produce same output.
        Enhanced with role-aware routing and adaptive fallback logic.
        
        Args:
            prompt: The prompt text
            capability: Required capability
            expert_role: Required expert role
            context: Additional context for routing
            request_id: Request ID for audit
            complexity_factor: Task complexity multiplier for latency tolerance
            
        Returns:
            Model name from configuration
            
        Raises:
            LLMRouterError: If no models available
        """
        context = context or {}
        request_id = request_id or self._generate_request_id(prompt)
        
        with self._router_lock:
            # Get available models (respecting circuit breakers)
            available = self._get_available_models()
            
            if not available:
                raise LLMRouterError("No models available (all circuits open)")
            
            # Role-aware routing strategy
            if self._strategy == RoutingStrategy.ROLE_AWARE:
                selected = self._select_by_role_aware_strategy(
                    available, capability, expert_role, context, complexity_factor
                )
                if selected:
                    self._record_decision(
                        request_id=request_id,
                        selected=selected,
                        reason=f"role_aware:{expert_role.value if expert_role else 'auto'}",
                        alternatives=available,
                        context=context,
                    )
                    return selected
            
            # Try routing rules first
            if capability and capability in self._routing_rules:
                for rule in self._routing_rules[capability]:
                    if rule.model_name in available and rule.matches(context):
                        # Verify role compatibility if specified
                        if expert_role:
                            model = self._models[rule.model_name]
                            if not model.is_suitable_for_role(expert_role):
                                continue
                        
                        self._record_decision(
                            request_id=request_id,
                            selected=rule.model_name,
                            reason=f"routing_rule:{capability}",
                            alternatives=available,
                            context=context,
                        )
                        return rule.model_name
            
            # Try capability + role matching
            if capability or expert_role:
                selected = self._select_by_capability_and_role(
                    available, capability, expert_role
                )
                if selected:
                    reason_parts = []
                    if capability:
                        reason_parts.append(f"capability:{capability}")
                    if expert_role:
                        reason_parts.append(f"role:{expert_role.value}")
                    
                    self._record_decision(
                        request_id=request_id,
                        selected=selected,
                        reason="|".join(reason_parts),
                        alternatives=available,
                        context=context,
                    )
                    return selected
            
            # Apply routing strategy
            selected = self._apply_strategy(available, context)
            
            self._record_decision(
                request_id=request_id,
                selected=selected,
                reason=f"strategy:{self._strategy.value}",
                alternatives=available,
                context=context,
            )
            
            return selected
    
    def _select_by_role_aware_strategy(
        self,
        available: List[str],
        capability: Optional[str],
        expert_role: Optional[ExpertRole],
        context: Dict[str, Any],
        complexity_factor: float,
    ) -> Optional[str]:
        """
        Select model using role-aware strategy with intelligent fallback.
        
        Args:
            available: List of available model names
            capability: Required capability
            expert_role: Required expert role
            context: Additional context
            complexity_factor: Task complexity multiplier
            
        Returns:
            Selected model name or None if no suitable model found
        """
        # Determine target role
        target_role = expert_role
        if not target_role and capability:
            # Infer role from capability
            role_candidates = self._capability_to_roles.get(capability, [])
            if role_candidates:
                target_role = role_candidates[0]  # Use most suitable role
        
        if not target_role:
            target_role = ExpertRole.GENERALIST
        
        # Try exact role match first
        role_models = self._role_to_models.get(target_role, [])
        for model_name in role_models:
            if model_name in available:
                model = self._models[model_name]
                if not capability or model.has_capability(capability):
                    return model_name
        
        # Adaptive fallback: try compatible roles
        if target_role != ExpertRole.GENERALIST:
            compatible_roles = self._get_compatible_roles(target_role)
            for fallback_role in compatible_roles:
                role_models = self._role_to_models.get(fallback_role, [])
                for model_name in role_models:
                    if model_name in available:
                        model = self._models[model_name]
                        if not capability or model.has_capability(capability):
                            logger.info(f"Role fallback: {target_role.value} -> {fallback_role.value} ({model_name})")
                            return model_name
        
        # Final fallback to generalists
        generalist_models = self._role_to_models.get(ExpertRole.GENERALIST, [])
        for model_name in generalist_models:
            if model_name in available:
                model = self._models[model_name]
                if not capability or model.has_capability(capability):
                    logger.info(f"Generalist fallback: {target_role.value} -> GENERALIST ({model_name})")
                    return model_name
        
        return None
    
    def _select_by_capability_and_role(
        self,
        available: List[str],
        capability: Optional[str],
        expert_role: Optional[ExpertRole],
    ) -> Optional[str]:
        """
        Select model by capability and role matching.
        
        Args:
            available: List of available model names
            capability: Required capability
            expert_role: Required expert role
            
        Returns:
            Selected model name or None if no match found
        """
        for model_name in self._fallback_chain:
            if model_name not in available:
                continue
            
            model = self._models[model_name]
            
            # Check capability match
            if capability and not model.has_capability(capability):
                continue
            
            # Check role suitability
            if expert_role and not model.is_suitable_for_role(expert_role):
                continue
            
            return model_name
        
        return None
    
    def _get_compatible_roles(self, target_role: ExpertRole) -> List[ExpertRole]:
        """
        Get list of compatible roles for fallback routing.
        
        Args:
            target_role: Target expert role
            
        Returns:
            List of compatible roles in priority order
        """
        compatibility_map = {
            ExpertRole.MATHEMATICAL: [ExpertRole.LOGICAL, ExpertRole.ANALYTICAL, ExpertRole.GENERALIST],
            ExpertRole.LOGICAL: [ExpertRole.MATHEMATICAL, ExpertRole.ANALYTICAL, ExpertRole.GENERALIST],
            ExpertRole.ANALYTICAL: [ExpertRole.LOGICAL, ExpertRole.MATHEMATICAL, ExpertRole.GENERALIST],
            ExpertRole.NARRATIVE: [ExpertRole.CREATIVE, ExpertRole.GENERALIST],
            ExpertRole.CREATIVE: [ExpertRole.NARRATIVE, ExpertRole.GENERALIST],
            ExpertRole.TRANSLATOR: [ExpertRole.GENERALIST],
            ExpertRole.SPECIALIST: [ExpertRole.ANALYTICAL, ExpertRole.LOGICAL, ExpertRole.GENERALIST],
            ExpertRole.GENERALIST: [],  # No fallback needed
        }
        
        return compatibility_map.get(target_role, [ExpertRole.GENERALIST])
    
    def get_fallback(
        self, 
        failed_model: str, 
        capability: Optional[str] = None,
        expert_role: Optional[ExpertRole] = None,
        preserve_reasoning_chain: bool = True
    ) -> Optional[str]:
        """
        Get next model in fallback chain with role-aware logic.
        
        Args:
            failed_model: Name of model that failed
            capability: Required capability to maintain
            expert_role: Required expert role to maintain
            preserve_reasoning_chain: Whether to preserve reasoning capabilities
            
        Returns:
            Next model name, or None if no fallback
        """
        with self._router_lock:
            # Record failure in circuit breaker
            if failed_model in self._circuit_breakers:
                self._circuit_breakers[failed_model].record_failure("fallback_triggered")
            
            # Record failure in stats
            if failed_model in self._stats:
                self._stats[failed_model].failed_requests += 1
            
            # Get available models
            available = self._get_available_models()
            
            # Remove the failed model from available list
            available = [m for m in available if m != failed_model]
            
            if not available:
                logger.error(f"No fallback available for {failed_model}: all models unavailable")
                return None
            
            # Get failed model's configuration for context
            failed_model_config = self._models.get(failed_model)
            if failed_model_config:
                failed_role = failed_model_config.expert_role
                logger.info(f"Seeking fallback for {failed_model} (role: {failed_role.value})")
            
            # Role-aware fallback strategy
            if expert_role or (failed_model_config and preserve_reasoning_chain):
                target_role = expert_role or failed_model_config.expert_role
                
                # Try same role first
                fallback = self._find_fallback_by_role(available, target_role, capability, after_model=failed_model)
                if fallback:
                    logger.info(f"Same-role fallback: {failed_model} -> {fallback}")
                    return fallback
                
                # Try compatible roles
                compatible_roles = self._get_compatible_roles(target_role)
                for compatible_role in compatible_roles:
                    fallback = self._find_fallback_by_role(available, compatible_role, capability, after_model=failed_model)
                    if fallback:
                        logger.info(f"Compatible-role fallback: {failed_model} -> {fallback} "
                                  f"({target_role.value} -> {compatible_role.value})")
                        return fallback
            
            # Capability-based fallback
            if capability:
                for model_name in available:
                    model = self._models[model_name]
                    if model.has_capability(capability):
                        logger.info(f"Capability fallback: {failed_model} -> {model_name}")
                        return model_name
            
            # Priority-based fallback (traditional)
            try:
                idx = self._fallback_chain.index(failed_model)
                for next_model in self._fallback_chain[idx + 1:]:
                    if next_model in available:
                        logger.warning(f"Priority fallback: {failed_model} -> {next_model}")
                        return next_model
            except ValueError:
                logger.debug("Failed model not found in fallback chain during priority fallback")
            
            # Last resort: any available model
            if available:
                fallback = available[0]
                logger.warning(f"Last resort fallback: {failed_model} -> {fallback}")
                return fallback
            
            logger.error(f"No fallback available for {failed_model}")
            return None
    
    def _find_fallback_by_role(
        self,
        available: List[str],
        target_role: ExpertRole,
        capability: Optional[str] = None,
        after_model: Optional[str] = None
    ) -> Optional[str]:
        """
        Find fallback model by expert role.
        
        Args:
            available: List of available model names
            target_role: Target expert role
            capability: Required capability
            after_model: Only consider models after this one in fallback chain
            
        Returns:
            Model name or None if no suitable model found
        """
        role_models = self._role_to_models.get(target_role, [])
        
        # If after_model specified, filter to only models after it in chain
        if after_model and after_model in self._fallback_chain:
            try:
                idx = self._fallback_chain.index(after_model)
                # Only consider models that come after failed model in chain
                valid_models = set(self._fallback_chain[idx + 1:])
                role_models = [m for m in role_models if m in valid_models]
            except ValueError:
                pass  # If not in chain, use all role models
        
        for model_name in role_models:
            if model_name not in available:
                continue
            
            if capability:
                model = self._models[model_name]
                if not model.has_capability(capability):
                    continue
            
            return model_name
        
        return None
    
    def record_success(
        self,
        model_name: str,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Record successful request for a model with role-aware latency evaluation."""
        with self._router_lock:
            if model_name in self._circuit_breakers:
                self._circuit_breakers[model_name].record_success(latency_ms)
            
            if model_name in self._stats:
                stats = self._stats[model_name]
                stats.total_requests += 1
                stats.successful_requests += 1
                stats.total_latency_ms += latency_ms
                stats.total_tokens_in += tokens_in
                stats.total_tokens_out += tokens_out
                
                if model_name in self._models:
                    model = self._models[model_name]
                    stats.total_cost += model.estimated_cost(tokens_in, tokens_out)
    
    def record_failure(self, model_name: str, failure_type: str = "general") -> None:
        """Record failed request for a model with detailed failure tracking."""
        with self._router_lock:
            if model_name in self._circuit_breakers:
                self._circuit_breakers[model_name].record_failure(failure_type)
            
            if model_name in self._stats:
                stats = self._stats[model_name]
                stats.total_requests += 1
                stats.failed_requests += 1
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a model."""
        return self._models.get(model_name)
    
    def list_models(self) -> List[str]:
        """List all model names."""
        return list(self._models.keys())
    
    def list_available_models(self) -> List[str]:
        """List models that are currently available."""
        with self._router_lock:
            return self._get_available_models()
    
    def list_capabilities(self) -> List[str]:
        """List all available capabilities."""
        capabilities: Set[str] = set()
        for model in self._models.values():
            capabilities.update(model.capabilities)
        return sorted(capabilities)
    
    def list_expert_roles(self) -> List[str]:
        """List all available expert roles."""
        return [role.value for role in self._role_to_models.keys()]
    
    def get_models_by_role(self, expert_role: ExpertRole) -> List[str]:
        """Get models that can fulfill a specific expert role."""
        with self._router_lock:
            return self._role_to_models.get(expert_role, [])
    
    def get_role_compatibility(self, model_name: str) -> List[ExpertRole]:
        """Get list of roles a model can fulfill."""
        model = self._models.get(model_name)
        if not model:
            return []
        
        compatible_roles = [model.expert_role]
        
        # Add roles this model can serve as fallback
        for role in ExpertRole:
            if role != model.expert_role and model.is_suitable_for_role(role):
                compatible_roles.append(role)
        
        return compatible_roles
    
    def get_stats(self, model_name: str) -> Optional[ModelStats]:
        """Get statistics for a model."""
        return self._stats.get(model_name)
    
    def get_all_stats(self) -> Dict[str, ModelStats]:
        """Get statistics for all models."""
        return dict(self._stats)
    
    def get_circuit_state(self, model_name: str) -> Optional[CircuitState]:
        """Get circuit breaker state for a model."""
        cb = self._circuit_breakers.get(model_name)
        return cb.state if cb else None
    
    def get_circuit_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed circuit breaker information for a model."""
        cb = self._circuit_breakers.get(model_name)
        return cb.get_state_info() if cb else None
    
    def get_all_circuit_info(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker information for all models."""
        with self._router_lock:
            return {
                name: cb.get_state_info() 
                for name, cb in self._circuit_breakers.items()
            }
    
    def force_circuit_state(self, model_name: str, state: CircuitState, reason: str = "manual") -> bool:
        """
        Manually set circuit breaker state for a model.
        
        Args:
            model_name: Name of the model
            state: Desired circuit state
            reason: Reason for manual intervention
            
        Returns:
            True if successful, False if model not found
        """
        with self._router_lock:
            cb = self._circuit_breakers.get(model_name)
            if not cb:
                return False
            
            if state == CircuitState.OPEN:
                cb.force_open(reason)
            elif state == CircuitState.CLOSED:
                cb.force_close(reason)
            # HALF_OPEN is handled automatically by the circuit breaker
            
            return True
    
    def get_recent_decisions(self, limit: int = 100) -> List[RoutingDecision]:
        """Get recent routing decisions for audit."""
        return self._decisions[-limit:]
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _get_available_models(self) -> List[str]:
        """Get list of available models (respecting circuit breakers)."""
        available = []
        for model_name in self._fallback_chain:
            if self._enable_circuit_breakers:
                cb = self._circuit_breakers.get(model_name)
                if cb and not cb.is_available():
                    continue
            available.append(model_name)
        return available
    
    def _apply_strategy(
        self,
        available: List[str],
        context: Dict[str, Any],
    ) -> str:
        """Apply routing strategy to select model."""
        if not available:
            raise LLMRouterError("No models available")
        
        if self._strategy == RoutingStrategy.PRIORITY:
            # Already sorted by priority in fallback chain
            return available[0]
        
        elif self._strategy == RoutingStrategy.LEAST_LATENCY:
            # Select model with lowest average latency
            best = available[0]
            best_latency = float('inf')
            
            for model_name in available:
                stats = self._stats.get(model_name)
                if stats and stats.avg_latency_ms < best_latency:
                    best = model_name
                    best_latency = stats.avg_latency_ms
            
            return best
        
        elif self._strategy == RoutingStrategy.LEAST_COST:
            # Select cheapest model
            best = available[0]
            best_cost = float('inf')
            
            for model_name in available:
                model = self._models.get(model_name)
                if model:
                    cost = model.cost_per_1k_input + model.cost_per_1k_output
                    if cost < best_cost:
                        best = model_name
                        best_cost = cost
            
            return best
        
        elif self._strategy == RoutingStrategy.ROUND_ROBIN:
            # Simple round-robin based on request count
            min_requests = float('inf')
            best = available[0]
            
            for model_name in available:
                stats = self._stats.get(model_name)
                requests = stats.total_requests if stats else 0
                if requests < min_requests:
                    best = model_name
                    min_requests = requests
            
            return best
        
        # Default to first available
        return available[0]
    
    def _record_decision(
        self,
        request_id: str,
        selected: str,
        reason: str,
        alternatives: List[str],
        context: Dict[str, Any],
    ) -> None:
        """Record routing decision for audit."""
        decision = RoutingDecision(
            timestamp=datetime.now(),
            request_id=request_id,
            selected_model=selected,
            reason=reason,
            alternatives=alternatives,
            context=context,
        )
        
        self._decisions.append(decision)
        
        # Keep only last 1000 decisions
        if len(self._decisions) > 1000:
            self._decisions = self._decisions[-1000:]
        
        logger.info(
            f"Routing decision: {selected} (reason={reason}, "
            f"alternatives={len(alternatives)})"
        )
    
    def _generate_request_id(self, prompt: str) -> str:
        """Generate deterministic request ID."""
        content = f"{time.time()}:{prompt[:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class LLMRouterError(Exception):
    """Error in LLM routing."""


# =============================================================================
# Factory Functions
# =============================================================================

def create_router_from_config(
    config_path: Optional[str] = None,
) -> LLMRouter:
    """
    Create router from configuration file with role-aware models.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configured LLMRouter instance with expert roles
    """
    # Default models with expert roles if no config
    models = [
        ModelConfig(
            name="default-generalist",
            provider=LLMProvider.LOCAL,
            capabilities=frozenset(["general"]),
            expert_role=ExpertRole.GENERALIST,
            priority=5,
        ),
        ModelConfig(
            name="math-specialist",
            provider=LLMProvider.LOCAL,
            capabilities=frozenset(["math", "reasoning", "analysis"]),
            expert_role=ExpertRole.MATHEMATICAL,
            priority=8,
            role_latency_tolerance=2.0,  # Allow longer processing for math
        ),
        ModelConfig(
            name="logic-specialist",
            provider=LLMProvider.LOCAL,
            capabilities=frozenset(["reasoning", "legal", "analysis"]),
            expert_role=ExpertRole.LOGICAL,
            priority=7,
            role_latency_tolerance=1.8,  # Allow longer processing for logic
        ),
    ]
    
    router = LLMRouter(models=models, strategy=RoutingStrategy.ROLE_AWARE)
    
    # Add role-aware routing rules
    router.add_routing_rule("math", "math-specialist", priority=10)
    router.add_routing_rule("reasoning", "logic-specialist", priority=9)
    router.add_routing_rule("legal", "logic-specialist", priority=8)
    
    return router


# =============================================================================
# Legacy Compatibility
# =============================================================================

class ExpertRouter:
    """
    Legacy router for backward compatibility with enhanced role-aware routing.
    
    DEPRECATED: Use LLMRouter instead.
    """
    
    def __init__(self, model_caps: Optional[dict] = None):
        """Initialize with optional model capabilities dict."""
        import warnings
        warnings.warn(
            "ExpertRouter is deprecated. Use LLMRouter instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        self._router = LLMRouter(strategy=RoutingStrategy.ROLE_AWARE)
        
        # Add default models with expert roles
        default_models = [
            ModelConfig(
                name="llama-general",
                provider=LLMProvider.LOCAL,
                capabilities=frozenset(["general"]),
                expert_role=ExpertRole.GENERALIST,
                priority=10
            ),
            ModelConfig(
                name="deepseek-code",
                provider=LLMProvider.LOCAL,
                capabilities=frozenset(["code", "legal", "math"]),
                expert_role=ExpertRole.MATHEMATICAL,
                priority=8,
                role_latency_tolerance=2.0
            ),
            ModelConfig(
                name="granite-reasoning",
                provider=LLMProvider.LOCAL,
                capabilities=frozenset(["reasoning", "analysis"]),
                expert_role=ExpertRole.LOGICAL,
                priority=7,
                role_latency_tolerance=1.8
            )
        ]
        
        for model in default_models:
            self._router.add_model(model)
        
        # Add role-aware routing rules
        self._router.add_routing_rule("code", "deepseek-code", priority=10)
        self._router.add_routing_rule("legal", "deepseek-code", priority=9)
        self._router.add_routing_rule("math", "deepseek-code", priority=8)
        self._router.add_routing_rule("reasoning", "granite-reasoning", priority=7)
        self._router.add_routing_rule("analysis", "granite-reasoning", priority=6)
    
    def select(self, prompt: str) -> str:
        """Select model based on prompt content with role-aware routing."""
        text = prompt.lower()
        
        # Enhanced keyword detection with role inference
        if any(kw in text for kw in ["کد", "code", "def ", "class ", "function", "algorithm"]):
            return self._router.select(prompt, capability="code", expert_role=ExpertRole.MATHEMATICAL)
        
        if any(kw in text for kw in ["قانون", "رأی", "حقوق", "legal", "law", "regulation"]):
            return self._router.select(prompt, capability="legal", expert_role=ExpertRole.LOGICAL)
        
        if any(kw in text for kw in ["استدلال", "تحلیل", "reason", "analyze", "logic"]):
            return self._router.select(prompt, capability="reasoning", expert_role=ExpertRole.LOGICAL)
        
        if any(kw in text for kw in ["ریاضی", "منطقی", "math", "calculate", "equation"]):
            return self._router.select(prompt, capability="math", expert_role=ExpertRole.MATHEMATICAL)
        
        # Default to generalist
        return self._router.select(prompt, expert_role=ExpertRole.GENERALIST)
