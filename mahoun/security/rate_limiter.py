"""
Advanced Rate Limiting
=======================

Sliding window rate limiter with Redis backend support.

Features:
- Sliding window algorithm for accurate rate limiting
- Per-user and per-IP rate limits
- Redis backend for distributed systems
- In-memory fallback for single-instance deployments
- Configurable time windows and limits
"""

import time
from typing import Dict, Optional, Tuple
from collections import deque
from dataclasses import dataclass
import threading
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, limit: int, window: int, retry_after: float):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window}s. "
            f"Retry after {retry_after:.1f}s"
        )


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_window: int
    window_seconds: int
    burst_multiplier: float = 1.0  # No burst by default for strict enforcement


class SlidingWindowCounter:
    """
    Sliding window counter for rate limiting.
    
    Uses a deque to track request timestamps within the window.
    """
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.requests: deque = deque()
        self.lock = threading.Lock()
    
    def check_and_increment(self, current_time: float) -> Tuple[bool, float]:
        """
        Check if request is allowed and increment counter.
        
        Args:
            current_time: Current timestamp
            
        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        with self.lock:
            # Remove expired requests
            cutoff_time = current_time - self.config.window_seconds
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            
            # Check limit
            current_count = len(self.requests)
            max_requests = int(
                self.config.requests_per_window * self.config.burst_multiplier
            )
            
            if current_count >= max_requests:
                # Calculate retry_after
                oldest_request = self.requests[0]
                retry_after = oldest_request + self.config.window_seconds - current_time
                return False, max(0, retry_after)
            
            # Add current request
            self.requests.append(current_time)
            return True, 0.0
    
    def get_current_count(self, current_time: float) -> int:
        """Get current request count in window."""
        with self.lock:
            cutoff_time = current_time - self.config.window_seconds
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            return len(self.requests)


class RateLimiter:
    """
    Advanced rate limiter with sliding window algorithm.
    
    Supports per-user and per-IP rate limiting with configurable limits.
    """
    
    def __init__(
        self,
        default_config: Optional[RateLimitConfig] = None,
        redis_url: Optional[str] = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            default_config: Default rate limit configuration
            redis_url: Optional Redis URL for distributed rate limiting
        """
        self.default_config = default_config or RateLimitConfig(
            requests_per_window=100,
            window_seconds=60
        )
        
        # Per-identifier counters
        self.counters: Dict[str, SlidingWindowCounter] = {}
        self.counters_lock = threading.Lock()
        
        # Custom configs per identifier
        self.custom_configs: Dict[str, RateLimitConfig] = {}
        
        # Redis support (optional)
        self.redis_client = None
        if redis_url:
            try:
                import redis
                self.redis_client = redis.from_url(redis_url)
                logger.info("Redis backend enabled for rate limiting")
            except ImportError:
                logger.warning("redis package not installed - using in-memory backend")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
    
    def set_custom_limit(
        self,
        identifier: str,
        requests_per_window: int,
        window_seconds: int
    ) -> None:
        """
        Set custom rate limit for specific identifier.
        
        Args:
            identifier: User ID, API key, or IP address
            requests_per_window: Number of requests allowed
            window_seconds: Time window in seconds
        """
        self.custom_configs[identifier] = RateLimitConfig(
            requests_per_window=requests_per_window,
            window_seconds=window_seconds
        )
        logger.info(
            f"Custom rate limit set for {identifier}: "
            f"{requests_per_window} req/{window_seconds}s"
        )
    
    def _get_counter(self, identifier: str) -> SlidingWindowCounter:
        """Get or create counter for identifier."""
        with self.counters_lock:
            if identifier not in self.counters:
                config = self.custom_configs.get(identifier, self.default_config)
                self.counters[identifier] = SlidingWindowCounter(config)
            return self.counters[identifier]
    
    def check_rate_limit(
        self,
        identifier: str,
        cost: int = 1
    ) -> None:
        """
        Check rate limit for identifier.
        
        Args:
            identifier: User ID, API key, or IP address
            cost: Request cost (default 1, can be higher for expensive operations)
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if self.redis_client:
            self._check_rate_limit_redis(identifier, cost)
        else:
            self._check_rate_limit_memory(identifier, cost)
    
    def _check_rate_limit_memory(self, identifier: str, cost: int) -> None:
        """Check rate limit using in-memory backend."""
        counter = self._get_counter(identifier)
        current_time = time.time()
        
        # Check multiple times for cost > 1
        for _ in range(cost):
            allowed, retry_after = counter.check_and_increment(current_time)
            if not allowed:
                config = self.custom_configs.get(identifier, self.default_config)
                raise RateLimitExceeded(
                    limit=config.requests_per_window,
                    window=config.window_seconds,
                    retry_after=retry_after
                )
    
    def _check_rate_limit_redis(self, identifier: str, cost: int) -> None:
        """Check rate limit using Redis backend."""
        config = self.custom_configs.get(identifier, self.default_config)
        key = f"ratelimit:{identifier}"
        current_time = time.time()
        window_start = current_time - config.window_seconds
        
        try:
            # Use Redis sorted set for sliding window
            pipe = self.redis_client.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiry
            pipe.expire(key, config.window_seconds)
            
            results = pipe.execute()
            current_count = results[1]
            
            max_requests = int(
                config.requests_per_window * config.burst_multiplier
            )
            
            if current_count >= max_requests:
                # Get oldest request for retry_after calculation
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = oldest_time + config.window_seconds - current_time
                else:
                    retry_after = config.window_seconds
                
                raise RateLimitExceeded(
                    limit=config.requests_per_window,
                    window=config.window_seconds,
                    retry_after=max(0, retry_after)
                )
                
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fallback to memory-based check
            self._check_rate_limit_memory(identifier, cost)
    
    def get_remaining_requests(self, identifier: str) -> int:
        """
        Get remaining requests for identifier.
        
        Args:
            identifier: User ID, API key, or IP address
            
        Returns:
            Number of remaining requests in current window
        """
        config = self.custom_configs.get(identifier, self.default_config)
        
        if self.redis_client:
            key = f"ratelimit:{identifier}"
            current_time = time.time()
            window_start = current_time - config.window_seconds
            
            try:
                # Clean old entries and count
                pipe = self.redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                results = pipe.execute()
                current_count = results[1]
            except Exception as e:
                logger.error(f"Redis query failed: {e}")
                counter = self._get_counter(identifier)
                current_count = counter.get_current_count(current_time)
        else:
            counter = self._get_counter(identifier)
            current_count = counter.get_current_count(time.time())
        
        return max(0, config.requests_per_window - current_count)
    
    def reset_limit(self, identifier: str) -> None:
        """
        Reset rate limit for identifier.
        
        Args:
            identifier: User ID, API key, or IP address
        """
        if self.redis_client:
            key = f"ratelimit:{identifier}"
            self.redis_client.delete(key)
        
        with self.counters_lock:
            if identifier in self.counters:
                del self.counters[identifier]
        
        logger.info(f"Rate limit reset for {identifier}")
    
    def cleanup_expired(self) -> int:
        """
        Cleanup expired counters from memory.
        
        Returns:
            Number of counters removed
        """
        if self.redis_client:
            return 0  # Redis handles expiry automatically
        
        current_time = time.time()
        removed = 0
        
        with self.counters_lock:
            expired_ids = []
            for identifier, counter in self.counters.items():
                if counter.get_current_count(current_time) == 0:
                    expired_ids.append(identifier)
            
            for identifier in expired_ids:
                del self.counters[identifier]
                removed += 1
        
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired rate limit counters")
        
        return removed
