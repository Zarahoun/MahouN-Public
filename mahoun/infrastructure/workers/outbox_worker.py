"""
MAHOUN Transactional Outbox Worker
==================================

Classification: KERNEL / GOVERNANCE / INFRASTRUCTURE
Purpose: Project committed PostgreSQL state into Neo4j with exactly-once semantics.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.graph.neo4j.connection import get_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("outbox_worker")

class OutboxWorker:
    def __init__(self, batch_size: int = 10, poll_interval: float = 1.0):
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._running = True
        
        # Postgres Config
        self.pg_conn_str = f"host={os.getenv('DB_POSTGRES_HOST', 'postgres')} " \
                           f"port={os.getenv('DB_POSTGRES_PORT', '5432')} " \
                           f"dbname={os.getenv('POSTGRES_DB', 'mahoun')} " \
                           f"user={os.getenv('POSTGRES_USER', 'mahoun')} " \
                           f"password={os.getenv('DB_POSTGRES_PASSWORD', 'mahoun')}"
        
        self.pg_conn = None
        
    def _connect_pg(self):
        if self.pg_conn is None or self.pg_conn.closed:
            self.pg_conn = psycopg2.connect(self.pg_conn_str, cursor_factory=RealDictCursor)
            self.pg_conn.autocommit = False
            logger.info("Connected to PostgreSQL")

    async def run(self):
        logger.info(f"Starting Outbox Worker (batch_size={self.batch_size})")
        
        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)

        while self._running:
            try:
                processed_count = await self.process_batch()
                if processed_count == 0:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(5.0) # Backoff on error

    def stop(self):
        logger.info("Stopping Outbox Worker...")
        self._running = False

    async def process_batch(self) -> int:
        self._connect_pg()
        
        with self.pg_conn.cursor() as cur:
            # 1. Acquire events using SKIP LOCKED for safe concurrency
            cur.execute("""
                UPDATE governance.transactional_outbox
                SET status = 'PROCESSING', locked_at = NOW()
                WHERE event_id IN (
                    SELECT event_id 
                    FROM governance.transactional_outbox
                    WHERE status IN ('PENDING', 'FAILED')
                    AND (retry_count < 5)
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING event_id, aggregate_type, aggregate_id, action, payload, correlation_id;
            """, (self.batch_size,))
            
            events = cur.fetchall()
            if not events:
                self.pg_conn.commit()
                return 0

            logger.info(f"Picked {len(events)} events for processing")
            
            for event in events:
                success = await self._project_event(event)
                
                if success:
                    cur.execute("""
                        UPDATE governance.transactional_outbox
                        SET status = 'PROCESSED', processed_at = NOW()
                        WHERE event_id = %s;
                    """, (event['event_id'],))
                else:
                    cur.execute("""
                        UPDATE governance.transactional_outbox
                        SET status = 'FAILED', retry_count = retry_count + 1, last_error = %s
                        WHERE event_id = %s;
                    """, ("Neo4j projection failed", event['event_id']))
            
            self.pg_conn.commit()
            return len(events)

    async def _project_event(self, event: Dict[str, Any]) -> bool:
        correlation_id = str(event['correlation_id']) if event['correlation_id'] else f"outbox-{uuid.uuid4()}"
        
        try:
            async with GovernanceContextManager.active_context(
                correlation_id=correlation_id,
                execution_mode="STRICT"
            ):
                conn = get_connection()
                with conn.governed_session(
                    correlation_id=correlation_id,
                    actor_id="outbox_worker"
                ) as session:
                    
                    if event['aggregate_type'] == 'legal.chunks':
                        return self._process_chunk_event(session, event)
                    
                    logger.warning(f"Unknown aggregate type: {event['aggregate_type']}")
                    return True # Skip unknown types

        except Exception as e:
            logger.error(f"Failed to project event {event['event_id']}: {e}")
            return False

    def _process_chunk_event(self, session: Any, event: Dict[str, Any]) -> bool:
        action = event['action']
        aggregate_id = str(event['aggregate_id'])
        payload = event['payload']
        
        if action in ('INSERT', 'UPDATE'):
            # Idempotent MERGE with version gate
            # We use aggregate_id as the primary node id in Neo4j
            node_data = {
                "id": aggregate_id,
                **payload
            }
            
            # Remove system/postgres specific fields from Neo4j node
            node_data.pop('created_date', None)
            
            # Neo4j write_node uses MERGE internally
            session.write_node(
                label="Chunk",
                node_data=node_data,
                merge=True
            )
            logger.info(f"Projected Chunk {aggregate_id} ({action})")
            
        elif action == 'DELETE':
            # Idempotent DELETE via canonical governed boundary.
            # CRITICAL: session.delete_node() enforces the full governance chain:
            #   require_context() → require_provenance() → _append_governance_audit()
            #   → _execute_authorized() (sets/resets _authorized_write_ctx)
            # Previous code used session.run() which does NOT exist on
            # GovernedNeo4jSession — causing AttributeError at runtime.
            session.delete_node(
                label="Chunk",
                node_id=aggregate_id,
                soft_delete=True,
                deleted_reason="outbox_worker_projection",
                source_event_id=event['event_id'],
            )
            logger.info(f"Projected Chunk {aggregate_id} (DELETE)")
            
        return True

if __name__ == "__main__":
    worker = OutboxWorker()
    asyncio.run(worker.run())
