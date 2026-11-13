"""
Monitoring module for Mahoun platform.

Provides enterprise-grade monitoring with Prometheus metrics,
SLA tracking, legal-specific analytics, and alerting.
"""

from mahoun.monitoring.legal_metrics import (
    legal_monitoring,
    UltraProfessionalLegalMonitoring,
    LegalMetricType,
    track_legal_query_decorator,
)
from mahoun.monitoring.alerting import (
    AlertingSystem,
    Alert,
    AlertSeverity,
    AlertChannel,
    AlertRule,
    get_alerting_system,
    send_alert,
)

__all__ = [
    # Legal monitoring
    "legal_monitoring",
    "UltraProfessionalLegalMonitoring",
    "LegalMetricType",
    "track_legal_query_decorator",
    # Alerting
    "AlertingSystem",
    "Alert",
    "AlertSeverity",
    "AlertChannel",
    "AlertRule",
    "get_alerting_system",
    "send_alert",
]
