"""
Model Loading Service with Circuit Breaker & Retry Logic

Extracted from: mahoun/bootstrap/executors/ai_ml_components.py (lines 293-340)
Responsibility: Load models with exponential backoff, circuit breaker protection,
               and graceful degradation on failure.

Architecture:
- Circuit breaker prevents cascading failures
- Exponential backoff with jitter for transient errors
- Async/await for non-blocking operations
- Comprehensive error context for debugging
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Generic
from random import uniform

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitBreakerState(str, Enum):
    """Circuit breaker FSM states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject immediately
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 3          # Failures before opening
    success_threshold: int = 2          # Successes before closing from half-open
    timeout_seconds: float = 60.0       # Time before half-open retry
    half_open_max_calls: int = 1        # Max concurrent calls in half-open


@dataclass
class RetryConfig:
    """Retry policy configuration"""
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd


@dataclass
class LoadResult(Generic[T]):
    """Model loading result with comprehensive context"""
    success: bool
    model: Optional[T]
    error: Optional[Exception]
    attempts: int
    duration_seconds: float
    circuit_breaker_state: CircuitBreakerState
    metadata: Dict[str, Any]


class CircuitBreaker:
    """
    Circuit breaker for model loading operations
    
    Prevents cascading failures by stopping requests when a dependency
    is consistently failing. Implements FSM: CLOSED → OPEN → HALF_OPEN → CLOSED
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitBreakerState:
        return self._state
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker"""
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                # Check if timeout elapsed → transition to HALF_OPEN
                if self._last_failure_time:
                    elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                    if elapsed >= self.config.timeout_seconds:
                        logger.info(
                            f"Circuit breaker transitioning to HALF_OPEN after {elapsed:.1f}s"
                        )
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._half_open_calls = 0
                    else:
                        raise RuntimeError(
                            f"Circuit breaker OPEN: rejecting call "
                            f"(retry in {self.config.timeout_seconds - elapsed:.1f}s)"
                        )
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise RuntimeError(
                        "Circuit breaker HALF_OPEN: max concurrent calls reached"
                    )
                self._half_open_calls += 1
        
        # Execute function (release lock to allow concurrent calls)
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call"""
        async with self._lock:
            self._failure_count = 0
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    logger.info("Circuit breaker transitioning to CLOSED (recovery confirmed)")
                    self._state = CircuitBreakerState.CLOSED
                    self._success_count = 0
    
    async def _on_failure(self):
        """Handle failed call"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                logger.warning("Circuit breaker transitioning to OPEN (half-open call failed)")
                self._state = CircuitBreakerState.OPEN
                self._success_count = 0
            elif self._failure_count >= self.config.failure_threshold:
                logger.error(
                    f"Circuit breaker transitioning to OPEN "
                    f"(failure threshold {self.config.failure_threshold} reached)"
                )
                self._state = CircuitBreakerState.OPEN


class ModelLoader:
    """
    Production-grade model loader with resilience patterns
    
    Features:
    - Circuit breaker protection against cascading failures
    - Exponential backoff with jitter for transient errors
    - Comprehensive error context for debugging
    - Async/await for non-blocking operations
    
    Example:
        loader = ModelLoader(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            retry_config=RetryConfig(max_attempts=3)
        )
        
        result = await loader.load_model(
            model_name="embedding-model",
            loader_func=lambda: SentenceTransformer("model-name")
        )
        
        if result.success:
            print(f"Model loaded in {result.duration_seconds:.2f}s")
        else:
            print(f"Failed after {result.attempts} attempts: {result.error}")
    """
    
    def __init__(
        self,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        self.circuit_breaker = CircuitBreaker(
            circuit_breaker_config or CircuitBreakerConfig()
        )
        self.retry_config = retry_config or RetryConfig()
    
    async def load_model(
        self,
        model_name: str,
        loader_func: Callable[[], T],
        metadata: Optional[Dict[str, Any]] = None
    ) -> LoadResult[T]:
        """
        Load model with retry logic and circuit breaker protection
        
        Args:
            model_name: Human-readable model identifier
            loader_func: Callable that loads the model (sync or async)
            metadata: Additional context for debugging
        
        Returns:
            LoadResult with success status, model (if successful), error, and context
        """
        start_time = datetime.utcnow()
        attempts = 0
        last_error: Optional[Exception] = None
        
        logger.info(
            f"Loading model '{model_name}' "
            f"(max_attempts={self.retry_config.max_attempts}, "
            f"circuit_breaker={self.circuit_breaker.state})"
        )
        
        for attempt in range(1, self.retry_config.max_attempts + 1):
            attempts = attempt
            try:
                # Execute through circuit breaker
                model = await self.circuit_breaker.call(loader_func)
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(
                    f"Model '{model_name}' loaded successfully "
                    f"(attempt {attempt}/{self.retry_config.max_attempts}, "
                    f"duration={duration:.2f}s)"
                )
                
                return LoadResult(
                    success=True,
                    model=model,
                    error=None,
                    attempts=attempts,
                    duration_seconds=duration,
                    circuit_breaker_state=self.circuit_breaker.state,
                    metadata=metadata or {}
                )
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Model '{model_name}' load failed "
                    f"(attempt {attempt}/{self.retry_config.max_attempts}): {e}"
                )
                
                # Don't retry if circuit breaker is open
                if self.circuit_breaker.state == CircuitBreakerState.OPEN:
                    logger.error(
                        f"Circuit breaker OPEN: aborting retry for '{model_name}'"
                    )
                    break
                
                # Calculate backoff delay
                if attempt < self.retry_config.max_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
        
        # All attempts failed
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            f"Model '{model_name}' failed to load after {attempts} attempts "
            f"(duration={duration:.2f}s, final_error={last_error})"
        )
        
        return LoadResult(
            success=False,
            model=None,
            error=last_error,
            attempts=attempts,
            duration_seconds=duration,
            circuit_breaker_state=self.circuit_breaker.state,
            metadata=metadata or {}
        )
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with optional jitter"""
        delay = min(
            self.retry_config.initial_delay_seconds * (self.retry_config.exponential_base ** (attempt - 1)),
            self.retry_config.max_delay_seconds
        )
        
        if self.retry_config.jitter:
            # Add ±25% jitter to prevent thundering herd
            jitter_range = delay * 0.25
            delay += uniform(-jitter_range, jitter_range)
        
        return max(0.0, delay)
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker (use for testing/admin operations)"""
        logger.warning("Circuit breaker manually reset")
        self.circuit_breaker._state = CircuitBreakerState.CLOSED
        self.circuit_breaker._failure_count = 0
        self.circuit_breaker._success_count = 0
