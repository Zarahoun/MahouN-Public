"""
Ultra Base Agent - Enterprise-Grade Agent Foundation
=====================================================
کلاس پایه فوق‌پیشرفته برای تمام Ultra Agents

Features:
- Circuit Breaker Pattern (جلوگیری از cascade failures)
- Retry with Exponential Backoff
- Structured Logging with Correlation ID
- Health Check Endpoint
- Graceful Degradation
- Async Context Manager
- State Machine for Agent Lifecycle
"""

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar
import contextlib
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ============================================================================
# Enums and Data Classes
# ============================================================================

class AgentState(str, Enum):
    """Agent lifecycle states"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    DEGRADED = "degraded"  # Working with reduced functionality
    FAILED = "failed"
    SHUTDOWN = "shutdown"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class AgentConfig:
    """Agent configuration with sensible defaults"""
    # Retry settings
    max_retries: int = 3
    retry_base_delay: float = 0.5  # seconds
    retry_max_delay: float = 30.0  # seconds
    retry_exponential_base: float = 2.0
    
    # Circuit breaker settings
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: float = 60.0  # seconds before half-open
    
    # Timeout settings
    operation_timeout: float = 30.0  # seconds
    initialization_timeout: float = 60.0  # seconds
    
    # Health check
    health_check_interval: float = 30.0  # seconds
    
    # Logging
    log_level: str = "INFO"
    enable_correlation_id: bool = True
    
    # Graceful degradation
    enable_fallback: bool = True
    fallback_timeout: float = 5.0  # seconds


@dataclass
class AgentResult(Generic[T]):
    """Standardized agent result"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    
    # Metadata
    correlation_id: Optional[str] = None
    processing_time_ms: float = 0.0
    retries_used: int = 0
    fallback_used: bool = False
    
    # Warnings (non-fatal issues)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "correlation_id": self.correlation_id,
            "processing_time_ms": self.processing_time_ms,
            "retries_used": self.retries_used,
            "fallback_used": self.fallback_used,
            "warnings": self.warnings,
        }


@dataclass
class CircuitBreaker:
    """Circuit breaker implementation"""
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    threshold: int = 5
    timeout: float = 60.0
    
    def record_success(self):
        """Record successful call"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
    
    def record_failure(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker moved to HALF_OPEN")
                    return True
            return False
        
        # HALF_OPEN: allow one request to test
        return True


# ============================================================================
# Ultra Base Agent
# ============================================================================

class UltraBaseAgent(ABC):
    """
    Enterprise-grade base agent with advanced patterns.
    
    Features:
    - Circuit Breaker: Prevents cascade failures
    - Retry with Backoff: Handles transient failures
    - Correlation ID: Tracks requests across services
    - Health Check: Monitors agent health
    - Graceful Degradation: Falls back when dependencies fail
    
    Usage:
        class MyAgent(UltraBaseAgent):
            async def _process_impl(self, input_data):
                # Your logic here
                return {"result": "..."}
        
        async with MyAgent("my_agent") as agent:
            result = await agent.process({"query": "..."})
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[AgentConfig] = None,
        parent_config: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.config = config or AgentConfig()
        self.parent_config = parent_config or {}
        
        # State management
        self._state = AgentState.CREATED
        self._initialized = False
        
        # Circuit breaker
        self._circuit_breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_threshold,
            timeout=self.config.circuit_breaker_timeout
        )
        
        # Metrics
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_retries": 0,
            "fallback_calls": 0,
            "total_processing_time_ms": 0.0,
            "last_call_time": None,
            "last_error": None,
        }
        
        # Logger with agent name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # Health check task
        self._health_task: Optional[asyncio.Task] = None
        self._closing: bool = False
        
        self.logger.info(f"UltraBaseAgent '{name}' created")
    
    # ========================================================================
    # Async Context Manager
    # ========================================================================
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()
        return False
    
    # ========================================================================
    # Lifecycle Methods
    # ========================================================================
    
    async def initialize(self) -> bool:
        """
        Initialize agent and dependencies.
        
        Override _initialize_impl() for custom initialization.
        """
        if self._initialized:
            return True
        
        self._state = AgentState.INITIALIZING
        self.logger.info(f"Initializing agent '{self.name}'...")
        
        try:
            # Run initialization with timeout
            await asyncio.wait_for(
                self._initialize_impl(),
                timeout=self.config.initialization_timeout
            )
            
            self._initialized = True
            self._state = AgentState.READY
            
            # Start lifecycle tasks
            self.start_background_tasks()
            
            self.logger.info(f"✅ Agent '{self.name}' initialized successfully")
            return True
            
        except asyncio.TimeoutError:
            self._state = AgentState.FAILED
            self.logger.error(f"Agent '{self.name}' initialization timed out")
            return False
        except Exception as e:
            self._state = AgentState.FAILED
            self.logger.error(f"Agent '{self.name}' initialization failed: {e}")
            return False
    
    async def close(self):
        """Idempotent shutdown; cancels and awaits background tasks."""
        if self._closing:
            return
        self._closing = True
        
        self.logger.info(f"Shutting down agent '{self.name}'...")
        
        # Cancel health check task
        task = self._health_task
        self._health_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        
        # Run custom shutdown
        try:
            await self._shutdown_impl()
        except Exception as e:
            self.logger.warning(f"Error during shutdown: {e}")
        
        self._state = AgentState.SHUTDOWN
        self._initialized = False
        self.logger.info(f"Agent '{self.name}' shut down")

    async def shutdown(self):
        """Graceful shutdown (Alias for close)"""
        await self.close()
    
    @abstractmethod
    async def _initialize_impl(self):
        """Override this for custom initialization"""
        pass
    
    async def _shutdown_impl(self):
        """Override this for custom shutdown (optional)"""
        pass
    
    # ========================================================================
    # Main Processing
    # ========================================================================
    
    async def process(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> AgentResult:
        """
        Process input with all enterprise patterns applied.
        
        Args:
            input_data: Input data dictionary
            correlation_id: Optional correlation ID for tracing
        
        Returns:
            AgentResult with success/failure and metadata
        """
        # Generate correlation ID if not provided
        if correlation_id is None and self.config.enable_correlation_id:
            correlation_id = str(uuid.uuid4())[:8]
        
        start_time = time.time()
        self._metrics["total_calls"] += 1
        self._metrics["last_call_time"] = datetime.now().isoformat()
        
        # Check circuit breaker
        if not self._circuit_breaker.can_execute():
            self.logger.warning(f"[{correlation_id}] Circuit breaker OPEN, rejecting request")
            return AgentResult(
                success=False,
                error="Circuit breaker open - service temporarily unavailable",
                error_type="CircuitBreakerOpen",
                correlation_id=correlation_id,
            )
        
        # Ensure initialized
        if not self._initialized:
            if not await self.initialize():
                return AgentResult(
                    success=False,
                    error="Agent initialization failed",
                    error_type="InitializationError",
                    correlation_id=correlation_id,
                )
        
        self._state = AgentState.PROCESSING
        retries_used = 0
        last_error: Optional[Any] = None
        # Retry loop with exponential backoff
        for attempt in range(self.config.max_retries + 1):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._process_impl(input_data, correlation_id),
                    timeout=self.config.operation_timeout
                )
                
                # Success
                self._circuit_breaker.record_success()
                self._metrics["successful_calls"] += 1
                self._state = AgentState.READY
                
                processing_time = (time.time() - start_time) * 1000
                self._metrics["total_processing_time_ms"] += processing_time
                
                return AgentResult(
                    success=True,
                    data=result,
                    correlation_id=correlation_id,
                    processing_time_ms=processing_time,
                    retries_used=retries_used,
                )
                
            except asyncio.TimeoutError:
                last_error = "Operation timed out"
                self.logger.warning(f"[{correlation_id}] Attempt {attempt + 1} timed out")
                
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"[{correlation_id}] Attempt {attempt + 1} failed: {e}")
            
            # Retry logic
            if attempt < self.config.max_retries:
                retries_used += 1
                self._metrics["total_retries"] += 1
                
                # Exponential backoff
                delay = min(
                    self.config.retry_base_delay * (self.config.retry_exponential_base ** attempt),
                    self.config.retry_max_delay
                )
                self.logger.info(f"[{correlation_id}] Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
        
        # All retries failed
        self._circuit_breaker.record_failure()
        self._metrics["failed_calls"] += 1
        self._metrics["last_error"] = last_error
        
        # Try fallback if enabled
        if self.config.enable_fallback:
            try:
                fallback_result = await asyncio.wait_for(
                    self._fallback_impl(input_data, correlation_id),
                    timeout=self.config.fallback_timeout
                )
                
                self._metrics["fallback_calls"] += 1
                self._state = AgentState.DEGRADED
                
                processing_time = (time.time() - start_time) * 1000
                
                return AgentResult(
                    success=True,
                    data=fallback_result,
                    correlation_id=correlation_id,
                    processing_time_ms=processing_time,
                    retries_used=retries_used,
                    fallback_used=True,
                    warnings=[f"Used fallback after {retries_used} retries: {last_error}"],
                )
            except Exception as e:
                self.logger.warning(f"[{correlation_id}] Fallback also failed: {e}")
        
        self._state = AgentState.READY
        processing_time = (time.time() - start_time) * 1000
        
        return AgentResult(
            success=False,
            error=last_error,
            error_type="ProcessingError",
            correlation_id=correlation_id,
            processing_time_ms=processing_time,
            retries_used=retries_used,
        )
    
    @abstractmethod
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Override this for actual processing logic"""
        pass
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Override this for fallback logic (optional)"""
        raise NotImplementedError("No fallback implemented")
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    def start_background_tasks(self) -> None:
        """Start agent background tasks exactly once."""
        if self._health_task is None and self.config.health_check_interval > 0:
            self._health_task = asyncio.create_task(
                self._health_check_loop(),
                name=f"{self.__class__.__name__}.health_check_loop",
            )
    
    def _start_health_check(self):
        """Deprecated: Use start_background_tasks instead."""
        self.start_background_tasks()
    
    async def _health_check_loop(self):
        """Periodic health check loop"""
        try:
            while not self._closing:
                await asyncio.sleep(self.config.health_check_interval)
                health = await self.health_check()
                
                if not health.get("healthy", False):
                    self.logger.warning(f"Health check failed: {health}")
                    
        except asyncio.CancelledError:
            # Important: allow clean cancellation
            raise
        except Exception as e:
            if not self._closing:
                self.logger.error(f"Health check error: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check agent health.
        
        Override _health_check_impl() for custom checks.
        """
        base_health = {
            "agent": self.name,
            "state": self._state.value,
            "initialized": self._initialized,
            "circuit_breaker": self._circuit_breaker.state.value,
            "metrics": self.get_metrics(),
        }
        
        try:
            custom_health = await self._health_check_impl()
            base_health.update(custom_health)
            base_health["healthy"] = (
                self._state in [AgentState.READY, AgentState.DEGRADED] and
                self._circuit_breaker.state != CircuitBreakerState.OPEN
            )
        except Exception as e:
            base_health["healthy"] = False
            base_health["health_check_error"] = str(e)
        
        return base_health
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        """Override for custom health checks (optional)"""
        return {}
    
    # ========================================================================
    # Metrics and Status
    # ========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get agent metrics"""
        metrics = self._metrics.copy()
        
        # Calculate derived metrics
        total = metrics["total_calls"]
        if total > 0:
            metrics["success_rate"] = metrics["successful_calls"] / total
            metrics["avg_processing_time_ms"] = metrics["total_processing_time_ms"] / total
        else:
            metrics["success_rate"] = 0.0
            metrics["avg_processing_time_ms"] = 0.0
        
        return metrics
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive agent status"""
        return {
            "name": self.name,
            "state": self._state.value,
            "initialized": self._initialized,
            "circuit_breaker": {
                "state": self._circuit_breaker.state.value,
                "failure_count": self._circuit_breaker.failure_count,
            },
            "config": {
                "max_retries": self.config.max_retries,
                "operation_timeout": self.config.operation_timeout,
                "enable_fallback": self.config.enable_fallback,
            },
            "metrics": self.get_metrics(),
        }


# Backward compatibility alias
BaseAgent = UltraBaseAgent
