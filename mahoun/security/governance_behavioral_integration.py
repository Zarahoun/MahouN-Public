"""
Behavioral Monitoring Integration for Governance Layer
=======================================================

Classification: CRITICAL / SECURITY INTEGRATION
Purpose: Non-invasive integration of behavioral monitoring into governance checkpoints

This module provides async hooks that can be called from:
- MutationAuthorizationBoundary.inspect()
- GovernedNeo4jSession.write_*()
- RBACManager.check_permission()

Design:
- Non-blocking: Monitoring failures do not halt operations
- Async: Monitoring happens in background tasks
- Graceful degradation: Disabled if monitoring service unavailable
- Zero performance impact: <1ms overhead per operation

Author: MAHOUN Security Council
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any

from mahoun.security.behavioral_monitor import (
    get_behavioral_monitor,
    BehavioralAnomalyEvent,
    ThreatLevel,
)
from mahoun.core.models.audit_event import AuditEvent, AuditEventType


logger = logging.getLogger(__name__)


# ============================================================================
# INTEGRATION HOOKS
# ============================================================================

async def observe_mutation_async(
    actor_id: str,
    operation_type: str,
    entity_count: int,
    correlation_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[BehavioralAnomalyEvent]:
    """
    Async hook for observing mutations (called from GovernedNeo4jSession).
    
    Returns:
        BehavioralAnomalyEvent if anomaly detected, None otherwise
    """
    try:
        monitor = get_behavioral_monitor()
        return await monitor.observe_mutation(
            actor_id=actor_id,
            operation_type=operation_type,
            entity_count=entity_count,
            correlation_id=correlation_id,
            metadata=metadata,
        )
    except Exception as e:
        logger.error(
            f"Behavioral monitoring failed for mutation observation: {e}",
            exc_info=True,
        )
        return None


def observe_mutation_background(
    actor_id: str,
    operation_type: str,
    entity_count: int,
    correlation_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Non-blocking background task for mutation observation.
    
    This is the preferred integration point — does not block mutation flow.
    
    Usage in GovernedNeo4jSession:
        from mahoun.security.governance_behavioral_integration import observe_mutation_background
        
        def write_node(self, label, node_data, merge=True):
            # ... existing write logic ...
            
            # Non-blocking behavioral monitoring
            observe_mutation_background(
                actor_id=self._actor_id,
                operation_type="NODE_CREATE" if not merge else "NODE_MERGE",
                entity_count=1,
                correlation_id=self._correlation_id,
                metadata={"label": label, "merge": merge},
            )
            
            return receipt
    """
    def _observe_sync():
        """Synchronous observation wrapper for thread execution"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    observe_mutation_async(
                        actor_id=actor_id,
                        operation_type=operation_type,
                        entity_count=entity_count,
                        correlation_id=correlation_id,
                        metadata=metadata,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.debug(f"Background behavioral monitoring failed (non-critical): {e}")
    
    try:
        # Try to use existing event loop if available
        loop = asyncio.get_running_loop()
        loop.create_task(
            observe_mutation_async(
                actor_id=actor_id,
                operation_type=operation_type,
                entity_count=entity_count,
                correlation_id=correlation_id,
                metadata=metadata,
            )
        )
    except RuntimeError:
        # No event loop — run in background thread
        import concurrent.futures
        import threading
        
        thread = threading.Thread(target=_observe_sync, daemon=True)
        thread.start()


async def observe_auth_failure_async(
    actor_id: str,
    attempted_permission: str,
    correlation_id: str,
) -> Optional[BehavioralAnomalyEvent]:
    """
    Async hook for observing authorization failures.
    
    Called from: RBACManager.check_permission() on denial
    """
    try:
        monitor = get_behavioral_monitor()
        return await monitor.observe_auth_failure(
            actor_id=actor_id,
            attempted_permission=attempted_permission,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.error(
            f"Behavioral monitoring failed for auth failure observation: {e}",
            exc_info=True,
        )
        return None


def observe_auth_failure_background(
    actor_id: str,
    attempted_permission: str,
    correlation_id: str,
) -> None:
    """
    Non-blocking background task for auth failure observation.
    
    Usage in RBACManager:
        from mahoun.security.governance_behavioral_integration import observe_auth_failure_background
        
        def check_permission(self, actor_id, permission, correlation_id):
            if not self.has_permission(actor_id, permission):
                # Log failure for behavioral monitoring
                observe_auth_failure_background(
                    actor_id=actor_id,
                    attempted_permission=permission.value,
                    correlation_id=correlation_id,
                )
                raise PermissionDeniedError(...)
    """
    def _observe_sync():
        """Synchronous observation wrapper for thread execution"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    observe_auth_failure_async(
                        actor_id=actor_id,
                        attempted_permission=attempted_permission,
                        correlation_id=correlation_id,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.debug(f"Background behavioral monitoring failed (non-critical): {e}")
    
    try:
        # Try to use existing event loop if available
        loop = asyncio.get_running_loop()
        loop.create_task(
            observe_auth_failure_async(
                actor_id=actor_id,
                attempted_permission=attempted_permission,
                correlation_id=correlation_id,
            )
        )
    except RuntimeError:
        # No event loop — run in background thread
        import threading
        
        thread = threading.Thread(target=_observe_sync, daemon=True)
        thread.start()



# ============================================================================
# ANOMALY RESPONSE ACTIONS
# ============================================================================

def should_block_operation(anomaly: BehavioralAnomalyEvent) -> bool:
    """
    Determine if an anomaly should block the operation.
    
    Default policy: Block only CRITICAL threats
    
    Override this function to implement custom blocking logic.
    """
    return anomaly.threat_level == ThreatLevel.CRITICAL


def create_audit_event_from_anomaly(
    anomaly: BehavioralAnomalyEvent,
) -> AuditEvent:
    """
    Convert behavioral anomaly to audit event for ledger.
    
    This allows anomalies to be persisted in the audit trail.
    """
    return AuditEvent(
        event_type=AuditEventType.SECURITY_ALERT,
        timestamp=anomaly.timestamp,
        actor_id=anomaly.actor_id,
        correlation_id=anomaly.correlation_id or anomaly.event_id,
        metadata={
            "anomaly_type": "behavioral",
            "metric": anomaly.metric.value,
            "observed_value": anomaly.observed_value,
            "expected_range": anomaly.expected_range,
            "deviation_score": anomaly.deviation_score,
            "threat_level": anomaly.threat_level.value,
            "context": anomaly.context,
        },
    )


# ============================================================================
# EXAMPLE INTEGRATION PATTERNS
# ============================================================================

"""
INTEGRATION PATTERN 1: GovernedNeo4jSession.write_node()
========================================================

Add this at the END of write_node() method (after mutation succeeds):

    # Behavioral monitoring (non-blocking)
    from mahoun.security.governance_behavioral_integration import observe_mutation_background
    
    observe_mutation_background(
        actor_id=self._actor_id,
        operation_type="NODE_CREATE" if not merge else "NODE_MERGE",
        entity_count=1,
        correlation_id=self._correlation_id,
        metadata={"label": label, "merge": merge},
    )


INTEGRATION PATTERN 2: RBACManager.check_permission()
======================================================

Add this AFTER permission denial (inside the raise block):

    # Behavioral monitoring for auth failure (non-blocking)
    from mahoun.security.governance_behavioral_integration import observe_auth_failure_background
    
    observe_auth_failure_background(
        actor_id=actor_id,
        attempted_permission=permission.value,
        correlation_id=correlation_id or "no-correlation",
    )


INTEGRATION PATTERN 3: High-Risk Operation Blocking
====================================================

If you want to BLOCK operations on CRITICAL anomalies:

    from mahoun.security.governance_behavioral_integration import (
        observe_mutation_async,
        should_block_operation,
    )
    
    async def write_node_with_blocking(self, label, node_data, merge=True):
        # Pre-mutation anomaly check
        anomaly = await observe_mutation_async(
            actor_id=self._actor_id,
            operation_type="NODE_CREATE" if not merge else "NODE_MERGE",
            entity_count=1,
            correlation_id=self._correlation_id,
            metadata={"label": label},
        )
        
        if anomaly and should_block_operation(anomaly):
            raise SecurityError(
                f"Operation blocked due to behavioral anomaly: {anomaly.metric.value}"
            )
        
        # ... proceed with mutation ...
"""
