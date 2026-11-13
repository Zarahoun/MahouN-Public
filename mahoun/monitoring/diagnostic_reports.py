"""
Diagnostic Report Generator
============================

Automatically generate diagnostic reports on anomalies and performance issues.
"""


import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import json

from mahoun.monitoring.anomaly_detector import AnomalyAlert, AnomalyDetectionSystem
from mahoun.monitoring.rolling_stats import RollingStatistics, MultiWindowStatsTracker
logger = logging.getLogger(__name__)


@dataclass
class DiagnosticReport:
    """Diagnostic report"""
    report_id: str
    timestamp: datetime
    trigger: str  # 'anomaly', 'degradation', 'manual'
    severity: str
    affected_metrics: List[str]
    summary: str
    details: Dict[str, Any]
    recommendations: List[str]
    visualizations: Optional[Dict[str, Any]] = None


class DiagnosticReportGenerator:
    """
    Generate diagnostic reports automatically
    
    Features:
    - Anomaly-triggered reports
    - Performance degradation reports
    - Root cause analysis
    - Actionable recommendations
    - Visualization data
    """
    
    def __init__(
        self,
        anomaly_detector: Optional[AnomalyDetectionSystem] = None,
        stats_tracker: Optional[MultiWindowStatsTracker] = None
    ):
        """
        Initialize report generator
        
        Args:
            anomaly_detector: Anomaly detection system
            stats_tracker: Statistics tracker
        """
        self.anomaly_detector = anomaly_detector
        self.stats_tracker = stats_tracker
        
        self.report_history: List[DiagnosticReport] = []
        
        logger.info("Initialized DiagnosticReportGenerator")
    
    def generate_anomaly_report(
        self,
        alerts: List[AnomalyAlert]
    ) -> DiagnosticReport:
        """
        Generate report for anomaly alerts
        
        Args:
            alerts: List of anomaly alerts
            
        Returns:
            DiagnosticReport
        """
        if not alerts:
            raise ValueError("No alerts provided")
        
        # Determine overall severity
        severity_order = ['low', 'medium', 'high', 'critical']
        max_severity = max(
            alerts,
            key=lambda a: severity_order.index(a.severity)
        ).severity
        
        # Get affected metrics
        affected_metrics = list(set(a.metric_name for a in alerts))
        
        # Generate summary
        summary = self._generate_anomaly_summary(alerts)
        
        # Generate details
        details = {
            'alerts': [asdict(a) for a in alerts],
            'alert_count': len(alerts),
            'affected_metrics': affected_metrics,
            'severity_distribution': self._get_severity_distribution(alerts)
        }
        
        # Add statistics if available
        if self.stats_tracker:
            details['statistics'] = {}
            for metric in affected_metrics:
                stats = self.stats_tracker.get_all_statistics(metric)
                if stats:
                    details['statistics'][metric] = {
                        window: {
                            'mean': s.mean,
                            'std': s.std,
                            'p95': s.p95
                        }
                        for window, s in stats.items()
                    }
        
        # Generate recommendations
        recommendations = self._generate_recommendations(alerts)
        
        # Generate visualizations data
        visualizations = self._generate_visualization_data(alerts)
        
        report = DiagnosticReport(
            report_id=f"anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(),
            trigger='anomaly',
            severity=max_severity,
            affected_metrics=affected_metrics,
            summary=summary,
            details=details,
            recommendations=recommendations,
            visualizations=visualizations
        )
        
        self.report_history.append(report)
        
        logger.info(f"Generated anomaly report: {report.report_id}")
        
        return report
    
    def generate_performance_report(
        self,
        metric_name: str,
        current_value: float,
        baseline_value: float,
        degradation_pct: float
    ) -> DiagnosticReport:
        """
        Generate report for performance degradation
        
        Args:
            metric_name: Name of metric
            current_value: Current value
            baseline_value: Baseline value
            degradation_pct: Degradation percentage
            
        Returns:
            DiagnosticReport
        """
        # Determine severity
        if degradation_pct > 30:
            severity = 'critical'
        elif degradation_pct > 20:
            severity = 'high'
        elif degradation_pct > 10:
            severity = 'medium'
        else:
            severity = 'low'
        
        # Generate summary
        summary = (
            f"Performance degradation detected in {metric_name}: "
            f"degraded by {degradation_pct:.1f}% "
            f"(baseline={baseline_value:.4f}, current={current_value:.4f})"
        )
        
        # Generate details
        details = {
            'metric_name': metric_name,
            'current_value': current_value,
            'baseline_value': baseline_value,
            'degradation_pct': degradation_pct,
            'absolute_change': current_value - baseline_value
        }
        
        # Add statistics if available
        if self.stats_tracker:
            stats = self.stats_tracker.get_all_statistics(metric_name)
            if stats:
                details['statistics'] = {
                    window: {
                        'mean': s.mean,
                        'std': s.std,
                        'trend': self.stats_tracker.calculators[window].get_trend(metric_name)
                    }
                    for window, s in stats.items()
                }
        
        # Generate recommendations
        recommendations = [
            f"Investigate recent changes to {metric_name}",
            "Check system resources (CPU, memory, disk)",
            "Review recent deployments or configuration changes",
            "Compare with historical baselines",
            "Consider rolling back recent changes if degradation persists"
        ]
        
        report = DiagnosticReport(
            report_id=f"degradation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(),
            trigger='degradation',
            severity=severity,
            affected_metrics=[metric_name],
            summary=summary,
            details=details,
            recommendations=recommendations
        )
        
        self.report_history.append(report)
        
        logger.info(f"Generated performance report: {report.report_id}")
        
        return report
    
    def _generate_anomaly_summary(self, alerts: List[AnomalyAlert]) -> str:
        """Generate summary for anomaly alerts"""
        if len(alerts) == 1:
            alert = alerts[0]
            return (
                f"Anomaly detected in {alert.metric_name}: "
                f"value={alert.current_value:.4f}, "
                f"expected=[{alert.expected_range[0]:.4f}, {alert.expected_range[1]:.4f}], "
                f"severity={alert.severity}"
            )
        else:
            metrics = list(set(a.metric_name for a in alerts))
            return (
                f"{len(alerts)} anomalies detected across {len(metrics)} metrics: "
                f"{', '.join(metrics[:3])}"
                f"{'...' if len(metrics) > 3 else ''}"
            )
    
    def _get_severity_distribution(self, alerts: List[AnomalyAlert]) -> Dict[str, int]:
        """Get distribution of severities"""
        distribution = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        
        for alert in alerts:
            distribution[alert.severity] += 1
        
        return distribution
    
    def _generate_recommendations(self, alerts: List[AnomalyAlert]) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Get unique metrics
        metrics = list(set(a.metric_name for a in alerts))
        
        # General recommendations
        recommendations.append(
            f"Investigate {len(metrics)} affected metric(s): {', '.join(metrics[:3])}"
        )
        
        # Severity-based recommendations
        critical_alerts = [a for a in alerts if a.severity == 'critical']
        if critical_alerts:
            recommendations.append(
                "⚠️ CRITICAL: Immediate action required - "
                "consider rolling back recent changes"
            )
        
        high_alerts = [a for a in alerts if a.severity == 'high']
        if high_alerts:
            recommendations.append(
                "HIGH: Review system logs and recent deployments"
            )
        
        # Metric-specific recommendations
        if any('latency' in a.metric_name.lower() for a in alerts):
            recommendations.append(
                "Check for network issues, database slow queries, or resource contention"
            )
        
        if any('error' in a.metric_name.lower() for a in alerts):
            recommendations.append(
                "Review error logs and exception traces"
            )
        
        if any('memory' in a.metric_name.lower() for a in alerts):
            recommendations.append(
                "Check for memory leaks or increased load"
            )
        
        # Add monitoring recommendation
        recommendations.append(
            "Continue monitoring for 15-30 minutes to confirm if issue persists"
        )
        
        return recommendations
    
    def _generate_visualization_data(
        self,
        alerts: List[AnomalyAlert]
    ) -> Dict[str, Any]:
        """Generate data for visualizations"""
        viz_data = {
            'severity_chart': {
                'type': 'pie',
                'data': self._get_severity_distribution(alerts)
            },
            'timeline': {
                'type': 'timeline',
                'data': [
                    {
                        'timestamp': a.timestamp.isoformat(),
                        'metric': a.metric_name,
                        'severity': a.severity,
                        'value': a.current_value
                    }
                    for a in alerts
                ]
            }
        }
        
        # Add time series data if available
        if self.stats_tracker:
            viz_data['time_series'] = {}
            
            for metric in set(a.metric_name for a in alerts):
                stats = self.stats_tracker.get_all_statistics(metric)
                if stats:
                    viz_data['time_series'][metric] = {
                        window: {
                            'mean': s.mean,
                            'std': s.std,
                            'min': s.min,
                            'max': s.max
                        }
                        for window, s in stats.items()
                    }
        
        return viz_data
    
    def export_report_markdown(self, report: DiagnosticReport) -> str:
        """
        Export report as Markdown
        
        Args:
            report: Diagnostic report
            
        Returns:
            Markdown string
        """
        md = [
            f"# Diagnostic Report: {report.report_id}",
            "",
            f"**Generated**: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Trigger**: {report.trigger}",
            f"**Severity**: {report.severity.upper()}",
            "",
            "## Summary",
            "",
            report.summary,
            "",
            "## Affected Metrics",
            ""
        ]
        
        for metric in report.affected_metrics:
            md.append(f"- {metric}")
        
        md.extend([
            "",
            "## Details",
            "",
            "```json",
            json.dumps(report.details, indent=2, default=str),
            "```",
            "",
            "## Recommendations",
            ""
        ])
        
        for i, rec in enumerate(report.recommendations, 1):
            md.append(f"{i}. {rec}")
        
        md.append("")
        
        return "\n".join(md)
    
    def export_report_json(self, report: DiagnosticReport) -> str:
        """
        Export report as JSON
        
        Args:
            report: Diagnostic report
            
        Returns:
            JSON string
        """
        report_dict = asdict(report)
        
        # Convert datetime to string
        report_dict['timestamp'] = report.timestamp.isoformat()
        
        return json.dumps(report_dict, indent=2, default=str)
    
    def get_recent_reports(
        self,
        limit: int = 10,
        severity: Optional[str] = None
    ) -> List[DiagnosticReport]:
        """
        Get recent reports
        
        Args:
            limit: Maximum number of reports
            severity: Filter by severity (optional)
            
        Returns:
            List of reports
        """
        reports = self.report_history
        
        if severity:
            reports = [r for r in reports if r.severity == severity]
        
        return reports[-limit:]
    
    def clear_history(self):
        """Clear report history"""
        self.report_history.clear()
        logger.info("Cleared report history")


# Convenience function
def create_report_generator(
    anomaly_detector: Optional[AnomalyDetectionSystem] = None,
    stats_tracker: Optional[MultiWindowStatsTracker] = None
) -> DiagnosticReportGenerator:
    """Create diagnostic report generator"""
    return DiagnosticReportGenerator(anomaly_detector, stats_tracker)
