"""
Rolling Statistics
==================

Compute rolling statistics over configurable time windows.
"""


import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesPoint:
    """Time series data point"""
    timestamp: datetime
    value: float


@dataclass
class RollingStatistics:
    """Rolling statistics result"""
    mean: float
    std: float
    min: float
    max: float
    median: float
    p25: float  # 25th percentile
    p75: float  # 75th percentile
    p95: float  # 95th percentile
    p99: float  # 99th percentile
    count: int
    window_start: datetime
    window_end: datetime


class RollingStatsCalculator:
    """
    Calculate rolling statistics over time windows
    
    Features:
    - Time-based windows (seconds, minutes, hours)
    - Count-based windows (last N samples)
    - Multiple percentiles
    - Efficient computation
    """
    
    def __init__(
        self,
        window_type: str = 'time',  # 'time' or 'count'
        window_size: int = 3600,  # seconds or count
        max_history: int = 10000
    ):
        """
        Initialize rolling stats calculator
        
        Args:
            window_type: Type of window ('time' or 'count')
            window_size: Window size (seconds for time, count for count)
            max_history: Maximum history to keep
        """
        self.window_type = window_type
        self.window_size = window_size
        self.max_history = max_history
        
        # Metric history
        self.metric_history: Dict[str, deque] = {}
        
        logger.info(
            f"Initialized RollingStatsCalculator: "
            f"type={window_type}, size={window_size}"
        )
    
    def add_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None
    ):
        """
        Add metric value
        
        Args:
            metric_name: Name of metric
            value: Metric value
            timestamp: Timestamp (default: now)
        """
        if metric_name not in self.metric_history:
            self.metric_history[metric_name] = deque(maxlen=self.max_history)
        
        if timestamp is None:
            timestamp = datetime.now()
        
        point = TimeSeriesPoint(timestamp=timestamp, value=value)
        self.metric_history[metric_name].append(point)
    
    def _get_window_data(
        self,
        metric_name: str,
        window_size: Optional[int] = None
    ) -> List[TimeSeriesPoint]:
        """
        Get data points within window
        
        Args:
            metric_name: Name of metric
            window_size: Override window size (optional)
            
        Returns:
            List of data points in window
        """
        if metric_name not in self.metric_history:
            return []
        
        history = list(self.metric_history[metric_name])
        
        if not history:
            return []
        
        window_size = window_size or self.window_size
        
        if self.window_type == 'count':
            # Last N samples
            return history[-window_size:]
        
        elif self.window_type == 'time':
            # Last N seconds
            cutoff_time = datetime.now() - timedelta(seconds=window_size)
            return [p for p in history if p.timestamp >= cutoff_time]
        
        return history
    
    def compute_statistics(
        self,
        metric_name: str,
        window_size: Optional[int] = None
    ) -> Optional[RollingStatistics]:
        """
        Compute rolling statistics
        
        Args:
            metric_name: Name of metric
            window_size: Override window size (optional)
            
        Returns:
            RollingStatistics or None if insufficient data
        """
        data_points = self._get_window_data(metric_name, window_size)
        
        if not data_points:
            return None
        
        values = np.array([p.value for p in data_points])
        
        if len(values) == 0:
            return None
        
        stats = RollingStatistics(
            mean=float(np.mean(values)),
            std=float(np.std(values)),
            min=float(np.min(values)),
            max=float(np.max(values)),
            median=float(np.median(values)),
            p25=float(np.percentile(values, 25)),
            p75=float(np.percentile(values, 75)),
            p95=float(np.percentile(values, 95)),
            p99=float(np.percentile(values, 99)),
            count=len(values),
            window_start=data_points[0].timestamp,
            window_end=data_points[-1].timestamp
        )
        
        return stats
    
    def compute_multiple_windows(
        self,
        metric_name: str,
        window_sizes: List[int]
    ) -> Dict[int, RollingStatistics]:
        """
        Compute statistics for multiple window sizes
        
        Args:
            metric_name: Name of metric
            window_sizes: List of window sizes
            
        Returns:
            Dictionary mapping window size to statistics
        """
        results = {}
        
        for window_size in window_sizes:
            stats = self.compute_statistics(metric_name, window_size)
            if stats:
                results[window_size] = stats
        
        return results
    
    def get_trend(
        self,
        metric_name: str,
        window_size: Optional[int] = None
    ) -> Optional[float]:
        """
        Compute trend (slope) of metric over window
        
        Args:
            metric_name: Name of metric
            window_size: Override window size (optional)
            
        Returns:
            Trend (slope) or None
        """
        data_points = self._get_window_data(metric_name, window_size)
        
        if len(data_points) < 2:
            return None
        
        # Convert timestamps to seconds since first point
        t0 = data_points[0].timestamp
        x = np.array([(p.timestamp - t0).total_seconds() for p in data_points])
        y = np.array([p.value for p in data_points])
        
        # Linear regression
        if len(x) > 1:
            slope, _ = np.polyfit(x, y, 1)
            return float(slope)
        
        return None
    
    def get_rate_of_change(
        self,
        metric_name: str,
        window_size: Optional[int] = None
    ) -> Optional[float]:
        """
        Compute rate of change (percentage change per second)
        
        Args:
            metric_name: Name of metric
            window_size: Override window size (optional)
            
        Returns:
            Rate of change or None
        """
        data_points = self._get_window_data(metric_name, window_size)
        
        if len(data_points) < 2:
            return None
        
        first_value = data_points[0].value
        last_value = data_points[-1].value
        
        if first_value == 0:
            return None
        
        time_diff = (data_points[-1].timestamp - data_points[0].timestamp).total_seconds()
        
        if time_diff == 0:
            return None
        
        # Percentage change per second
        pct_change = ((last_value - first_value) / first_value) * 100
        rate = pct_change / time_diff
        
        return float(rate)
    
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
        
        logger.info(f"Cleared history for {metric_name or 'all metrics'}")


class MultiWindowStatsTracker:
    """
    Track statistics across multiple time windows simultaneously
    
    Useful for monitoring at different granularities:
    - Last minute
    - Last 5 minutes
    - Last hour
    - Last day
    """
    
    def __init__(
        self,
        window_configs: Optional[List[Tuple[str, int]]] = None
    ):
        """
        Initialize multi-window tracker
        
        Args:
            window_configs: List of (name, window_size) tuples
                           Default: [('1m', 60), ('5m', 300), ('1h', 3600), ('1d', 86400)]
        """
        if window_configs is None:
            window_configs = [
                ('1m', 60),
                ('5m', 300),
                ('1h', 3600),
                ('1d', 86400)
            ]
        
        self.window_configs = window_configs
        
        # Create calculator for each window
        self.calculators: Dict[str, RollingStatsCalculator] = {}
        
        for name, window_size in window_configs:
            self.calculators[name] = RollingStatsCalculator(
                window_type='time',
                window_size=window_size
            )
        
        logger.info(
            f"Initialized MultiWindowStatsTracker with {len(window_configs)} windows"
        )
    
    def add_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None
    ):
        """
        Add metric to all windows
        
        Args:
            metric_name: Name of metric
            value: Metric value
            timestamp: Timestamp (default: now)
        """
        for calculator in self.calculators.values():
            calculator.add_metric(metric_name, value, timestamp)
    
    def get_all_statistics(
        self,
        metric_name: str
    ) -> Dict[str, RollingStatistics]:
        """
        Get statistics for all windows
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Dictionary mapping window name to statistics
        """
        results = {}
        
        for window_name, calculator in self.calculators.items():
            stats = calculator.compute_statistics(metric_name)
            if stats:
                results[window_name] = stats
        
        return results
    
    def get_summary(self, metric_name: str) -> Dict[str, Dict[str, float]]:
        """
        Get summary statistics for all windows
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Nested dictionary with statistics
        """
        summary = {}
        
        for window_name, calculator in self.calculators.items():
            stats = calculator.compute_statistics(metric_name)
            if stats:
                summary[window_name] = {
                    'mean': stats.mean,
                    'std': stats.std,
                    'min': stats.min,
                    'max': stats.max,
                    'p95': stats.p95,
                    'count': stats.count
                }
        
        return summary
    
    def get_trends(self, metric_name: str) -> Dict[str, float]:
        """
        Get trends for all windows
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Dictionary mapping window name to trend
        """
        trends = {}
        
        for window_name, calculator in self.calculators.items():
            trend = calculator.get_trend(metric_name)
            if trend is not None:
                trends[window_name] = trend
        
        return trends
    
    def clear_all(self):
        """Clear all history"""
        for calculator in self.calculators.values():
            calculator.clear_history()
        
        logger.info("Cleared all window histories")


# Convenience function
def create_default_tracker() -> MultiWindowStatsTracker:
    """Create tracker with default windows"""
    return MultiWindowStatsTracker()
