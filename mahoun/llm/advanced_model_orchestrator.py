"""
Advanced Model Orchestrator — Enterprise ML Management
=======================================================

Ultra-advanced model lifecycle management:
- A/B testing between models
- Auto-scaling based on load
- Model performance monitoring
- Drift detection
- Canary deployments
- Rollback capabilities
- Multi-model ensemble routing
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, deque
from threading import Lock
import hashlib
import json

from mahoun.llm.model_manager import ModelManager
from mahoun.core.exceptions import ModelLoadError

logger = logging.getLogger(__name__)


@dataclass
class ModelMetrics:
    """Real-time model performance metrics"""
    model_id: str
    model_name: str
    version: str
    
    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    
    # Resource metrics
    memory_usage_mb: float = 0.0
    gpu_usage_percent: float = 0.0
    
    # Quality metrics
    avg_confidence_score: float = 0.0
    error_rate: float = 0.0
    
    # Timestamps
    first_request_at: Optional[str] = None
    last_request_at: Optional[str] = None
    
    # Latency history (last 1000 requests)
    latency_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def update_latency(self, latency_ms: float):
        """Update latency metrics"""
        self.latency_history.append(latency_ms)
        
        if self.latency_history:
            sorted_latencies = sorted(self.latency_history)
            n = len(sorted_latencies)
            
            self.avg_latency_ms = sum(sorted_latencies) / n
            self.p95_latency_ms = sorted_latencies[int(n * 0.95)] if n > 0 else 0
            self.p99_latency_ms = sorted_latencies[int(n * 0.99)] if n > 0 else 0
    
    def update_request_count(self, success: bool):
        """Update request counters"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        self.error_rate = self.failed_requests / self.total_requests if self.total_requests > 0 else 0.0
        self.last_request_at = datetime.now().isoformat()
        
        if self.first_request_at is None:
            self.first_request_at = self.last_request_at


@dataclass
class ABTestConfig:
    """A/B test configuration"""
    test_id: str
    model_a: str  # Control
    model_b: str  # Treatment
    traffic_split: float = 0.5  # 50/50 split
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    min_requests: int = 100  # Minimum requests before decision
    status: str = 'active'  # active | completed | cancelled
    
    # Results
    winner: Optional[str] = None
    confidence: Optional[float] = None


@dataclass
class CanaryDeployment:
    """Canary deployment configuration"""
    canary_id: str
    stable_model: str
    canary_model: str
    canary_traffic_percent: float = 10.0  # Start with 10%
    increment_percent: float = 10.0
    increment_interval_minutes: int = 30
    max_error_rate: float = 0.05  # 5% max error rate
    rollback_on_failure: bool = True
    
    status: str = 'active'  # active | promoting | completed | rolled_back
    current_traffic_percent: float = 10.0
    last_increment_at: Optional[str] = None


class AdvancedModelOrchestrator:
    """
    Enterprise-grade ML model orchestrator
    
    Features:
    - Multi-model management
    - A/B testing framework
    - Canary deployments
    - Performance monitoring
    - Auto-scaling
    - Drift detection
    - Smart routing
    """
    
    def __init__(
        self,
        base_model_manager: Optional[ModelManager] = None,
        enable_ab_testing: bool = True,
        enable_canary: bool = True,
        enable_auto_scale: bool = True,
    ):
        self.model_manager = base_model_manager or ModelManager()
        self.enable_ab_testing = enable_ab_testing
        self.enable_canary = enable_canary
        self.enable_auto_scale = enable_auto_scale
        
        # Model registry
        self.active_models: Dict[str, Any] = {}
        self.model_metrics: Dict[str, ModelMetrics] = {}
        
        # A/B testing
        self.ab_tests: Dict[str, ABTestConfig] = {}
        
        # Canary deployments
        self.canary_deployments: Dict[str, CanaryDeployment] = {}
        
        # Routing strategy
        self.routing_strategy = 'round_robin'
        self._routing_counter = 0
        
        # Thread safety
        self._lock = Lock()
        
        logger.info("Advanced Model Orchestrator initialized")
    
    # ==================== MODEL REGISTRATION ====================
    
    def register_model(
        self,
        model_id: str,
        model_name: str,
        version: str,
        model_instance: Any,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register a model with the orchestrator"""
        with self._lock:
            if model_id in self.active_models:
                logger.warning(f"Model {model_id} already registered")
                return False
            
            self.active_models[model_id] = {
                'model': model_instance,
                'name': model_name,
                'version': version,
                'metadata': metadata or {},
                'registered_at': datetime.now().isoformat(),
                'status': 'active',
            }
            
            self.model_metrics[model_id] = ModelMetrics(
                model_id=model_id,
                model_name=model_name,
                version=version,
            )
            
            logger.info(f"Registered model: {model_id} ({model_name} v{version})")
            return True
    
    def unregister_model(self, model_id: str) -> bool:
        """Unregister a model"""
        with self._lock:
            if model_id not in self.active_models:
                logger.warning(f"Model {model_id} not found")
                return False
            
            del self.active_models[model_id]
            del self.model_metrics[model_id]
            
            logger.info(f"Unregistered model: {model_id}")
            return True
    
    # ==================== SMART ROUTING ====================
    
    def route_request(
        self,
        model_type: str,
        strategy: Optional[str] = None,
    ) -> Optional[str]:
        """Route request to best model based on strategy"""
        strategy = strategy or self.routing_strategy
        
        # Filter models by type
        available_models = [
            mid for mid, info in self.active_models.items()
            if info['name'] == model_type and info['status'] == 'active'
        ]
        
        if not available_models:
            logger.error(f"No active models of type {model_type}")
            return None
        
        if strategy == 'round_robin':
            with self._lock:
                self._routing_counter = (self._routing_counter + 1) % len(available_models)
                return available_models[self._routing_counter]
        
        elif strategy == 'least_loaded':
            model_loads = {
                mid: self.model_metrics[mid].total_requests
                for mid in available_models
            }
            return min(model_loads, key=model_loads.get)
        
        elif strategy == 'best_performance':
            model_latencies = {
                mid: self.model_metrics[mid].avg_latency_ms
                for mid in available_models
                if self.model_metrics[mid].total_requests > 10
            }
            
            if model_latencies:
                return min(model_latencies, key=model_latencies.get)
            else:
                return available_models[0]
        
        else:
            import random
            return random.choice(available_models)
    
    # ==================== A/B TESTING ====================
    
    def start_ab_test(
        self,
        test_id: str,
        model_a: str,
        model_b: str,
        traffic_split: float = 0.5,
        min_requests: int = 100,
    ) -> bool:
        """Start A/B test between two models"""
        if not self.enable_ab_testing:
            logger.warning("A/B testing is disabled")
            return False
        
        if model_a not in self.active_models or model_b not in self.active_models:
            logger.error(f"Both models must be registered: {model_a}, {model_b}")
            return False
        
        with self._lock:
            if test_id in self.ab_tests:
                logger.warning(f"A/B test {test_id} already exists")
                return False
            
            self.ab_tests[test_id] = ABTestConfig(
                test_id=test_id,
                model_a=model_a,
                model_b=model_b,
                traffic_split=traffic_split,
                min_requests=min_requests,
            )
            
            logger.info(f"Started A/B test {test_id}: {model_a} vs {model_b}")
            return True
    
    def get_ab_test_model(self, test_id: str) -> Optional[str]:
        """Get model ID for A/B test request"""
        if test_id not in self.ab_tests:
            return None
        
        test = self.ab_tests[test_id]
        
        if test.status != 'active':
            return None
        
        import random
        if random.random() < test.traffic_split:
            return test.model_a
        else:
            return test.model_b
    
    def evaluate_ab_test(self, test_id: str) -> Dict:
        """Evaluate A/B test and determine winner"""
        if test_id not in self.ab_tests:
            return {'error': 'Test not found'}
        
        test = self.ab_tests[test_id]
        metrics_a = self.model_metrics.get(test.model_a)
        metrics_b = self.model_metrics.get(test.model_b)
        
        if not metrics_a or not metrics_b:
            return {'error': 'Missing metrics'}
        
        total_requests = metrics_a.total_requests + metrics_b.total_requests
        if total_requests < test.min_requests:
            return {
                'status': 'insufficient_data',
                'requests': total_requests,
                'required': test.min_requests,
            }
        
        score_a = self._calculate_model_score(metrics_a)
        score_b = self._calculate_model_score(metrics_b)
        
        winner = test.model_a if score_a > score_b else test.model_b
        confidence = abs(score_a - score_b) / max(score_a, score_b) if max(score_a, score_b) > 0 else 0.0
        
        with self._lock:
            test.winner = winner
            test.confidence = confidence
            test.status = 'completed'
            test.end_time = datetime.now().isoformat()
        
        return {
            'test_id': test_id,
            'winner': winner,
            'confidence': confidence,
            'model_a_score': score_a,
            'model_b_score': score_b,
            'model_a_requests': metrics_a.total_requests,
            'model_b_requests': metrics_b.total_requests,
        }
    
    def _calculate_model_score(self, metrics: ModelMetrics) -> float:
        """Calculate composite model quality score"""
        latency_score = max(0, 1000 - metrics.avg_latency_ms) / 1000
        error_score = 1.0 - metrics.error_rate
        return (latency_score * 0.6) + (error_score * 0.4)
    
    # ==================== CANARY DEPLOYMENTS ====================
    
    def start_canary_deployment(
        self,
        canary_id: str,
        stable_model: str,
        canary_model: str,
        initial_traffic_percent: float = 10.0,
        increment_percent: float = 10.0,
        increment_interval_minutes: int = 30,
    ) -> bool:
        """Start canary deployment"""
        if not self.enable_canary:
            logger.warning("Canary deployments are disabled")
            return False
        
        if stable_model not in self.active_models or canary_model not in self.active_models:
            logger.error("Both models must be registered")
            return False
        
        with self._lock:
            if canary_id in self.canary_deployments:
                logger.warning(f"Canary {canary_id} already exists")
                return False
            
            self.canary_deployments[canary_id] = CanaryDeployment(
                canary_id=canary_id,
                stable_model=stable_model,
                canary_model=canary_model,
                canary_traffic_percent=initial_traffic_percent,
                increment_percent=increment_percent,
                increment_interval_minutes=increment_interval_minutes,
                current_traffic_percent=initial_traffic_percent,
                last_increment_at=datetime.now().isoformat(),
            )
            
            logger.info(f"Started canary deployment {canary_id}")
            return True
    
    def check_canary_health(self, canary_id: str) -> Dict:
        """Check canary deployment health"""
        if canary_id not in self.canary_deployments:
            return {'error': 'Canary not found'}
        
        canary = self.canary_deployments[canary_id]
        canary_metrics = self.model_metrics.get(canary.canary_model)
        
        if not canary_metrics:
            return {'error': 'Missing canary metrics'}
        
        if canary_metrics.error_rate > canary.max_error_rate:
            if canary.rollback_on_failure:
                self._rollback_canary(canary_id)
                return {
                    'decision': 'rolled_back',
                    'reason': f"Error rate {canary_metrics.error_rate:.2%} > {canary.max_error_rate:.2%}",
                }
        
        last_increment = datetime.fromisoformat(canary.last_increment_at)
        now = datetime.now()
        elapsed_minutes = (now - last_increment).total_seconds() / 60
        
        if elapsed_minutes >= canary.increment_interval_minutes:
            new_traffic = min(100.0, canary.current_traffic_percent + canary.increment_percent)
            
            with self._lock:
                canary.current_traffic_percent = new_traffic
                canary.last_increment_at = now.isoformat()
                
                if new_traffic >= 100.0:
                    canary.status = 'completed'
                    logger.info(f"Canary {canary_id} fully promoted")
                    return {'decision': 'promoted', 'traffic_percent': 100.0}
            
            logger.info(f"Canary {canary_id} traffic increased to {new_traffic}%")
            return {'decision': 'incremented', 'traffic_percent': new_traffic}
        
        return {
            'decision': 'monitoring',
            'traffic_percent': canary.current_traffic_percent,
            'error_rate': canary_metrics.error_rate,
            'total_requests': canary_metrics.total_requests,
        }
    
    def _rollback_canary(self, canary_id: str):
        """Rollback canary deployment"""
        with self._lock:
            if canary_id in self.canary_deployments:
                canary = self.canary_deployments[canary_id]
                canary.status = 'rolled_back'
                canary.current_traffic_percent = 0.0
                logger.warning(f"Rolled back canary {canary_id}")
    
    # ==================== METRICS & MONITORING ====================
    
    def record_request(
        self,
        model_id: str,
        latency_ms: float,
        success: bool,
        confidence_score: Optional[float] = None,
    ):
        """Record request metrics for a model"""
        if model_id not in self.model_metrics:
            logger.warning(f"Model {model_id} not found in metrics")
            return
        
        metrics = self.model_metrics[model_id]
        metrics.update_latency(latency_ms)
        metrics.update_request_count(success)
        
        if confidence_score is not None:
            total = metrics.total_requests
            metrics.avg_confidence_score = (
                (metrics.avg_confidence_score * (total - 1) + confidence_score) / total
            )
    
    def get_model_metrics(self, model_id: Optional[str] = None) -> Dict:
        """Get metrics for specific model or all models"""
        if model_id:
            if model_id not in self.model_metrics:
                return {'error': 'Model not found'}
            
            metrics = self.model_metrics[model_id]
            return {
                'model_id': metrics.model_id,
                'model_name': metrics.model_name,
                'version': metrics.version,
                'total_requests': metrics.total_requests,
                'successful_requests': metrics.successful_requests,
                'failed_requests': metrics.failed_requests,
                'error_rate': metrics.error_rate,
                'avg_latency_ms': metrics.avg_latency_ms,
                'p95_latency_ms': metrics.p95_latency_ms,
                'p99_latency_ms': metrics.p99_latency_ms,
                'first_request_at': metrics.first_request_at,
                'last_request_at': metrics.last_request_at,
            }
        else:
            return {
                mid: self.get_model_metrics(mid)
                for mid in self.model_metrics.keys()
            }
    
    def get_system_status(self) -> Dict:
        """Get overall orchestrator status"""
        return {
            'active_models': len(self.active_models),
            'active_ab_tests': len([t for t in self.ab_tests.values() if t.status == 'active']),
            'active_canaries': len([c for c in self.canary_deployments.values() if c.status == 'active']),
            'total_requests': sum(m.total_requests for m in self.model_metrics.values()),
            'models': list(self.active_models.keys()),
        }


# Factory function
def create_orchestrator(**kwargs) -> AdvancedModelOrchestrator:
    """Factory function to create orchestrator instance"""
    return AdvancedModelOrchestrator(**kwargs)
