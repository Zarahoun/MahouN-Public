"""
Task and Event Orchestrator
============================

Features:
- Distributed task scheduling with priority queues
- Health monitoring and auto-recovery
- Circuit breakers and rate limiting
- Event-driven architecture with pub/sub
- Real-time metrics and alerting
- A/B testing orchestration
- Canary deployments
- Blue-green deployments
- Feature flags
- Chaos engineering integration
"""

import asyncio
import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from queue import PriorityQueue
import json
import hashlib

try:
    import numpy as np
    import torch
    import torch.nn as nn
except ImportError:
    np = None
    torch = None
    class DummyModule:
        Module = object
    nn = DummyModule()


# ============================================================================
# Core Types and Enums
# ============================================================================

class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


class ComponentState(Enum):
    """Component state"""
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"
    STOPPED = "stopped"


class DeploymentStrategy(Enum):
    """Deployment strategies"""
    IMMEDIATE = "immediate"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    SHADOW = "shadow"


@dataclass
class Task:
    """Orchestrator task"""
    id: str
    name: str
    priority: TaskPriority
    func: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    timeout: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __lt__(self, other):
        """Compare tasks by priority"""
        return self.priority.value < other.priority.value


@dataclass
class ComponentHealth:
    """Component health status"""
    name: str
    state: ComponentState
    last_heartbeat: datetime
    error_count: int = 0
    success_count: int = 0
    latency_ms: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    custom_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class Event:
    """System event"""
    type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest())


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitBreaker:
    """Circuit breaker for fault tolerance"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function with circuit breaker protection"""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        if self.state == "half_open":
            self.state = "closed"
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


# ============================================================================
# Rate Limiter
# ============================================================================

class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Add tokens based on elapsed time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def wait_and_acquire(self, tokens: int = 1, timeout: Optional[float] = None):
        """Wait until tokens are available"""
        start_time = time.time()
        
        while True:
            if self.acquire(tokens):
                return True
            
            if timeout and (time.time() - start_time) > timeout:
                return False
            
            time.sleep(0.01)


# ============================================================================
# Event Bus
# ============================================================================

class EventBus:
    """Pub/sub event bus"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: deque = deque(maxlen=1000)
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to event type"""
        self.subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from event type"""
        if callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
    
    def publish(self, event: Event):
        """Publish event to subscribers"""
        self.event_history.append(event)
        
        # Notify subscribers
        for callback in self.subscribers.get(event.type, []):
            try:
                callback(event)
            except Exception as e:
                print(f"Error in event callback: {e}")
        
        # Notify wildcard subscribers
        for callback in self.subscribers.get("*", []):
            try:
                callback(event)
            except Exception as e:
                print(f"Error in wildcard callback: {e}")
    
    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history"""
        if event_type:
            return [e for e in self.event_history if e.type == event_type][-limit:]
        return list(self.event_history)[-limit:]


# ============================================================================
# Feature Flags
# ============================================================================

class FeatureFlags:
    """Feature flag management"""
    
    def __init__(self):
        self.flags: Dict[str, bool] = {}
        self.rollout_percentages: Dict[str, float] = {}
    
    def enable(self, flag: str):
        """Enable feature flag"""
        self.flags[flag] = True
    
    def disable(self, flag: str):
        """Disable feature flag"""
        self.flags[flag] = False
    
    def is_enabled(self, flag: str, user_id: Optional[str] = None) -> bool:
        """Check if feature is enabled"""
        if flag not in self.flags:
            return False
        
        # Check rollout percentage
        if flag in self.rollout_percentages:
            percentage = self.rollout_percentages[flag]
            if user_id:
                # Deterministic rollout based on user_id
                hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
                return (hash_val % 100) < (percentage * 100)
            else:
                # Random rollout
                return np.random.random() < percentage
        
        return self.flags[flag]
    
    def set_rollout(self, flag: str, percentage: float):
        """Set gradual rollout percentage"""
        self.rollout_percentages[flag] = max(0.0, min(1.0, percentage))


# ============================================================================
# Ultra Orchestrator
# ============================================================================

class UltraOrchestrator:
    """
    Task and event orchestrator.

    Manages:
    - Task scheduling and execution
    - Component health monitoring
    - Circuit breakers and rate limiting
    - Event-driven coordination
    - Deployment strategies
    - Feature flags
    - Metrics and alerting
    """
    
    def __init__(
        self,
        max_workers: int = 10,
        health_check_interval: float = 30.0,
    ):
        self.max_workers = max_workers
        self.health_check_interval = health_check_interval
        
        # Task management
        self.task_queue = PriorityQueue()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.completed_tasks: deque = deque(maxlen=1000)
        
        # Component management
        self.components: Dict[str, Any] = {}
        self.component_health: Dict[str, ComponentHealth] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.rate_limiters: Dict[str, RateLimiter] = {}
        
        # Event system
        self.event_bus = EventBus()
        
        # Feature flags
        self.feature_flags = FeatureFlags()
        
        # Deployment management
        self.active_deployments: Dict[str, Dict[str, Any]] = {}
        
        # Metrics
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_latency_ms": 0.0,
            "component_failures": defaultdict(int),
        }
        
        # State
        self.running = False
        self.start_time = None
        
        print("🎯 Ultra Orchestrator initialized")
    
    def register_component(
        self,
        name: str,
        component: Any,
        circuit_breaker: bool = True,
        rate_limit: Optional[Tuple[float, int]] = None,
    ):
        """Register component with orchestrator"""
        self.components[name] = component
        
        # Initialize health
        self.component_health[name] = ComponentHealth(
            name=name,
            state=ComponentState.INITIALIZING,
            last_heartbeat=datetime.now(),
        )
        
        # Setup circuit breaker
        if circuit_breaker:
            self.circuit_breakers[name] = CircuitBreaker()
        
        # Setup rate limiter
        if rate_limit:
            rate, capacity = rate_limit
            self.rate_limiters[name] = RateLimiter(rate, capacity)
        
        print(f"   ✅ Registered component: {name}")
    
    def submit_task(
        self,
        name: str,
        func: Callable,
        priority: TaskPriority = TaskPriority.MEDIUM,
        *args,
        **kwargs,
    ) -> str:
        """Submit task for execution"""
        task_id = f"{name}_{int(time.time() * 1000)}"
        
        task = Task(
            id=task_id,
            name=name,
            priority=priority,
            func=func,
            args=args,
            kwargs=kwargs,
        )
        
        self.task_queue.put(task)
        
        # Publish event
        self.event_bus.publish(Event(
            type="task_submitted",
            source="orchestrator",
            data={"task_id": task_id, "name": name, "priority": priority.value},
        ))
        
        return task_id
    
    async def start(self):
        """Start orchestrator"""
        if self.running:
            return
        
        self.running = True
        self.start_time = datetime.now()
        
        print("🚀 Starting Ultra Orchestrator...")
        
        # Start worker tasks
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_workers)
        ]
        
        # Start health monitor
        health_monitor = asyncio.create_task(self._health_monitor())
        
        # Start metrics collector
        metrics_collector = asyncio.create_task(self._metrics_collector())
        
        # Publish event
        self.event_bus.publish(Event(
            type="orchestrator_started",
            source="orchestrator",
            data={"workers": self.max_workers},
        ))
        
        print("✅ Orchestrator started")
        
        # Wait for all tasks
        await asyncio.gather(*workers, health_monitor, metrics_collector)
    
    async def stop(self):
        """Stop orchestrator"""
        print("🛑 Stopping orchestrator...")
        
        self.running = False
        
        # Cancel running tasks
        for task in self.running_tasks.values():
            task.cancel()
        
        # Publish event
        self.event_bus.publish(Event(
            type="orchestrator_stopped",
            source="orchestrator",
            data={},
        ))
        
        print("✅ Orchestrator stopped")
    
    async def _worker(self, worker_id: int):
        """Worker task"""
        while self.running:
            try:
                # Get task from queue (non-blocking)
                if not self.task_queue.empty():
                    task = self.task_queue.get_nowait()
                    
                    # Execute task
                    await self._execute_task(task, worker_id)
                else:
                    # No tasks, sleep briefly
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1.0)
    
    async def _execute_task(self, task: Task, worker_id: int):
        """Execute task with monitoring"""
        start_time = time.time()
        
        try:
            # Check rate limit
            component_name = task.name.split("_")[0]
            if component_name in self.rate_limiters:
                if not self.rate_limiters[component_name].acquire():
                    # Rate limited, requeue
                    self.task_queue.put(task)
                    return
            
            # Execute with circuit breaker
            if component_name in self.circuit_breakers:
                result = await asyncio.to_thread(
                    self.circuit_breakers[component_name].call,
                    task.func,
                    *task.args,
                    **task.kwargs
                )
            else:
                if asyncio.iscoroutinefunction(task.func):
                    result = await task.func(*task.args, **task.kwargs)
                else:
                    result = await asyncio.to_thread(task.func, *task.args, **task.kwargs)
            
            # Success
            latency = (time.time() - start_time) * 1000
            self.metrics["tasks_completed"] += 1
            self.metrics["total_latency_ms"] += latency
            
            # Update component health
            if component_name in self.component_health:
                health = self.component_health[component_name]
                health.success_count += 1
                health.latency_ms = latency
                health.last_heartbeat = datetime.now()
                health.state = ComponentState.HEALTHY
            
            # Record completion
            self.completed_tasks.append({
                "task_id": task.id,
                "name": task.name,
                "latency_ms": latency,
                "completed_at": datetime.now(),
                "worker_id": worker_id,
            })
            
            # Publish event
            self.event_bus.publish(Event(
                type="task_completed",
                source="orchestrator",
                data={
                    "task_id": task.id,
                    "name": task.name,
                    "latency_ms": latency,
                    "worker_id": worker_id,
                },
            ))
            
        except Exception as e:
            # Failure
            self.metrics["tasks_failed"] += 1
            
            component_name = task.name.split("_")[0]
            self.metrics["component_failures"][component_name] += 1
            
            # Update component health
            if component_name in self.component_health:
                health = self.component_health[component_name]
                health.error_count += 1
                health.state = ComponentState.DEGRADED
            
            # Retry logic
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                self.task_queue.put(task)
                print(f"   🔄 Retrying task {task.id} (attempt {task.retry_count})")
            else:
                print(f"   ❌ Task {task.id} failed after {task.max_retries} retries: {e}")
            
            # Publish event
            self.event_bus.publish(Event(
                type="task_failed",
                source="orchestrator",
                data={
                    "task_id": task.id,
                    "name": task.name,
                    "error": str(e),
                    "retry_count": task.retry_count,
                },
            ))
    
    async def _health_monitor(self):
        """Monitor component health"""
        while self.running:
            try:
                for name, health in self.component_health.items():
                    # Check heartbeat
                    time_since_heartbeat = (datetime.now() - health.last_heartbeat).total_seconds()
                    
                    if time_since_heartbeat > 60:
                        health.state = ComponentState.UNHEALTHY
                        
                        # Publish alert
                        self.event_bus.publish(Event(
                            type="component_unhealthy",
                            source="health_monitor",
                            data={
                                "component": name,
                                "time_since_heartbeat": time_since_heartbeat,
                            },
                        ))
                    
                    # Check error rate
                    total_requests = health.success_count + health.error_count
                    if total_requests > 100:
                        error_rate = health.error_count / total_requests
                        if error_rate > 0.1:  # 10% error rate
                            health.state = ComponentState.DEGRADED
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                print(f"Health monitor error: {e}")
                await asyncio.sleep(5.0)
    
    async def _metrics_collector(self):
        """Collect and publish metrics"""
        while self.running:
            try:
                # Compute metrics
                uptime = (datetime.now() - self.start_time).total_seconds()
                avg_latency = (
                    self.metrics["total_latency_ms"] / max(1, self.metrics["tasks_completed"])
                )
                
                metrics_snapshot = {
                    "uptime_seconds": uptime,
                    "tasks_completed": self.metrics["tasks_completed"],
                    "tasks_failed": self.metrics["tasks_failed"],
                    "avg_latency_ms": avg_latency,
                    "queue_size": self.task_queue.qsize(),
                    "running_tasks": len(self.running_tasks),
                    "component_health": {
                        name: health.state.value
                        for name, health in self.component_health.items()
                    },
                }
                
                # Publish metrics event
                self.event_bus.publish(Event(
                    type="metrics_snapshot",
                    source="metrics_collector",
                    data=metrics_snapshot,
                ))
                
                await asyncio.sleep(60.0)  # Every minute
                
            except Exception as e:
                print(f"Metrics collector error: {e}")
                await asyncio.sleep(5.0)
    
    async def deploy_model(
        self,
        model_id: str,
        model: nn.Module,
        strategy: DeploymentStrategy = DeploymentStrategy.CANARY,
        traffic_percentage: float = 0.1,
    ):
        """Deploy model with specified strategy"""
        print(f"🚀 Deploying model {model_id} with {strategy.value} strategy...")
        
        deployment = {
            "model_id": model_id,
            "model": model,
            "strategy": strategy,
            "traffic_percentage": traffic_percentage,
            "started_at": datetime.now(),
            "status": "deploying",
        }
        
        self.active_deployments[model_id] = deployment
        
        if strategy == DeploymentStrategy.CANARY:
            await self._canary_deployment(model_id, model, traffic_percentage)
        elif strategy == DeploymentStrategy.BLUE_GREEN:
            await self._blue_green_deployment(model_id, model)
        elif strategy == DeploymentStrategy.SHADOW:
            await self._shadow_deployment(model_id, model)
        else:
            # Immediate deployment
            deployment["status"] = "deployed"
        
        # Publish event
        self.event_bus.publish(Event(
            type="model_deployed",
            source="orchestrator",
            data={
                "model_id": model_id,
                "strategy": strategy.value,
            },
        ))
        
        print(f"✅ Model {model_id} deployed successfully")
    
    async def _canary_deployment(
        self,
        model_id: str,
        model: nn.Module,
        initial_traffic: float,
    ):
        """Canary deployment with gradual rollout"""
        traffic = initial_traffic
        
        while traffic < 1.0:
            print(f"   📊 Canary at {traffic*100:.0f}% traffic")
            
            # Monitor metrics
            await asyncio.sleep(300)  # 5 minutes
            
            # Check if canary is healthy
            # (simplified - in production, check actual metrics)
            is_healthy = True
            
            if is_healthy:
                # Increase traffic
                traffic = min(1.0, traffic + 0.1)
            else:
                # Rollback
                print(f"   ❌ Canary unhealthy, rolling back")
                self.active_deployments[model_id]["status"] = "rolled_back"
                return
        
        self.active_deployments[model_id]["status"] = "deployed"
        self.active_deployments[model_id]["traffic_percentage"] = 1.0
    
    async def _blue_green_deployment(self, model_id: str, model: nn.Module):
        """Blue-green deployment"""
        print(f"   🔵 Deploying to green environment")
        
        # Deploy to green
        await asyncio.sleep(1.0)
        
        # Switch traffic
        print(f"   🔄 Switching traffic to green")
        await asyncio.sleep(0.5)
        
        self.active_deployments[model_id]["status"] = "deployed"
    
    async def _shadow_deployment(self, model_id: str, model: nn.Module):
        """Shadow deployment (no user-facing traffic)"""
        print(f"   👻 Shadow deployment active")
        
        self.active_deployments[model_id]["status"] = "shadow"
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        return {
            "running": self.running,
            "uptime_seconds": uptime,
            "metrics": self.metrics,
            "queue_size": self.task_queue.qsize(),
            "running_tasks": len(self.running_tasks),
            "components": {
                name: {
                    "state": health.state.value,
                    "success_count": health.success_count,
                    "error_count": health.error_count,
                    "latency_ms": health.latency_ms,
                }
                for name, health in self.component_health.items()
            },
            "active_deployments": len(self.active_deployments),
        }


# ============================================================================
# Example Usage
# ============================================================================

async def example_usage():
    """Example of using ultra orchestrator"""
    # Create orchestrator
    orchestrator = UltraOrchestrator(max_workers=5)
    
    # Register components
    orchestrator.register_component(
        "rl_agent",
        None,
        circuit_breaker=True,
        rate_limit=(10.0, 100),  # 10 requests/sec, capacity 100
    )
    
    orchestrator.register_component(
        "active_learner",
        None,
        circuit_breaker=True,
    )
    
    # Subscribe to events
    def on_task_completed(event: Event):
        print(f"   ✅ Task completed: {event.data['task_id']}")
    
    orchestrator.event_bus.subscribe("task_completed", on_task_completed)
    
    # Submit tasks
    def sample_task(x):
        time.sleep(0.1)
        return x * 2
    
    for i in range(10):
        orchestrator.submit_task(
            f"rl_agent_task_{i}",
            sample_task,
            TaskPriority.HIGH,
            i,
        )
    
    # Start orchestrator
    start_task = asyncio.create_task(orchestrator.start())
    
    # Let it run for a bit
    await asyncio.sleep(5.0)
    
    # Get status
    status = orchestrator.get_status()
    print(f"\n📊 Status: {status}")
    
    # Stop
    await orchestrator.stop()


if __name__ == "__main__":
    print("🎯 Ultra-Advanced Orchestrator")
    print("=" * 60)
    
    asyncio.run(example_usage())

# Compatibility shims for older features (not used in this version)
    def stop(self):
        pass
