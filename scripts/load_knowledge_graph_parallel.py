#!/usr/bin/env python3
"""
Knowledge Graph Loader using Batch Processing System

This script loads legal data (statutes, precedents, entities) into the Neo4j
knowledge graph using the batch processing system with priority queuing.

Performance Target: 4000+ facts in 7-10 minutes (3-4x speedup vs sequential)

Usage:
    # Load sample data (test)
    python scripts/load_knowledge_graph_parallel.py --dry-run

    # Production graph writes are quarantined; use the read-only mode.
    python scripts/load_knowledge_graph_parallel.py --dry-run

    # Load with custom worker config
    python scripts/load_knowledge_graph_parallel.py --statute-workers 6 --precedent-workers 6
"""

import asyncio
import argparse
import logging
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from datetime import datetime

MAX_CPU_SAFE_WORKERS = 2
MAX_CPU_SAFE_BATCH_SIZE = 200

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mahoun.graph.batch import (
    BatchJob,
    BatchConfig,
    JobPriority,
    JobStatus,
    PriorityQueue,
    Worker,
    ResourceLimits,
)
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LoaderConfig:
    """Configuration for Knowledge Graph loader"""
    dry_run: bool = False
    statute_workers: int = 1
    precedent_workers: int = 1
    entity_workers: int = 1
    batch_size: int = 100
    max_queue_size: int = 5000
    worker_timeout: float = 300.0  # 5 minutes per job
    stats_interval: float = 10.0   # Print stats every 10 seconds

    def __post_init__(self) -> None:
        worker_values = {
            "statute_workers": self.statute_workers,
            "precedent_workers": self.precedent_workers,
            "entity_workers": self.entity_workers,
        }
        for name, value in worker_values.items():
            if value < 1 or value > MAX_CPU_SAFE_WORKERS:
                raise ValueError(
                    f"{name} must be between 1 and {MAX_CPU_SAFE_WORKERS}"
                )
        if self.batch_size < 1 or self.batch_size > MAX_CPU_SAFE_BATCH_SIZE:
            raise ValueError(
                f"batch_size must be between 1 and {MAX_CPU_SAFE_BATCH_SIZE}"
            )


@dataclass
class LoaderStats:
    """Statistics tracking"""
    statutes_loaded: int = 0
    precedents_loaded: int = 0
    entities_loaded: int = 0
    errors: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def duration(self) -> float:
        """Total duration in seconds"""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def throughput(self) -> float:
        """Items per second"""
        duration = self.duration()
        if duration == 0:
            return 0.0
        total = self.statutes_loaded + self.precedents_loaded + self.entities_loaded
        return total / duration

    def summary(self) -> str:
        """Return summary statistics"""
        return (
            f"Statutes: {self.statutes_loaded}, "
            f"Precedents: {self.precedents_loaded}, "
            f"Entities: {self.entities_loaded}, "
            f"Errors: {self.errors}, "
            f"Duration: {self.duration():.1f}s, "
            f"Throughput: {self.throughput():.1f} items/s"
        )


class LegalDataSource:
    """Mock data source for legal data"""

    @staticmethod
    def get_statute_ids() -> List[str]:
        """Get statute IDs to load"""
        # Civil Code: 1-800, Commercial: 801-1400, Labor: 1401-1600
        return [f"statute_{i}" for i in range(1, 1601)]

    @staticmethod
    def get_precedent_ids() -> List[str]:
        """Get precedent IDs to load"""
        # Supreme Court: 1-1000, Admin: 1001-1500, Commercial: 1501-2300
        return [f"precedent_{i}" for i in range(1, 2301)]

    @staticmethod
    def get_entity_ids() -> List[str]:
        """Get entity IDs to load"""
        # Various legal entities
        return [f"entity_{i}" for i in range(1, 1001)]

    @staticmethod
    async def load_statute(statute_id: str) -> Dict[str, Any]:
        """Load statute data from source"""
        # Simulate database lookup
        await asyncio.sleep(0.01)  # 10ms lookup
        return {
            "id": statute_id,
            "type": "statute",
            "title": f"Article {statute_id}",
            "text": f"Statute text for {statute_id}",
            "category": "civil" if statute_id < 801 else "commercial" if statute_id < 1401 else "labor",
        }

    @staticmethod
    async def load_precedent(precedent_id: str) -> Dict[str, Any]:
        """Load precedent data from source"""
        await asyncio.sleep(0.01)  # 10ms lookup
        return {
            "id": precedent_id,
            "type": "precedent",
            "precedent_id": f"Case_{precedent_id}",
            "decision": f"Decision text for {precedent_id}",
            "court": "supreme" if precedent_id < 1001 else "admin" if precedent_id < 1501 else "commercial",
        }

    @staticmethod
    async def load_entity(entity_id: str) -> Dict[str, Any]:
        """Load entity data from source"""
        await asyncio.sleep(0.01)  # 10ms lookup
        return {
            "id": entity_id,
            "type": "entity",
            "name": f"Entity {entity_id}",
            "category": "organization",
        }


class KnowledgeGraphLoader:
    """Loads legal data into the batch system in read-only dry-run mode.

    The historical direct Neo4j mutation path is quarantined until this loader
    is integrated with an approved governed ingestion workflow.
    """

    def __init__(self, config: LoaderConfig):
        self.config = config
        self.stats = LoaderStats(start_time=time.time())
        self.queue: Optional[PriorityQueue] = None
        self.workers: Dict[str, List[Worker]] = {
            "statute": [],
            "precedent": [],
            "entity": [],
        }

    def _assert_read_only_mode(self) -> None:
        """Fail closed rather than allowing an ungoverned graph mutation."""
        if not self.config.dry_run:
            raise RuntimeError(
                "Knowledge graph writes are quarantined in this batch loader. "
                "Use --dry-run or the canonical governed ingestion workflow."
            )

    async def load_statute_job(self, job: BatchJob) -> Dict[str, Any]:
        """Load statute into knowledge graph"""
        statute_id = job.data["statute_id"]

        try:
            self._assert_read_only_mode()
            logger.debug(f"[DRY-RUN] Loading statute {statute_id}")
            await asyncio.sleep(0.05)  # Simulate work
            self.stats.statutes_loaded += 1
            return {"status": "success", "id": statute_id}

        except Exception as e:
            logger.error(f"Error loading statute {statute_id}: {e}")
            self.stats.errors += 1
            raise

    async def load_precedent_job(self, job: BatchJob) -> Dict[str, Any]:
        """Load precedent into knowledge graph"""
        precedent_id = job.data["precedent_id"]

        try:
            self._assert_read_only_mode()
            logger.debug(f"[DRY-RUN] Loading precedent {precedent_id}")
            await asyncio.sleep(0.03)
            self.stats.precedents_loaded += 1
            return {"status": "success", "id": precedent_id}

        except Exception as e:
            logger.error(f"Error loading precedent {precedent_id}: {e}")
            self.stats.errors += 1
            raise

    async def load_entity_job(self, job: BatchJob) -> Dict[str, Any]:
        """Load entity into knowledge graph"""
        entity_id = job.data["entity_id"]

        try:
            self._assert_read_only_mode()
            logger.debug(f"[DRY-RUN] Loading entity {entity_id}")
            await asyncio.sleep(0.02)
            self.stats.entities_loaded += 1
            return {"status": "success", "id": entity_id}

        except Exception as e:
            logger.error(f"Error loading entity {entity_id}: {e}")
            self.stats.errors += 1
            raise

    async def create_workers(self):
        """Create worker pools"""
        limits = ResourceLimits(max_memory_mb=4096)

        # Statute workers (HIGH priority)
        for i in range(self.config.statute_workers):
            worker = Worker(
                worker_id=f"statute_{i}",
                task_handler=self.load_statute_job,
                resource_limits=limits,
                heartbeat_interval=30.0,
            )
            self.workers["statute"].append(worker)

        # Precedent workers (NORMAL priority)
        for i in range(self.config.precedent_workers):
            worker = Worker(
                worker_id=f"precedent_{i}",
                task_handler=self.load_precedent_job,
                resource_limits=limits,
                heartbeat_interval=30.0,
            )
            self.workers["precedent"].append(worker)

        # Entity workers (LOW priority)
        for i in range(self.config.entity_workers):
            worker = Worker(
                worker_id=f"entity_{i}",
                task_handler=self.load_entity_job,
                resource_limits=limits,
                heartbeat_interval=30.0,
            )
            self.workers["entity"].append(worker)

        logger.info(
            f"Created {self.config.statute_workers} statute workers, "
            f"{self.config.precedent_workers} precedent workers, "
            f"{self.config.entity_workers} entity workers"
        )

    async def submit_jobs(self):
        """Submit all jobs to queue"""
        logger.info("Submitting jobs to queue...")

        # Submit statutes with HIGH priority
        statute_ids = LegalDataSource.get_statute_ids()
        for statute_id in statute_ids:
            job = BatchJob(
                task_name="load_statute",
                data={"statute_id": statute_id},
                priority=JobPriority.HIGH,  # Highest priority
                timeout=self.config.worker_timeout,
                max_retries=2,
            )
            await self.queue.enqueue(job)

        logger.info(f"Submitted {len(statute_ids)} statute jobs")

        # Submit precedents with NORMAL priority
        precedent_ids = LegalDataSource.get_precedent_ids()
        for precedent_id in precedent_ids:
            job = BatchJob(
                task_name="load_precedent",
                data={"precedent_id": precedent_id},
                priority=JobPriority.NORMAL,
                timeout=self.config.worker_timeout,
                max_retries=2,
            )
            await self.queue.enqueue(job)

        logger.info(f"Submitted {len(precedent_ids)} precedent jobs")

        # Submit entities with LOW priority
        entity_ids = LegalDataSource.get_entity_ids()
        for entity_id in entity_ids:
            job = BatchJob(
                task_name="load_entity",
                data={"entity_id": entity_id},
                priority=JobPriority.LOW,  # Lowest priority
                timeout=self.config.worker_timeout,
                max_retries=2,
            )
            await self.queue.enqueue(job)

        logger.info(f"Submitted {len(entity_ids)} entity jobs")

        total = len(statute_ids) + len(precedent_ids) + len(entity_ids)
        logger.info(f"Total jobs submitted: {total}")

    async def monitor_progress(self):
        """Monitor and report progress"""
        logger.info("Starting progress monitoring...")

        # Give workers time to start dequeuing
        await asyncio.sleep(2)

        while True:
            # Check if queue is empty
            queue_size = await self.queue.size()
            if queue_size == 0:
                # Check if all workers are idle
                all_idle = True
                for worker_list in self.workers.values():
                    for worker in worker_list:
                        if not worker.state.value == "idle":
                            all_idle = False
                            break

                if all_idle:
                    logger.info("All jobs completed!")
                    break

            # Report progress
            metrics = self.queue.get_metrics()
            total_jobs = metrics["total_enqueued"]
            processed = metrics["total_dequeued"]
            remaining = total_jobs - processed
            
            logger.info(
                f"Progress: {self.stats.summary()} | "
                f"Remaining: {remaining}/{total_jobs}"
            )

            await asyncio.sleep(self.config.stats_interval)

    async def start_workers(self):
        """Start all workers"""
        logger.info("Starting workers...")

        tasks = []
        for worker_type, worker_list in self.workers.items():
            for worker in worker_list:
                tasks.append(worker.start(self.queue))
                logger.debug(f"Started {worker_type} worker")

        await asyncio.gather(*tasks)

    async def stop_workers(self):
        """Stop all workers gracefully"""
        logger.info("Stopping workers...")

        tasks = []
        for worker_type, worker_list in self.workers.items():
            for worker in worker_list:
                tasks.append(worker.stop(graceful=True, timeout=30))

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All workers stopped")

    async def load(self):
        """Execute knowledge graph loading"""
        try:
            self._assert_read_only_mode()
            # Create queue
            self.queue = PriorityQueue(max_size=self.config.max_queue_size)
            logger.info(f"Created priority queue (max size: {self.config.max_queue_size})")

            # Create workers
            await self.create_workers()

            # Start workers task
            worker_task = asyncio.create_task(self.start_workers())

            # Submit jobs task
            submit_task = asyncio.create_task(self.submit_jobs())

            # Wait for both to complete
            await asyncio.gather(worker_task, submit_task)

            # Monitor progress
            await self.monitor_progress()

            # Final stats
            self.stats.end_time = time.time()
            logger.info(f"Load complete! {self.stats.summary()}")

        except Exception as e:
            logger.error(f"Loading failed: {e}", exc_info=True)
            raise
        finally:
            await self.stop_workers()


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Load Knowledge Graph data using batch processing"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the supported read-only simulation mode",
    )
    parser.add_argument(
        "--statute-workers",
        type=int,
        default=1,
        help="Number of statute loader workers (default: 1; max: 2)",
    )
    parser.add_argument(
        "--precedent-workers",
        type=int,
        default=1,
        help="Number of precedent loader workers (default: 1; max: 2)",
    )
    parser.add_argument(
        "--entity-workers",
        type=int,
        default=1,
        help="Number of entity loader workers (default: 1; max: 2)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create config
    config = LoaderConfig(
        dry_run=args.dry_run,
        statute_workers=args.statute_workers,
        precedent_workers=args.precedent_workers,
        entity_workers=args.entity_workers,
    )

    logger.info(f"Knowledge Graph Loader starting...")
    logger.info(f"Config: {config}")

    # Create and run loader
    loader = KnowledgeGraphLoader(config)
    await loader.load()


if __name__ == "__main__":
    asyncio.run(main())
