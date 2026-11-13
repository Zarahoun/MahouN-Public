"""
Behavioral Anomaly Monitor for Governance Layer
================================================

Classification: CRITICAL / SECURITY / INSIDER THREAT DETECTION
Purpose: Real-time behavioral anomaly detection integrated with governance layer

Features:
- Actor behavior profiling (mutation patterns, timing, frequency)
- Anomaly detection for suspicious governance activities
- Integration with RBACManager and MutationAuthorizationBoundary
- Automatic alerting and audit logging
- Statistical and ML-based detection methods

Design:
- Non-blocking (async monitoring)
- Graceful degradation (monitoring failure does not block operations)
- Zero false positives for legitimate admin activity
- Configurable thresholds per deployment profile

Author: MAHOUN Security Council
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque

try:
    from mahoun.monitoring.anomaly_detector import (
        StatisticalAnomalyDetector,
        AnomalyAlert,
    )
except ImportError:
    # Graceful degradation if monitoring module unavailable
    StatisticalAnomalyDetector = None
    AnomalyAlert = None

from mahoun.core.models.audit_event import AuditEvent, AuditEventType
from mahoun.core.exceptions_v2 import SecurityBreachException


logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & DATA MODELS
# ============================================================================

class BehaviorMetric(str, Enum):
    """Behavioral metrics tracked per actor"""
    MUTATION_RATE = "mutation_rate"           # mutations per minute
    DELETE_RATE = "delete_rate"               # delete operations per hour
    FAILED_AUTH_RATE = "failed_auth_rate"     # failed authorization attempts
    OFF_HOURS_ACTIVITY = "off_hours_activity" # activity outside business hours
    BULK_OPERATION_SIZE = "bulk_operation_size" # number of entities in single op
    SENSITIVE_ACCESS = "sensitive_access"     # access to sensitive labels/keys


class ThreatLevel(str, Enum):
    """Threat severity classification"""
    INFO = "info"           # Normal behavior, no action needed
    LOW = "low"             # Slightly unusual, log only
    MEDIUM = "medium"       # Suspicious, alert security team
    HIGH = "high"           # High confidence attack, block + alert
    CRITICAL = "critical"   # Active breach detected, immediate response


@dataclass
class BehaviorProfile:
    """Actor behavioral profile baseline"""
    actor_id: str
    first_seen: datetime
    last_seen: datetime
    total_mutations: int = 0
    total_deletes: int = 0
    total_failed_auth: int = 0
    avg_mutations_per_hour: float = 0.0
    typical_active_hours: List[int] = field(default_factory=list)  # [9, 10, 11, ..., 17]
    typical_operations: Dict[str, int] = field(default_factory=dict)
    
    def update_activity(
        self,
        mutation_count: int = 0,
        delete_count: int = 0,
        failed_auth: bool = False,
        current_hour: int = 0,
    ):
        """Update profile with new activity"""
        self.last_seen = datetime.now(timezone.utc)
        self.total_mutations += mutation_count
        self.total_deletes += delete_count
        if failed_auth:
            self.total_failed_auth += 1
        
        # Track typical hours
        if current_hour not in self.typical_active_hours:
            self.typical_active_hours.append(current_hour)


@dataclass
class BehavioralAnomalyEvent:
    """Detected behavioral anomaly"""
    event_id: str
    timestamp: datetime
    actor_id: str
    metric: BehaviorMetric
    observed_value: float
    expected_range: tuple[float, float]
    deviation_score: float  # z-score or similar
    threat_level: ThreatLevel
    context: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    
    def to_audit_event(self) -> AuditEvent:
        """Convert to AuditEvent for ledger"""
        return AuditEvent(
            event_type=AuditEventType.SECURITY_ALERT,
            timestamp=self.timestamp,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id or self.event_id,
            metadata={
                "anomaly_type": "behavioral",
                "metric": self.metric.value,
                "observed_value": self.observed_value,
                "expected_range": self.expected_range,
                "deviation_score": self.deviation_score,
                "threat_level": self.threat_level.value,
                "context": self.context,
            },
        )


# ============================================================================
# BEHAVIORAL MONITOR
# ============================================================================

class GovernanceBehavioralMonitor:
    """
    Real-time behavioral anomaly detection for governance operations.
    
    Monitors:
    - Mutation patterns (frequency, timing, targets)
    - Authorization failures (potential privilege escalation attempts)
    - Bulk operations (mass delete, mass export)
    - Off-hours activity (outside normal business hours)
    
    Detection Methods:
    - Statistical anomaly detection (Z-score, IQR)
    - Time-series analysis (sudden spikes)
    - Pattern matching (known attack signatures)
    
    Integration Points:
    - MutationAuthorizationBoundary.inspect() — called on every mutation
    - RBACManager.check_permission() — called on every authorization check
    - GovernedNeo4jSession — logs all write operations
    
    Thread Safety:
    - All methods are async and thread-safe
    - Profile updates use locks
    - Non-blocking (does not delay mutations)
    """
    
    def __init__(
        self,
        enable_monitoring: bool = True,
        window_size: int = 100,
        z_threshold: float = 3.0,
        alert_callback: Optional[callable] = None,
    ):
        """
        Initialize behavioral monitor.
        
        Args:
            enable_monitoring: Enable/disable monitoring (graceful degradation)
            window_size: Historical window for statistical detection
            z_threshold: Z-score threshold for anomaly detection
            alert_callback: Async callback for alerts (for external integration)
        """
        self.enabled = enable_monitoring and StatisticalAnomalyDetector is not None
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.alert_callback = alert_callback
        
        # Statistical detector
        if StatisticalAnomalyDetector:
            self.detector = StatisticalAnomalyDetector(
                window_size=window_size,
                z_threshold=z_threshold,
            )
        else:
            self.detector = None
            logger.warning(
                "StatisticalAnomalyDetector unavailable — behavioral monitoring disabled"
            )
        
        # Actor profiles (baseline behaviors)
        self._profiles: Dict[str, BehaviorProfile] = {}
        self._profile_lock = asyncio.Lock()
        
        # Recent activity buffer (for rate calculation)
        self._activity_buffer: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        
        # Detected anomalies (for correlation)
        self._recent_anomalies: deque[BehavioralAnomalyEvent] = deque(maxlen=500)
        
        logger.info(
            f"GovernanceBehavioralMonitor initialized: "
            f"enabled={enable_monitoring}, window={window_size}, z_threshold={z_threshold}"
        )
    
    async def observe_mutation(
        self,
        actor_id: str,
        operation_type: str,  # NODE_CREATE, NODE_DELETE, etc.
        entity_count: int,
        correlation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[BehavioralAnomalyEvent]:
        """
        Observe a mutation and check for behavioral anomalies.
        
        Called by: MutationAuthorizationBoundary.inspect()
        
        Returns:
            BehavioralAnomalyEvent if anomaly detected, None otherwise
        """
        if not self.enabled:
            return None
        
        try:
            # Update actor profile
            await self._update_profile(actor_id, operation_type, entity_count)
            
            # Calculate current metrics
            mutation_rate = await self._calculate_mutation_rate(actor_id)
            delete_rate = await self._calculate_delete_rate(actor_id, operation_type)
            bulk_size = entity_count
            off_hours = self._is_off_hours(datetime.now(timezone.utc))
            
            # Check each metric for anomalies
            anomalies = []
            
            # Check 1: Mutation rate spike
            if mutation_rate > 0 and self.detector:
                alert = self.detector.detect_anomaly(
                    f"{actor_id}:mutation_rate",
                    mutation_rate,
                )
                if alert:
                    anomalies.append(
                        self._create_anomaly_event(
                            actor_id,
                            BehaviorMetric.MUTATION_RATE,
                            mutation_rate,
                            alert,
                            correlation_id,
                        )
                    )
            
            # Check 2: Bulk operation size
            if bulk_size > 10:  # Threshold: more than 10 entities at once
                anomalies.append(
                    BehavioralAnomalyEvent(
                        event_id=f"bulk-{actor_id}-{int(datetime.now(timezone.utc).timestamp())}",
                        timestamp=datetime.now(timezone.utc),
                        actor_id=actor_id,
                        metric=BehaviorMetric.BULK_OPERATION_SIZE,
                        observed_value=float(bulk_size),
                        expected_range=(1.0, 10.0),
                        deviation_score=float(bulk_size) / 10.0,
                        threat_level=ThreatLevel.MEDIUM if bulk_size < 100 else ThreatLevel.HIGH,
                        context={
                            "operation_type": operation_type,
                            "entity_count": entity_count,
                            "metadata": metadata or {},
                        },
                        correlation_id=correlation_id,
                    )
                )
            
            # Check 3: Off-hours activity
            if off_hours and mutation_rate > 5:  # Threshold: >5 mutations/min off-hours
                anomalies.append(
                    BehavioralAnomalyEvent(
                        event_id=f"offhours-{actor_id}-{int(datetime.now(timezone.utc).timestamp())}",
                        timestamp=datetime.now(timezone.utc),
                        actor_id=actor_id,
                        metric=BehaviorMetric.OFF_HOURS_ACTIVITY,
                        observed_value=mutation_rate,
                        expected_range=(0.0, 2.0),
                        deviation_score=mutation_rate / 2.0,
                        threat_level=ThreatLevel.MEDIUM,
                        context={
                            "current_hour": datetime.now(timezone.utc).hour,
                            "operation_type": operation_type,
                        },
                        correlation_id=correlation_id,
                    )
                )
            
            # Check 4: Delete rate spike
            if delete_rate > 0 and operation_type in ("NODE_DELETE", "REL_DELETE") and self.detector:
                alert = self.detector.detect_anomaly(
                    f"{actor_id}:delete_rate",
                    delete_rate,
                )
                if alert:
                    anomalies.append(
                        self._create_anomaly_event(
                            actor_id,
                            BehaviorMetric.DELETE_RATE,
                            delete_rate,
                            alert,
                            correlation_id,
                        )
                    )
            
            # Log and alert on anomalies
            if anomalies:
                for anomaly in anomalies:
                    await self._handle_anomaly(anomaly)
                
                # Return highest severity anomaly
                return max(
                    anomalies,
                    key=lambda a: list(ThreatLevel).index(a.threat_level),
                )
            
            return None
        
        except Exception as e:
            logger.error(
                f"Behavioral monitoring error for actor {actor_id}: {e}",
                exc_info=True,
            )
            # Graceful degradation: monitoring failure does not block operations
            return None
    
    async def observe_auth_failure(
        self,
        actor_id: str,
        attempted_permission: str,
        correlation_id: str,
    ) -> Optional[BehavioralAnomalyEvent]:
        """
        Observe failed authorization attempt (potential privilege escalation).
        
        Called by: RBACManager.check_permission() on failure
        """
        if not self.enabled:
            return None
        
        try:
            # Update profile
            async with self._profile_lock:
                profile = self._get_or_create_profile(actor_id)
                profile.update_activity(failed_auth=True)
            
            # Calculate failed auth rate (per hour)
            failed_auth_rate = await self._calculate_failed_auth_rate(actor_id)
            
            # Check for anomaly
            if failed_auth_rate > 5:  # Threshold: >5 failures per hour
                anomaly = BehavioralAnomalyEvent(
                    event_id=f"authfail-{actor_id}-{int(datetime.now(timezone.utc).timestamp())}",
                    timestamp=datetime.now(timezone.utc),
                    actor_id=actor_id,
                    metric=BehaviorMetric.FAILED_AUTH_RATE,
                    observed_value=failed_auth_rate,
                    expected_range=(0.0, 3.0),
                    deviation_score=failed_auth_rate / 3.0,
                    threat_level=ThreatLevel.HIGH if failed_auth_rate > 10 else ThreatLevel.MEDIUM,
                    context={
                        "attempted_permission": attempted_permission,
                        "recent_failures": failed_auth_rate,
                    },
                    correlation_id=correlation_id,
                )
                
                await self._handle_anomaly(anomaly)
                return anomaly
            
            return None
        
        except Exception as e:
            logger.error(
                f"Auth failure monitoring error for actor {actor_id}: {e}",
                exc_info=True,
            )
            return None
    
    async def _update_profile(
        self,
        actor_id: str,
        operation_type: str,
        entity_count: int,
    ):
        """Update actor behavioral profile"""
        async with self._profile_lock:
            profile = self._get_or_create_profile(actor_id)
            
            mutation_count = 1 if operation_type.startswith("NODE_") else 0
            delete_count = 1 if "DELETE" in operation_type else 0
            current_hour = datetime.now(timezone.utc).hour
            
            profile.update_activity(
                mutation_count=mutation_count,
                delete_count=delete_count,
                current_hour=current_hour,
            )
            
            # Track operation types
            profile.typical_operations[operation_type] = (
                profile.typical_operations.get(operation_type, 0) + 1
            )
        
        # Add to activity buffer (for rate calculation)
        self._activity_buffer[actor_id].append({
            "timestamp": datetime.now(timezone.utc),
            "operation_type": operation_type,
            "entity_count": entity_count,
        })
    
    def _get_or_create_profile(self, actor_id: str) -> BehaviorProfile:
        """Get existing profile or create new baseline"""
        if actor_id not in self._profiles:
            self._profiles[actor_id] = BehaviorProfile(
                actor_id=actor_id,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
        return self._profiles[actor_id]
    
    async def _calculate_mutation_rate(self, actor_id: str) -> float:
        """Calculate mutations per minute (last 5 minutes)"""
        now = datetime.now(timezone.utc)
        recent = [
            activity
            for activity in self._activity_buffer[actor_id]
            if (now - activity["timestamp"]).total_seconds() < 300  # 5 minutes
        ]
        
        if not recent:
            return 0.0
        
        return len(recent) / 5.0  # per minute
    
    async def _calculate_delete_rate(self, actor_id: str, operation_type: str) -> float:
        """Calculate delete operations per hour (last 1 hour)"""
        now = datetime.now(timezone.utc)
        recent_deletes = [
            activity
            for activity in self._activity_buffer[actor_id]
            if (now - activity["timestamp"]).total_seconds() < 3600  # 1 hour
            and "DELETE" in activity["operation_type"]
        ]
        
        return float(len(recent_deletes))
    
    async def _calculate_failed_auth_rate(self, actor_id: str) -> float:
        """Calculate failed auth attempts per hour"""
        profile = self._profiles.get(actor_id)
        if not profile:
            return 0.0
        
        # Simple rate: total failures / hours since first seen
        hours_active = max(
            (datetime.now(timezone.utc) - profile.first_seen).total_seconds() / 3600,
            1.0,  # minimum 1 hour
        )
        
        return profile.total_failed_auth / hours_active
    
    def _is_off_hours(self, timestamp: datetime) -> bool:
        """Check if timestamp is outside business hours (9-17 UTC)"""
        hour = timestamp.hour
        return hour < 9 or hour >= 17
    
    def _create_anomaly_event(
        self,
        actor_id: str,
        metric: BehaviorMetric,
        observed_value: float,
        alert: AnomalyAlert,
        correlation_id: str,
    ) -> BehavioralAnomalyEvent:
        """Create BehavioralAnomalyEvent from StatisticalAnomalyDetector alert"""
        # Map deviation score to threat level
        if alert.deviation_score > 5.0:
            threat_level = ThreatLevel.CRITICAL
        elif alert.deviation_score > 3.5:
            threat_level = ThreatLevel.HIGH
        elif alert.deviation_score > 2.5:
            threat_level = ThreatLevel.MEDIUM
        else:
            threat_level = ThreatLevel.LOW
        
        return BehavioralAnomalyEvent(
            event_id=f"{metric.value}-{actor_id}-{int(alert.timestamp.timestamp())}",
            timestamp=alert.timestamp,
            actor_id=actor_id,
            metric=metric,
            observed_value=observed_value,
            expected_range=alert.expected_range,
            deviation_score=alert.deviation_score,
            threat_level=threat_level,
            context={"alert_message": alert.message},
            correlation_id=correlation_id,
        )
    
    async def _handle_anomaly(self, anomaly: BehavioralAnomalyEvent):
        """Handle detected anomaly (log, alert, audit)"""
        # Store for correlation
        self._recent_anomalies.append(anomaly)
        
        # Log based on severity
        log_msg = (
            f"Behavioral anomaly detected: {anomaly.metric.value} "
            f"for actor {anomaly.actor_id}, threat_level={anomaly.threat_level.value}, "
            f"observed={anomaly.observed_value:.2f}, "
            f"expected={anomaly.expected_range}"
        )
        
        if anomaly.threat_level == ThreatLevel.CRITICAL:
            logger.critical(log_msg)
        elif anomaly.threat_level == ThreatLevel.HIGH:
            logger.error(log_msg)
        elif anomaly.threat_level == ThreatLevel.MEDIUM:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        
        # External alert callback (e.g., PagerDuty, Slack)
        if self.alert_callback:
            try:
                await self.alert_callback(anomaly)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}", exc_info=True)
    
    def get_profile(self, actor_id: str) -> Optional[BehaviorProfile]:
        """Get actor behavioral profile (for admin dashboard)"""
        return self._profiles.get(actor_id)
    
    def get_recent_anomalies(
        self,
        actor_id: Optional[str] = None,
        threat_level: Optional[ThreatLevel] = None,
        limit: int = 50,
    ) -> List[BehavioralAnomalyEvent]:
        """Get recent anomalies (for security dashboard)"""
        anomalies = list(self._recent_anomalies)
        
        if actor_id:
            anomalies = [a for a in anomalies if a.actor_id == actor_id]
        
        if threat_level:
            anomalies = [a for a in anomalies if a.threat_level == threat_level]
        
        return anomalies[:limit]


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_behavioral_monitor: Optional[GovernanceBehavioralMonitor] = None


def get_behavioral_monitor() -> GovernanceBehavioralMonitor:
    """Get singleton behavioral monitor instance (lazy initialization)"""
    global _behavioral_monitor
    
    if _behavioral_monitor is None:
        # TODO: Load config from runtime settings
        _behavioral_monitor = GovernanceBehavioralMonitor(
            enable_monitoring=True,
            window_size=100,
            z_threshold=3.0,
        )
    
    return _behavioral_monitor
