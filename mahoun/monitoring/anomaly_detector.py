"""
Anomaly Detection System
=========================

Statistical anomaly detection for performance monitoring.
"""


import logging
from typing import List, Dict, Optional, Tuple
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AnomalyAlert:
    """Anomaly alert"""
    metric_name: str
    current_value: float
    expected_range: Tuple[float, float]
    severity: str  # 'low', 'medium', 'high', 'critical'
    timestamp: datetime
    message: str
    z_score: float


class StatisticalAnomalyDetector:
    """
    Statistical anomaly detection using Z-score and IQR methods
    
    Features:
    - Z-score based detection
    - IQR (Interquartile Range) based detection
    - Configurable sensitivity
    - Alert generation
    - Historical tracking
    """
    
    def __init__(
        self,
        window_size: int = 100,
        z_threshold: float = 3.0,
        iqr_multiplier: float = 1.5,
        min_samples: int = 10
    ):
        """
        Initialize anomaly detector
        
        Args:
            window_size: Size of rolling window for statistics
            z_threshold: Z-score threshold for anomaly (typically 2-3)
            iqr_multiplier: IQR multiplier for outlier detection (typically 1.5)
            min_samples: Minimum samples before detection starts
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.iqr_multiplier = iqr_multiplier
        self.min_samples = min_samples
        
        # Metric history
        self.metric_history: Dict[str, deque] = {}
        
        # Alert history
        self.alert_history: List[AnomalyAlert] = []
        
        logger.info(
            f"Initialized StatisticalAnomalyDetector: "
            f"window={window_size}, z_threshold={z_threshold}"
        )
    
    def add_metric(self, metric_name: str, value: float):
        """
        Add metric value to history
        
        Args:
            metric_name: Name of metric
            value: Metric value
        """
        if metric_name not in self.metric_history:
            self.metric_history[metric_name] = deque(maxlen=self.window_size)
        
        self.metric_history[metric_name].append(value)
    
    def detect_anomaly_zscore(
        self,
        metric_name: str,
        value: float
    ) -> Optional[AnomalyAlert]:
        """
        Detect anomaly using Z-score method
        
        Args:
            metric_name: Name of metric
            value: Current value
            
        Returns:
            AnomalyAlert if anomaly detected, None otherwise
        """
        if metric_name not in self.metric_history:
            return None
        
        history = list(self.metric_history[metric_name])
        
        if len(history) < self.min_samples:
            return None
        
        # Compute statistics
        mean = np.mean(history)
        std = np.std(history)
        
        if std == 0:
            return None
        
        # Compute Z-score
        z_score = abs((value - mean) / std)
        
        # Check if anomaly
        if z_score > self.z_threshold:
            # Determine severity
            if z_score > 5.0:
                severity = 'critical'
            elif z_score > 4.0:
                severity = 'high'
            elif z_score > 3.5:
                severity = 'medium'
            else:
                severity = 'low'
            
            # Expected range (mean ± threshold * std)
            expected_range = (
                mean - self.z_threshold * std,
                mean + self.z_threshold * std
            )
            
            alert = AnomalyAlert(
                metric_name=metric_name,
                current_value=value,
                expected_range=expected_range,
                severity=severity,
                timestamp=datetime.now(),
                message=(
                    f"Anomaly detected in {metric_name}: "
                    f"value={value:.4f}, expected=[{expected_range[0]:.4f}, {expected_range[1]:.4f}], "
                    f"z_score={z_score:.2f}"
                ),
                z_score=z_score
            )
            
            self.alert_history.append(alert)
            
            logger.warning(alert.message)
            
            return alert
        
        return None
    
    def detect_anomaly_iqr(
        self,
        metric_name: str,
        value: float
    ) -> Optional[AnomalyAlert]:
        """
        Detect anomaly using IQR (Interquartile Range) method
        
        Args:
            metric_name: Name of metric
            value: Current value
            
        Returns:
            AnomalyAlert if anomaly detected, None otherwise
        """
        if metric_name not in self.metric_history:
            return None
        
        history = list(self.metric_history[metric_name])
        
        if len(history) < self.min_samples:
            return None
        
        # Compute quartiles
        q1 = np.percentile(history, 25)
        q3 = np.percentile(history, 75)
        iqr = q3 - q1
        
        if iqr == 0:
            return None
        
        # Compute bounds
        lower_bound = q1 - self.iqr_multiplier * iqr
        upper_bound = q3 + self.iqr_multiplier * iqr
        
        # Check if anomaly
        if value < lower_bound or value > upper_bound:
            # Determine severity based on distance from bounds
            if value < lower_bound:
                distance = (lower_bound - value) / iqr
            else:
                distance = (value - upper_bound) / iqr
            
            if distance > 3.0:
                severity = 'critical'
            elif distance > 2.0:
                severity = 'high'
            elif distance > 1.0:
                severity = 'medium'
            else:
                severity = 'low'
            
            # Compute pseudo z-score for consistency
            median = np.median(history)
            mad = np.median(np.abs(np.array(history) - median))
            z_score = abs((value - median) / (mad * 1.4826)) if mad > 0 else 0
            
            alert = AnomalyAlert(
                metric_name=metric_name,
                current_value=value,
                expected_range=(lower_bound, upper_bound),
                severity=severity,
                timestamp=datetime.now(),
                message=(
                    f"Anomaly detected in {metric_name} (IQR): "
                    f"value={value:.4f}, expected=[{lower_bound:.4f}, {upper_bound:.4f}]"
                ),
                z_score=z_score
            )
            
            self.alert_history.append(alert)
            
            logger.warning(alert.message)
            
            return alert
        
        return None
    
    def detect_anomaly(
        self,
        metric_name: str,
        value: float,
        method: str = 'zscore'
    ) -> Optional[AnomalyAlert]:
        """
        Detect anomaly using specified method
        
        Args:
            metric_name: Name of metric
            value: Current value
            method: Detection method ('zscore' or 'iqr')
            
        Returns:
            AnomalyAlert if anomaly detected, None otherwise
        """
        # Add to history
        self.add_metric(metric_name, value)
        
        # Detect anomaly
        if method == 'zscore':
            return self.detect_anomaly_zscore(metric_name, value)
        elif method == 'iqr':
            return self.detect_anomaly_iqr(metric_name, value)
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def get_metric_statistics(self, metric_name: str) -> Dict[str, float]:
        """
        Get statistics for a metric
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Dictionary of statistics
        """
        if metric_name not in self.metric_history:
            return {}
        
        history = list(self.metric_history[metric_name])
        
        if not history:
            return {}
        
        return {
            'mean': np.mean(history),
            'std': np.std(history),
            'min': np.min(history),
            'max': np.max(history),
            'median': np.median(history),
            'q1': np.percentile(history, 25),
            'q3': np.percentile(history, 75),
            'count': len(history)
        }
    
    def get_recent_alerts(
        self,
        metric_name: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 10
    ) -> List[AnomalyAlert]:
        """
        Get recent alerts
        
        Args:
            metric_name: Filter by metric name (optional)
            severity: Filter by severity (optional)
            limit: Maximum number of alerts to return
            
        Returns:
            List of recent alerts
        """
        alerts = self.alert_history
        
        # Filter by metric name
        if metric_name:
            alerts = [a for a in alerts if a.metric_name == metric_name]
        
        # Filter by severity
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        # Return most recent
        return alerts[-limit:]
    
    def clear_history(self, metric_name: Optional[str] = None):
        """
        Clear metric history
        
        Args:
            metric_name: Metric to clear (if None, clear all)
        """
        if metric_name:
            if metric_name in self.metric_history:
                self.metric_history[metric_name].clear()
        else:
            self.metric_history.clear()
            self.alert_history.clear()
        
        logger.info(f"Cleared history for {metric_name or 'all metrics'}")


class PerformanceDegradationDetector:
    """
    Detect performance degradation over time
    
    Features:
    - Trend analysis
    - Degradation detection
    - Alert on sustained degradation
    """
    
    def __init__(
        self,
        degradation_threshold: float = 0.1,  # 10% degradation
        window_size: int = 50,
        min_samples: int = 10
    ):
        """
        Initialize degradation detector
        
        Args:
            degradation_threshold: Threshold for degradation (0.1 = 10%)
            window_size: Window size for trend analysis
            min_samples: Minimum samples before detection
        """
        self.degradation_threshold = degradation_threshold
        self.window_size = window_size
        self.min_samples = min_samples
        
        self.metric_history: Dict[str, deque] = {}
        
        logger.info(
            f"Initialized PerformanceDegradationDetector: "
            f"threshold={degradation_threshold:.1%}"
        )
    
    def add_metric(self, metric_name: str, value: float):
        """Add metric value"""
        if metric_name not in self.metric_history:
            self.metric_history[metric_name] = deque(maxlen=self.window_size)
        
        self.metric_history[metric_name].append(value)
    
    def detect_degradation(
        self,
        metric_name: str,
        value: float,
        higher_is_better: bool = True
    ) -> Optional[AnomalyAlert]:
        """
        Detect performance degradation
        
        Args:
            metric_name: Name of metric
            value: Current value
            higher_is_better: Whether higher values are better
            
        Returns:
            AnomalyAlert if degradation detected
        """
        # Add to history
        self.add_metric(metric_name, value)
        
        history = list(self.metric_history[metric_name])
        
        if len(history) < self.min_samples:
            return None
        
        # Compute baseline (first half of window)
        mid_point = len(history) // 2
        baseline = np.mean(history[:mid_point])
        recent = np.mean(history[mid_point:])
        
        if baseline == 0:
            return None
        
        # Compute degradation
        if higher_is_better:
            degradation = (baseline - recent) / baseline
        else:
            degradation = (recent - baseline) / baseline
        
        # Check if degraded
        if degradation > self.degradation_threshold:
            # Determine severity
            if degradation > 0.3:
                severity = 'critical'
            elif degradation > 0.2:
                severity = 'high'
            elif degradation > 0.15:
                severity = 'medium'
            else:
                severity = 'low'
            
            alert = AnomalyAlert(
                metric_name=metric_name,
                current_value=value,
                expected_range=(baseline * 0.9, baseline * 1.1),
                severity=severity,
                timestamp=datetime.now(),
                message=(
                    f"Performance degradation detected in {metric_name}: "
                    f"degraded by {degradation:.1%} (baseline={baseline:.4f}, recent={recent:.4f})"
                ),
                z_score=degradation / self.degradation_threshold
            )
            
            logger.warning(alert.message)
            
            return alert
        
        return None


class AnomalyDetectionSystem:
    """
    Combined anomaly detection system
    
    Combines:
    - Statistical anomaly detection
    - Performance degradation detection
    - Alert management
    """
    
    def __init__(
        self,
        enable_statistical: bool = True,
        enable_degradation: bool = True,
        **kwargs
    ):
        """
        Initialize anomaly detection system
        
        Args:
            enable_statistical: Enable statistical detection
            enable_degradation: Enable degradation detection
            **kwargs: Additional arguments for detectors
        """
        self.enable_statistical = enable_statistical
        self.enable_degradation = enable_degradation
        
        self.statistical_detector = (
            StatisticalAnomalyDetector(**kwargs)
            if enable_statistical
            else None
        )
        
        self.degradation_detector = (
            PerformanceDegradationDetector(**kwargs)
            if enable_degradation
            else None
        )
        
        logger.info(
            f"Initialized AnomalyDetectionSystem: "
            f"statistical={enable_statistical}, degradation={enable_degradation}"
        )
    
    def check_metric(
        self,
        metric_name: str,
        value: float,
        higher_is_better: bool = True
    ) -> List[AnomalyAlert]:
        """
        Check metric for anomalies
        
        Args:
            metric_name: Name of metric
            value: Current value
            higher_is_better: Whether higher values are better
            
        Returns:
            List of alerts (if any)
        """
        alerts = []
        
        # Statistical detection
        if self.enable_statistical and self.statistical_detector:
            alert = self.statistical_detector.detect_anomaly(metric_name, value)
            if alert:
                alerts.append(alert)
        
        # Degradation detection
        if self.enable_degradation and self.degradation_detector:
            alert = self.degradation_detector.detect_degradation(
                metric_name,
                value,
                higher_is_better
            )
            if alert:
                alerts.append(alert)
        
        return alerts
    
    def get_all_alerts(
        self,
        severity: Optional[str] = None,
        limit: int = 20
    ) -> List[AnomalyAlert]:
        """Get all recent alerts"""
        alerts = []
        
        if self.statistical_detector:
            alerts.extend(
                self.statistical_detector.get_recent_alerts(
                    severity=severity,
                    limit=limit
                )
            )
        
        # Sort by timestamp
        alerts.sort(key=lambda x: x.timestamp, reverse=True)
        
        return alerts[:limit]
