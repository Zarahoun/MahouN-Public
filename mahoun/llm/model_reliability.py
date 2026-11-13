"""
Model Reliability System
=========================
Ensures models work reliably with monitoring and fallbacks
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
import time

log = logging.getLogger(__name__)


@dataclass
class ModelHealth:
    """Model health status"""
    model_name: str
    is_healthy: bool
    last_success: Optional[datetime]
    last_failure: Optional[datetime]
    success_count: int
    failure_count: int
    avg_latency_ms: float
    current_fallback: Optional[str]


class ModelReliabilityMonitor:
    """
    Monitor model reliability and manage fallbacks
    
    Features:
    - Health tracking
    - Automatic fallback switching
    - Performance monitoring
    - Alert generation
    """
    
    def __init__(self):
        self.health_status: Dict[str, ModelHealth] = {}
        self.fallback_active: Dict[str, str] = {}
    
    def record_success(
        self,
        model_name: str,
        latency_ms: float
    ):
        """Record successful model inference"""
        if model_name not in self.health_status:
            self.health_status[model_name] = ModelHealth(
                model_name=model_name,
                is_healthy=True,
                last_success=datetime.utcnow(),
                last_failure=None,
                success_count=1,
                failure_count=0,
                avg_latency_ms=latency_ms,
                current_fallback=None
            )
        else:
            health = self.health_status[model_name]
            health.success_count += 1
            health.last_success = datetime.utcnow()
            health.is_healthy = True
            
            # Update average latency (exponential moving average)
            alpha = 0.1
            health.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * health.avg_latency_ms
            )
    
    def record_failure(
        self,
        model_name: str,
        error: str
    ):
        """Record model failure"""
        if model_name not in self.health_status:
            self.health_status[model_name] = ModelHealth(
                model_name=model_name,
                is_healthy=False,
                last_success=None,
                last_failure=datetime.utcnow(),
                success_count=0,
                failure_count=1,
                avg_latency_ms=0.0,
                current_fallback=None
            )
        else:
            health = self.health_status[model_name]
            health.failure_count += 1
            health.last_failure = datetime.utcnow()
            
            # Mark unhealthy if failure rate is high
            total = health.success_count + health.failure_count
            failure_rate = health.failure_count / total
            
            if failure_rate > 0.1:  # >10% failure rate
                health.is_healthy = False
                log.warning(f"⚠️ Model {model_name} marked unhealthy (failure rate: {failure_rate:.1%})")
    
    def get_health(self, model_name: str) -> Optional[ModelHealth]:
        """Get model health status"""
        return self.health_status.get(model_name)
    
    def get_all_health(self) -> Dict[str, ModelHealth]:
        """Get all model health statuses"""
        return self.health_status
    
    def should_use_fallback(self, model_name: str) -> bool:
        """Check if fallback should be used"""
        health = self.get_health(model_name)
        
        if not health:
            return False
        
        # Use fallback if model is unhealthy
        if not health.is_healthy:
            return True
        
        # Use fallback if recent failures
        if health.last_failure:
            time_since_failure = datetime.utcnow() - health.last_failure
            if time_since_failure < timedelta(minutes=5):
                return True
        
        return False
    
    def set_fallback(self, primary_model: str, fallback_model: str):
        """Set active fallback"""
        self.fallback_active[primary_model] = fallback_model
        
        if primary_model in self.health_status:
            self.health_status[primary_model].current_fallback = fallback_model
        
        log.info(f"🔄 Fallback active: {primary_model} → {fallback_model}")
    
    def clear_fallback(self, primary_model: str):
        """Clear fallback (primary recovered)"""
        if primary_model in self.fallback_active:
            del self.fallback_active[primary_model]
        
        if primary_model in self.health_status:
            self.health_status[primary_model].current_fallback = None
        
        log.info(f"✅ Primary model recovered: {primary_model}")
    
    def generate_report(self) -> str:
        """Generate health report"""
        report = ["📊 Model Health Report", "=" * 50, ""]
        
        for model_name, health in self.health_status.items():
            status = "✅" if health.is_healthy else "❌"
            fallback = f" → {health.current_fallback}" if health.current_fallback else ""
            
            report.append(f"{status} {model_name}{fallback}")
            report.append(f"   Success: {health.success_count}, Failures: {health.failure_count}")
            report.append(f"   Avg Latency: {health.avg_latency_ms:.0f}ms")
            report.append("")
        
        return "\n".join(report)


# Global instance
_reliability_monitor: Optional[ModelReliabilityMonitor] = None


def get_reliability_monitor() -> ModelReliabilityMonitor:
    """Get global reliability monitor"""
    global _reliability_monitor
    if _reliability_monitor is None:
        _reliability_monitor = ModelReliabilityMonitor()
    return _reliability_monitor


def with_reliability_tracking(model_name: str):
    """Decorator for tracking model reliability"""
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            monitor = get_reliability_monitor()
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                monitor.record_success(model_name, latency_ms)
                return result
                
            except Exception as e:
                monitor.record_failure(model_name, str(e))
                raise
        
        return wrapper
    return decorator
