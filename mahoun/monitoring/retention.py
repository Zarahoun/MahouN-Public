"""
Data Retention Policy
=====================
Automated data cleanup based on retention policies
"""

import asyncio
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)


class RetentionPolicy:
    """Data retention policy manager"""
    
    # Retention periods (days)
    POLICIES = {
        "audit_logs": 90,        # 3 months
        "sessions": 30,          # 1 month
        "cache": 7,              # 1 week
        "temp_files": 1,         # 1 day
        "feedback": 365,         # 1 year
        "system_metrics": 30     # 1 month
    }
    
    @staticmethod
    async def cleanup_audit_logs(db, days: int = 90):
        """Delete audit logs older than specified days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            "DELETE FROM audit_logs WHERE created_at < $1",
            cutoff_date
        )
        
        deleted = result.split()[-1] if result else "0"
        log.info(f"Deleted {deleted} audit logs older than {days} days")
        return int(deleted)
    
    @staticmethod
    async def cleanup_sessions(db, days: int = 30):
        """Delete expired sessions"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            "DELETE FROM sessions WHERE expires_at < $1 OR created_at < $2",
            datetime.utcnow(),
            cutoff_date
        )
        
        deleted = result.split()[-1] if result else "0"
        log.info(f"Deleted {deleted} expired sessions")
        return int(deleted)
    
    @staticmethod
    async def cleanup_cache(redis, days: int = 7):
        """Cleanup old cache entries"""
        # Redis TTL handles this automatically
        # This is just for manual cleanup if needed
        log.info("Cache cleanup handled by Redis TTL")
        return 0
    
    @staticmethod
    async def cleanup_metrics(db, days: int = 30):
        """Delete old system metrics"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            "DELETE FROM system_metrics WHERE timestamp < $1",
            cutoff_date
        )
        
        deleted = result.split()[-1] if result else "0"
        log.info(f"Deleted {deleted} old metrics")
        return int(deleted)
    
    @staticmethod
    async def run_cleanup(db, redis):
        """Run all cleanup tasks"""
        log.info("🧹 Starting retention policy cleanup...")
        
        total_deleted = 0
        
        # Cleanup audit logs
        total_deleted += await RetentionPolicy.cleanup_audit_logs(
            db, RetentionPolicy.POLICIES["audit_logs"]
        )
        
        # Cleanup sessions
        total_deleted += await RetentionPolicy.cleanup_sessions(
            db, RetentionPolicy.POLICIES["sessions"]
        )
        
        # Cleanup metrics
        total_deleted += await RetentionPolicy.cleanup_metrics(
            db, RetentionPolicy.POLICIES["system_metrics"]
        )
        
        log.info(f"✅ Cleanup complete! Total deleted: {total_deleted} records")
        return total_deleted


async def schedule_cleanup(db, redis, interval_hours: int = 24):
    """Schedule periodic cleanup"""
    while True:
        try:
            await RetentionPolicy.run_cleanup(db, redis)
        except Exception as e:
            log.error(f"Cleanup failed: {e}")
        
        # Wait for next run
        await asyncio.sleep(interval_hours * 3600)
