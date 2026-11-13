#!/usr/bin/env python3
"""
Debug script to replicate the loader worker pattern and find the issue
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mahoun.graph.batch import (
    BatchJob,
    JobPriority,
    JobQueue,
    Worker,
    ResourceLimits,
)
from mahoun.graph.neo4j.connection import get_connection

class DebugLoader:
    """Debug version of the loader to trace the issue"""
    
    def __init__(self):
        self.stats = type('obj', (object,), {'statutes_loaded': 0, 'errors': 0})()
        
    async def load_statute_job(self, job: BatchJob) -> dict:
        """Debug version of load statute job with detailed tracing"""
        print(f"[DEBUG] load_statute_job called")
        print(f"[DEBUG] job.job_id: {job.job_id}")
        print(f"[DEBUG] job.task_name: {job.task_name}")
        print(f"[DEBUG] job.data: {job.data}")
        print(f"[DEBUG] job.data type: {type(job.data)}")
        print(f"[DEBUG] job.data repr: {repr(job.data)}")
        
        if job.data is None:
            print("[ERROR] job.data is None!")
            return {"status": "error", "message": "job.data is None"}
            
        if not isinstance(job.data, dict):
            print(f"[ERROR] job.data is not a dict: {type(job.data)}")
            return {"status": "error", "message": f"job.data is not a dict: {type(job.data)}"}
            
        print(f"[DEBUG] job.data keys: {list(job.data.keys())}")
        
        if "statute_id" not in job.data:
            print(f"[ERROR] 'statute_id' not in job.data")
            print(f"[ERROR] Available keys: {list(job.data.keys())}")
            return {"status": "error", "message": "'statute_id' not in job.data"}
            
        statute_id = job.data["statute_id"]
        print(f"[DEBUG] Successfully extracted statute_id: {statute_id}")
        
        # Simulate the dry run behavior
        print(f"[DEBUG] Simulating dry run processing for {statute_id}")
        await asyncio.sleep(0.01)
        self.stats.statutes_loaded += 1
        return {"status": "success", "id": statute_id}

async def test_debug_loader():
    """Test the debug loader with the exact same pattern as the real loader"""
    print("[INFO] Starting debug loader test...")
    
    # Create queue
    queue = JobQueue(max_size=10)
    print(f"[INFO] Created queue with max_size=10")
    
    # Create loader instance
    loader = DebugLoader()
    print(f"[INFO] Created loader instance")
    
    # Create worker (exact pattern from loader)
    limits = ResourceLimits(max_memory_mb=4096)
    worker = Worker(
        worker_id=f"debug_worker_0",
        task_handler=loader.load_statute_job,
        resource_limits=limits,
        heartbeat_interval=30.0,
    )
    print(f"[INFO] Created worker: {worker.worker_id}")
    
    # Start worker
    print(f"[INFO] Starting worker...")
    await worker.start(queue)
    print(f"[INFO] Worker started")
    
    # Submit a few jobs (exact pattern from loader)
    statute_ids = [f"debug_statute_{i}" for i in range(3)]
    print(f"[INFO] Submitting {len(statute_ids)} jobs: {statute_ids}")
    
    for statute_id in statute_ids:
        job = BatchJob(
            task_name="load_statute",
            data={"statute_id": statute_id},
            priority=JobPriority.HIGH,
            timeout=30.0,
            max_retries=2,
        )
        print(f"[DEBUG] Submitting job: job_id={job.job_id}, data={job.data}")
        await queue.enqueue(job)
        print(f"[DEBUG] Job enqueued successfully")
    
    print(f"[INFO] All jobs submitted, waiting for processing...")
    
    # Wait for completion with timeout
    try:
        # Wait a bit for processing to start
        await asyncio.sleep(2)
        
        # Check if queue is empty (simple completion check)
        for i in range(10):  # Wait up to 10 seconds
            queue_size = await queue.size()
            print(f"[DEBUG] Queue size: {queue_size}")
            if queue_size == 0:
                # Check if worker is idle
                if worker.state.value == "idle":
                    print(f"[INFO] Queue empty and worker idle - processing complete")
                    break
            await asyncio.sleep(1)
        else:
            print(f"[WARNING] Timeout waiting for completion")
            
    except Exception as e:
        print(f"[ERROR] Exception during wait: {e}")
        import traceback
        traceback.print_exc()
    
    # Stop worker
    print(f"[INFO] Stopping worker...")
    await worker.stop(graceful=True, timeout=10)
    print(f"[INFO] Worker stopped")
    
    print(f"[INFO] Final stats: {self.stats.statutes_loaded} statutes loaded, {self.stats.errors} errors")
    print(f"[INFO] Test completed successfully")

if __name__ == "__main__":
    asyncio.run(test_debug_loader())
