"""
Health check data models.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class HealthStatus(str, Enum):
    """Health status enumeration."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheckResult(BaseModel):
    """Result of a single health check."""
    
    name: str = Field(..., description="Name of the health check")
    status: HealthStatus = Field(..., description="Health status")
    message: Optional[str] = Field(None, description="Status message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    duration_ms: Optional[float] = Field(None, description="Check duration in milliseconds")


class SystemHealthReport(BaseModel):
    """Complete system health report."""
    
    status: HealthStatus = Field(..., description="Overall system status")
    checks: Dict[str, HealthCheckResult] = Field(..., description="Individual check results")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Report timestamp")
    version: str = Field("0.1.0", description="Application version")
    uptime_seconds: Optional[float] = Field(None, description="System uptime in seconds")
    
    @property
    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        return self.status == HealthStatus.HEALTHY
    
    @property
    def failed_checks(self) -> list[str]:
        """Get list of failed check names."""
        return [
            name for name, result in self.checks.items()
            if result.status == HealthStatus.UNHEALTHY
        ]
