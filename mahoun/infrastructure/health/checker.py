"""
Enhanced health checker with comprehensive system checks.
"""

import asyncio
import psutil
import time
from typing import Optional
from datetime import datetime

from mahoun.infrastructure.health.models import (
    HealthStatus,
    HealthCheckResult,
    SystemHealthReport,
)


class EnhancedHealthChecker:
    """
    Production-grade health checker.
    
    Checks:
    - API responsiveness
    - Database connectivity (Neo4j, PostgreSQL, Redis)
    - Disk space
    - Memory usage
    - CPU usage
    - Service dependencies
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.min_disk_space_gb = 5.0
        self.max_memory_percent = 90.0
        self.max_cpu_percent = 95.0
    
    async def check_all(self) -> SystemHealthReport:
        """Run all health checks and return comprehensive report."""
        checks = {}
        
        # Run all checks concurrently
        check_tasks = {
            "api": self._check_api(),
            "database_postgres": self._check_postgres(),
            "database_neo4j": self._check_neo4j(),
            "database_redis": self._check_redis(),
            "disk_space": self._check_disk_space(),
            "memory": self._check_memory(),
            "cpu": self._check_cpu(),
        }
        
        results = await asyncio.gather(*check_tasks.values(), return_exceptions=True)
        
        for name, result in zip(check_tasks.keys(), results):
            if isinstance(result, Exception):
                checks[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}",
                )
            else:
                checks[name] = result
        
        # Determine overall status
        overall_status = self._determine_overall_status(checks)
        
        return SystemHealthReport(
            status=overall_status,
            checks=checks,
            uptime_seconds=time.time() - self.start_time,
        )
    
    async def _check_api(self) -> HealthCheckResult:
        """Check API responsiveness."""
        start = time.time()
        
        try:
            # Simple check - if we're here, API is responding
            duration_ms = (time.time() - start) * 1000
            
            return HealthCheckResult(
                name="api",
                status=HealthStatus.HEALTHY,
                message="API is responsive",
                duration_ms=duration_ms,
            )
        except Exception as e:
            return HealthCheckResult(
                name="api",
                status=HealthStatus.UNHEALTHY,
                message=f"API check failed: {str(e)}",
            )
    
    async def _check_postgres(self) -> HealthCheckResult:
        """Check PostgreSQL connectivity."""
        start = time.time()
        
        try:
            # Try to import and connect
            import asyncpg
            from mahoun.core.settings import get_settings
            
            settings = get_settings()
            
            if not settings.ENABLE_POSTGRES:
                return HealthCheckResult(
                    name="database_postgres",
                    status=HealthStatus.HEALTHY,
                    message="PostgreSQL disabled (not required)",
                )
            
            conn = await asyncpg.connect(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.DB_POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                timeout=5.0,
            )
            
            # Test query
            await conn.fetchval("SELECT 1")
            await conn.close()
            
            duration_ms = (time.time() - start) * 1000
            
            return HealthCheckResult(
                name="database_postgres",
                status=HealthStatus.HEALTHY,
                message="PostgreSQL connection successful",
                duration_ms=duration_ms,
            )
        except Exception as e:
            return HealthCheckResult(
                name="database_postgres",
                status=HealthStatus.UNHEALTHY,
                message=f"PostgreSQL connection failed: {str(e)}",
            )
    
    async def _check_neo4j(self) -> HealthCheckResult:
        """Check Neo4j connectivity."""
        start = time.time()
        
        try:
            from mahoun.core.runtime_config import get_runtime_settings
            
            settings = get_runtime_settings()
            
            if not settings.graph_enabled:
                return HealthCheckResult(
                    name="database_neo4j",
                    status=HealthStatus.HEALTHY,
                    message="Neo4j disabled (not required)",
                )
            
            from mahoun.graph.neo4j.connection import get_connection
            import asyncio
            
            conn = get_connection()
            # ping() is synchronous; run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            is_alive = await loop.run_in_executor(None, conn.ping)
            
            duration_ms = (time.time() - start) * 1000
            
            if is_alive:
                return HealthCheckResult(
                    name="database_neo4j",
                    status=HealthStatus.HEALTHY,
                    message="Neo4j connection successful",
                    duration_ms=duration_ms,
                )
            else:
                return HealthCheckResult(
                    name="database_neo4j",
                    status=HealthStatus.UNHEALTHY,
                    message="Neo4j ping returned False",
                )
        except Exception as e:
            return HealthCheckResult(
                name="database_neo4j",
                status=HealthStatus.UNHEALTHY,
                message=f"Neo4j connection failed: {str(e)}",
            )
    
    async def _check_redis(self) -> HealthCheckResult:
        """Check Redis connectivity."""
        start = time.time()
        
        try:
            import redis.asyncio as redis
            from mahoun.core.settings import get_settings
            
            settings = get_settings()
            
            if not settings.ENABLE_REDIS:
                return HealthCheckResult(
                    name="database_redis",
                    status=HealthStatus.HEALTHY,
                    message="Redis disabled (not required)",
                )
            
            client = redis.from_url(
                settings.REDIS_URL,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                socket_connect_timeout=5.0,
            )
            
            await client.ping()
            await client.close()
            
            duration_ms = (time.time() - start) * 1000
            
            return HealthCheckResult(
                name="database_redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                duration_ms=duration_ms,
            )
        except Exception as e:
            return HealthCheckResult(
                name="database_redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
            )
    
    async def _check_disk_space(self) -> HealthCheckResult:
        """Check available disk space."""
        try:
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024 ** 3)
            used_percent = disk.percent
            
            if free_gb < self.min_disk_space_gb:
                status = HealthStatus.UNHEALTHY
                message = f"Low disk space: {free_gb:.2f}GB free"
            elif used_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {used_percent}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space OK: {free_gb:.2f}GB free"
            
            return HealthCheckResult(
                name="disk_space",
                status=status,
                message=message,
                details={
                    "free_gb": round(free_gb, 2),
                    "used_percent": used_percent,
                    "total_gb": round(disk.total / (1024 ** 3), 2),
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="disk_space",
                status=HealthStatus.UNKNOWN,
                message=f"Disk check failed: {str(e)}",
            )
    
    async def _check_memory(self) -> HealthCheckResult:
        """Check memory usage."""
        try:
            memory = psutil.virtual_memory()
            used_percent = memory.percent
            available_gb = memory.available / (1024 ** 3)
            
            if used_percent > self.max_memory_percent:
                status = HealthStatus.UNHEALTHY
                message = f"High memory usage: {used_percent}%"
            elif used_percent > 80:
                status = HealthStatus.DEGRADED
                message = f"Memory usage elevated: {used_percent}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory OK: {used_percent}% used"
            
            return HealthCheckResult(
                name="memory",
                status=status,
                message=message,
                details={
                    "used_percent": used_percent,
                    "available_gb": round(available_gb, 2),
                    "total_gb": round(memory.total / (1024 ** 3), 2),
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.UNKNOWN,
                message=f"Memory check failed: {str(e)}",
            )
    
    async def _check_cpu(self) -> HealthCheckResult:
        """Check CPU usage."""
        try:
            # Get CPU usage over 1 second interval
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            if cpu_percent > self.max_cpu_percent:
                status = HealthStatus.UNHEALTHY
                message = f"High CPU usage: {cpu_percent}%"
            elif cpu_percent > 80:
                status = HealthStatus.DEGRADED
                message = f"CPU usage elevated: {cpu_percent}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"CPU OK: {cpu_percent}% used"
            
            return HealthCheckResult(
                name="cpu",
                status=status,
                message=message,
                details={
                    "usage_percent": cpu_percent,
                    "cpu_count": cpu_count,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                name="cpu",
                status=HealthStatus.UNKNOWN,
                message=f"CPU check failed: {str(e)}",
            )
    
    def _determine_overall_status(
        self, checks: dict[str, HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall system status from individual checks."""
        statuses = [check.status for check in checks.values()]
        
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
