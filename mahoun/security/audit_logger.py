"""
Security Audit Logger
=====================

Comprehensive security event logging for compliance and forensics.

Features:
- Structured audit logs with JSON format
- Event categorization (auth, access, data, system)
- Severity levels (info, warning, critical)
- Automatic enrichment (timestamp, user, IP, session)
- Log rotation and retention
- Query and analysis support
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
from collections import deque

logger = logging.getLogger(__name__)


class EventCategory(str, Enum):
    """Security event categories."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    SYSTEM_CHANGE = "system_change"
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT = "rate_limit"
    API_KEY = "api_key"


class EventSeverity(str, Enum):
    """Event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Security audit event."""
    event_id: str
    timestamp: datetime
    category: EventCategory
    severity: EventSeverity
    action: str
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    resource: Optional[str] = None
    result: str = "success"  # success, failure, denied
    details: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['category'] = self.category.value
        data['severity'] = self.severity.value
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class SecurityAuditLogger:
    """
    Comprehensive security audit logger.
    
    Logs all security-relevant events with structured data for compliance.
    """
    
    def __init__(
        self,
        log_dir: Path = Path("security_logs"),
        max_memory_events: int = 10000,
        enable_file_logging: bool = True
    ):
        """
        Initialize security audit logger.
        
        Args:
            log_dir: Directory to store audit log files
            max_memory_events: Maximum events to keep in memory
            enable_file_logging: Whether to write logs to files
        """
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging
        
        if self.enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory event buffer for fast queries
        self.events: deque = deque(maxlen=max_memory_events)
        self.events_lock = threading.Lock()
        
        # Event counters by category
        self.counters: Dict[str, int] = {}
        self.counters_lock = threading.Lock()
    
    def log_event(
        self,
        category: EventCategory,
        action: str,
        severity: EventSeverity = EventSeverity.INFO,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        resource: Optional[str] = None,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """
        Log a security audit event.
        
        Args:
            category: Event category
            action: Action performed
            severity: Event severity
            user_id: User identifier
            ip_address: Client IP address
            session_id: Session identifier
            resource: Resource accessed/modified
            result: Operation result (success, failure, denied)
            details: Additional event details
            metadata: Additional metadata
            
        Returns:
            Created AuditEvent
        """
        import uuid
        
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            category=category,
            severity=severity,
            action=action,
            user_id=user_id,
            ip_address=ip_address,
            session_id=session_id,
            resource=resource,
            result=result,
            details=details or {},
            metadata=metadata or {}
        )
        
        # Add to memory buffer
        with self.events_lock:
            self.events.append(event)
        
        # Update counters
        with self.counters_lock:
            key = f"{category.value}_{result}"
            self.counters[key] = self.counters.get(key, 0) + 1
        
        # Write to file
        if self.enable_file_logging:
            self._write_to_file(event)
        
        # Log to standard logger based on severity
        log_msg = f"[{category.value}] {action} - {result}"
        if severity == EventSeverity.CRITICAL:
            logger.critical(log_msg, extra=event.to_dict())
        elif severity == EventSeverity.ERROR:
            logger.error(log_msg, extra=event.to_dict())
        elif severity == EventSeverity.WARNING:
            logger.warning(log_msg, extra=event.to_dict())
        else:
            logger.info(log_msg, extra=event.to_dict())
        
        return event
    
    def _write_to_file(self, event: AuditEvent) -> None:
        """Write event to daily log file."""
        date_str = event.timestamp.strftime("%Y%m%d")
        log_file = self.log_dir / f"security_audit_{date_str}.jsonl"
        
        try:
            with open(log_file, 'a') as f:
                f.write(event.to_json() + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    # Convenience methods for common events
    
    def log_authentication(
        self,
        action: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log authentication event."""
        severity = EventSeverity.WARNING if result == "failure" else EventSeverity.INFO
        return self.log_event(
            category=EventCategory.AUTHENTICATION,
            action=action,
            severity=severity,
            user_id=user_id,
            ip_address=ip_address,
            result=result,
            details=details
        )
    
    def log_authorization(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log authorization event."""
        severity = EventSeverity.WARNING if result == "denied" else EventSeverity.INFO
        return self.log_event(
            category=EventCategory.AUTHORIZATION,
            action=action,
            severity=severity,
            user_id=user_id,
            resource=resource,
            result=result,
            details=details
        )
    
    def log_data_access(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log data access event."""
        return self.log_event(
            category=EventCategory.DATA_ACCESS,
            action=action,
            severity=EventSeverity.INFO,
            user_id=user_id,
            resource=resource,
            details=details
        )
    
    def log_data_modification(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log data modification event."""
        return self.log_event(
            category=EventCategory.DATA_MODIFICATION,
            action=action,
            severity=EventSeverity.INFO,
            user_id=user_id,
            resource=resource,
            details=details
        )
    
    def log_security_violation(
        self,
        action: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log security violation."""
        return self.log_event(
            category=EventCategory.SECURITY_VIOLATION,
            action=action,
            severity=EventSeverity.CRITICAL,
            user_id=user_id,
            ip_address=ip_address,
            result="violation",
            details=details
        )
    
    def log_rate_limit(
        self,
        action: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log rate limit event."""
        return self.log_event(
            category=EventCategory.RATE_LIMIT,
            action=action,
            severity=EventSeverity.WARNING,
            user_id=user_id,
            ip_address=ip_address,
            result="blocked",
            details=details
        )
    
    # Query methods
    
    def query_events(
        self,
        category: Optional[EventCategory] = None,
        severity: Optional[EventSeverity] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Query audit events from memory buffer.
        
        Args:
            category: Filter by category
            severity: Filter by severity
            user_id: Filter by user
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of events to return
            
        Returns:
            List of matching AuditEvent objects
        """
        with self.events_lock:
            events = list(self.events)
        
        # Apply filters
        if category:
            events = [e for e in events if e.category == category]
        
        if severity:
            events = [e for e in events if e.severity == severity]
        
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        
        # Sort by timestamp (newest first) and limit
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]
    
    def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get audit log statistics.
        
        Args:
            start_time: Start time for statistics
            end_time: End time for statistics
            
        Returns:
            Statistics dictionary
        """
        with self.events_lock:
            events = list(self.events)
        
        # Filter by time
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        
        # Calculate statistics
        total_events = len(events)
        
        by_category = {}
        by_severity = {}
        by_result = {}
        
        for event in events:
            # By category
            cat = event.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
            
            # By severity
            sev = event.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            
            # By result
            res = event.result
            by_result[res] = by_result.get(res, 0) + 1
        
        return {
            "total_events": total_events,
            "by_category": by_category,
            "by_severity": by_severity,
            "by_result": by_result,
            "time_range": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None
            }
        }
    
    def get_recent_violations(self, limit: int = 10) -> List[AuditEvent]:
        """Get recent security violations."""
        return self.query_events(
            category=EventCategory.SECURITY_VIOLATION,
            limit=limit
        )
    
    def get_failed_authentications(
        self,
        since: Optional[datetime] = None,
        limit: int = 50
    ) -> List[AuditEvent]:
        """Get recent failed authentication attempts."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        with self.events_lock:
            events = [
                e for e in self.events
                if e.category == EventCategory.AUTHENTICATION
                and e.result == "failure"
                and e.timestamp >= since
            ]
        
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]
    
    def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Delete log files older than specified days.
        
        Args:
            days_to_keep: Number of days to retain logs
            
        Returns:
            Number of files deleted
        """
        if not self.enable_file_logging:
            return 0
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        deleted = 0
        
        for log_file in self.log_dir.glob("security_audit_*.jsonl"):
            try:
                # Extract date from filename
                date_str = log_file.stem.split('_')[-1]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    deleted += 1
                    logger.info(f"Deleted old audit log: {log_file}")
            except Exception as e:
                logger.error(f"Failed to process {log_file}: {e}")
        
        return deleted


# Global audit logger instance
_audit_logger: Optional[SecurityAuditLogger] = None


def get_audit_logger() -> SecurityAuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = SecurityAuditLogger()
    return _audit_logger


def log_security_event(
    category: EventCategory,
    action: str,
    **kwargs
) -> AuditEvent:
    """Convenience function to log security event."""
    return get_audit_logger().log_event(category, action, **kwargs)
