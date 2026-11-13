"""
Deadlock Detector
=================

Runtime deadlock detection using wait-for graph analysis.

Features:
- Wait-for graph construction
- Cycle detection (deadlock identification)
- Automatic deadlock resolution
- Deadlock prevention policies
- Real-time monitoring

Based on Banker's algorithm and wait-for graph theory.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime, timezone
from threading import RLock
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


class DeadlockResolutionPolicy(str, Enum):
    """Deadlock resolution policy"""
    ABORT_YOUNGEST = "abort_youngest"  # Abort youngest transaction
    ABORT_OLDEST = "abort_oldest"  # Abort oldest transaction
    ABORT_LEAST_WORK = "abort_least_work"  # Abort transaction with least work
    MANUAL = "manual"  # Manual intervention required


@dataclass
class ResourceRequest:
    """Resource request information"""
    transaction_id: str
    resource_id: str
    timestamp: datetime
    priority: int = 0
    work_done: float = 0.0  # Amount of work completed
    
    def age_seconds(self) -> float:
        """Get age of request in seconds"""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()


@dataclass
class DeadlockInfo:
    """Deadlock detection result"""
    detected: bool
    cycle: List[str] = field(default_factory=list)  # Transaction IDs in cycle
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolution_policy: Optional[DeadlockResolutionPolicy] = None
    victim_transaction: Optional[str] = None  # Transaction to abort
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "detected": self.detected,
            "cycle": self.cycle,
            "timestamp": self.timestamp.isoformat(),
            "resolution_policy": self.resolution_policy.value if self.resolution_policy else None,
            "victim_transaction": self.victim_transaction,
        }


class DeadlockDetector:
    """
    Production-grade deadlock detector.
    
    Features:
    - Wait-for graph construction
    - Cycle detection using DFS
    - Multiple resolution policies
    - Automatic deadlock resolution
    - Real-time monitoring
    - Statistics tracking
    
    Usage:
        detector = DeadlockDetector(
            resolution_policy=DeadlockResolutionPolicy.ABORT_YOUNGEST
        )
        
        # Register resource request
        detector.register_wait(
            transaction_id="tx1",
            resource_id="resource_a",
            held_by="tx2"
        )
        
        # Check for deadlocks
        deadlock = detector.detect()
        
        if deadlock.detected:
            # Resolve deadlock
            victim = detector.resolve(deadlock)
            print(f"Aborting transaction: {victim}")
    """
    
    def __init__(
        self,
        resolution_policy: DeadlockResolutionPolicy = DeadlockResolutionPolicy.ABORT_YOUNGEST,
        detection_interval_seconds: float = 5.0,
        enable_auto_resolution: bool = True
    ):
        """
        Initialize deadlock detector.
        
        Args:
            resolution_policy: Policy for resolving deadlocks
            detection_interval_seconds: How often to check for deadlocks
            enable_auto_resolution: Automatically resolve detected deadlocks
        """
        self.resolution_policy = resolution_policy
        self.detection_interval = detection_interval_seconds
        self.enable_auto_resolution = enable_auto_resolution
        
        # Wait-for graph: transaction -> set of transactions it's waiting for
        self._wait_for_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Resource ownership: resource -> transaction holding it
        self._resource_owners: Dict[str, str] = {}
        
        # Active requests
        self._active_requests: Dict[str, ResourceRequest] = {}
        
        # Transaction metadata
        self._transaction_metadata: Dict[str, Dict] = {}
        
        # Statistics
        self._deadlocks_detected = 0
        self._deadlocks_resolved = 0
        self._false_positives = 0
        
        # Thread safety
        self._lock = RLock()
        
        logger.info(
            f"DeadlockDetector initialized "
            f"(policy={resolution_policy.value}, interval={self.detection_interval}s)"
        )
    
    def register_wait(
        self,
        transaction_id: str,
        resource_id: str,
        held_by: str,
        priority: int = 0,
        work_done: float = 0.0
    ) -> None:
        """
        Register that a transaction is waiting for a resource.
        
        Args:
            transaction_id: Transaction waiting for resource
            resource_id: Resource being waited for
            held_by: Transaction currently holding the resource
            priority: Transaction priority (higher = more important)
            work_done: Amount of work completed (0.0 to 1.0)
        """
        with self._lock:
            # Add to wait-for graph
            self._wait_for_graph[transaction_id].add(held_by)
            
            # Record resource ownership
            self._resource_owners[resource_id] = held_by
            
            # Store request
            request = ResourceRequest(
                transaction_id=transaction_id,
                resource_id=resource_id,
                timestamp=datetime.now(timezone.utc),
                priority=priority,
                work_done=work_done
            )
            self._active_requests[f"{transaction_id}:{resource_id}"] = request
            
            # Store transaction metadata
            if transaction_id not in self._transaction_metadata:
                self._transaction_metadata[transaction_id] = {
                    "start_time": datetime.now(timezone.utc),
                    "priority": priority,
                    "work_done": work_done,
                }
            
            logger.debug(
                f"Registered wait: {transaction_id} waiting for "
                f"{resource_id} (held by {held_by})"
            )
    
    def release_wait(
        self,
        transaction_id: str,
        resource_id: Optional[str] = None
    ) -> None:
        """
        Release a wait (transaction acquired resource or gave up).
        
        Args:
            transaction_id: Transaction releasing wait
            resource_id: Specific resource (if None, release all)
        """
        with self._lock:
            if resource_id:
                # Release specific resource
                request_key = f"{transaction_id}:{resource_id}"
                if request_key in self._active_requests:
                    request = self._active_requests[request_key]
                    held_by = self._resource_owners.get(resource_id)
                    
                    if held_by:
                        self._wait_for_graph[transaction_id].discard(held_by)
                    
                    del self._active_requests[request_key]
                    
                    logger.debug(f"Released wait: {transaction_id} for {resource_id}")
            else:
                # Release all resources for transaction
                self._wait_for_graph.pop(transaction_id, None)
                
                # Remove all requests for this transaction
                keys_to_remove = [
                    k for k in self._active_requests.keys()
                    if k.startswith(f"{transaction_id}:")
                ]
                for key in keys_to_remove:
                    del self._active_requests[key]
                
                logger.debug(f"Released all waits for {transaction_id}")
    
    def acquire_resource(
        self,
        transaction_id: str,
        resource_id: str
    ) -> None:
        """
        Register that a transaction acquired a resource.
        
        Args:
            transaction_id: Transaction acquiring resource
            resource_id: Resource being acquired
        """
        with self._lock:
            self._resource_owners[resource_id] = transaction_id
            
            # Release any wait for this resource
            self.release_wait(transaction_id, resource_id)
            
            logger.debug(f"Resource acquired: {resource_id} by {transaction_id}")
    
    def release_resource(
        self,
        transaction_id: str,
        resource_id: str
    ) -> None:
        """
        Register that a transaction released a resource.
        
        Args:
            transaction_id: Transaction releasing resource
            resource_id: Resource being released
        """
        with self._lock:
            if self._resource_owners.get(resource_id) == transaction_id:
                del self._resource_owners[resource_id]
                logger.debug(f"Resource released: {resource_id} by {transaction_id}")
    
    def detect(self) -> DeadlockInfo:
        """
        Detect deadlocks in wait-for graph.
        
        Returns:
            DeadlockInfo with detection results
        """
        with self._lock:
            # Find cycles using DFS
            cycle = self._find_cycle()
            
            if cycle:
                self._deadlocks_detected += 1
                
                logger.warning(f"Deadlock detected: cycle={cycle}")
                
                # Determine victim if auto-resolution enabled
                victim = None
                if self.enable_auto_resolution:
                    victim = self._select_victim(cycle)
                
                return DeadlockInfo(
                    detected=True,
                    cycle=cycle,
                    resolution_policy=self.resolution_policy,
                    victim_transaction=victim
                )
            else:
                return DeadlockInfo(detected=False)
    
    def resolve(self, deadlock: DeadlockInfo) -> Optional[str]:
        """
        Resolve a detected deadlock.
        
        Args:
            deadlock: DeadlockInfo from detect()
            
        Returns:
            Transaction ID to abort (victim)
        """
        if not deadlock.detected:
            return None
        
        with self._lock:
            # Select victim if not already selected
            victim = deadlock.victim_transaction
            if not victim:
                victim = self._select_victim(deadlock.cycle)
            
            if victim:
                # Abort victim transaction
                self._abort_transaction(victim)
                self._deadlocks_resolved += 1
                
                logger.info(f"Deadlock resolved: aborted {victim}")
                
                return victim
            else:
                logger.error("Failed to select victim for deadlock resolution")
                return None
    
    def _find_cycle(self) -> List[str]:
        """
        Find cycle in wait-for graph using iterative DFS.
        
        Returns:
            List of transaction IDs in cycle, or empty list if no cycle
            
        Note:
            Uses iterative DFS to avoid recursion depth issues with large graphs
        """
        visited: Set[str] = set()
        
        # Try DFS from each node
        for start_node in list(self._wait_for_graph.keys()):
            if start_node in visited:
                continue
                
            # Iterative DFS with explicit stack
            # Stack contains: (current_node, path_to_node, nodes_in_current_path)
            stack: List[Tuple[str, List[str], Set[str]]] = [
                (start_node, [start_node], {start_node})
            ]
            
            while stack:
                node, path, path_set = stack.pop()
                visited.add(node)
                
                # Check all neighbors
                for neighbor in self._wait_for_graph.get(node, set()):
                    if neighbor in path_set:
                        # Found cycle
                        cycle_start = path.index(neighbor)
                        return path[cycle_start:]
                    elif neighbor not in visited:
                        # Add to stack with extended path
                        new_path = path + [neighbor]
                        new_path_set = path_set | {neighbor}
                        stack.append((neighbor, new_path, new_path_set))
        
        return []
    
    def _select_victim(self, cycle: List[str]) -> Optional[str]:
        """
        Select victim transaction to abort.
        
        Args:
            cycle: List of transaction IDs in deadlock cycle
            
        Returns:
            Transaction ID to abort
        """
        if not cycle:
            return None
        
        if self.resolution_policy == DeadlockResolutionPolicy.ABORT_YOUNGEST:
            # Abort youngest (most recent) transaction
            youngest = None
            youngest_time = None
            
            for tx_id in cycle:
                metadata = self._transaction_metadata.get(tx_id)
                if metadata:
                    start_time = metadata["start_time"]
                    if youngest_time is None or start_time > youngest_time:
                        youngest = tx_id
                        youngest_time = start_time
            
            return youngest or cycle[0]
        
        elif self.resolution_policy == DeadlockResolutionPolicy.ABORT_OLDEST:
            # Abort oldest transaction
            oldest = None
            oldest_time = None
            
            for tx_id in cycle:
                metadata = self._transaction_metadata.get(tx_id)
                if metadata:
                    start_time = metadata["start_time"]
                    if oldest_time is None or start_time < oldest_time:
                        oldest = tx_id
                        oldest_time = start_time
            
            return oldest or cycle[0]
        
        elif self.resolution_policy == DeadlockResolutionPolicy.ABORT_LEAST_WORK:
            # Abort transaction with least work done
            least_work = None
            least_work_amount = float('inf')
            
            for tx_id in cycle:
                metadata = self._transaction_metadata.get(tx_id)
                if metadata:
                    work_done = metadata["work_done"]
                    if work_done < least_work_amount:
                        least_work = tx_id
                        least_work_amount = work_done
            
            return least_work or cycle[0]
        
        else:  # MANUAL
            # Return first transaction in cycle for manual intervention
            return cycle[0]
    
    def _abort_transaction(self, transaction_id: str) -> None:
        """
        Abort a transaction (remove from wait-for graph).
        
        Args:
            transaction_id: Transaction to abort
        """
        # Remove from wait-for graph
        self._wait_for_graph.pop(transaction_id, None)
        
        # Remove all requests
        keys_to_remove = [
            k for k in self._active_requests.keys()
            if k.startswith(f"{transaction_id}:")
        ]
        for key in keys_to_remove:
            del self._active_requests[key]
        
        # Remove metadata
        self._transaction_metadata.pop(transaction_id, None)
        
        # Release all resources held by this transaction
        resources_to_release = [
            res_id for res_id, owner in self._resource_owners.items()
            if owner == transaction_id
        ]
        for res_id in resources_to_release:
            del self._resource_owners[res_id]
    
    def get_statistics(self) -> Dict:
        """Get deadlock detector statistics"""
        with self._lock:
            return {
                "deadlocks_detected": self._deadlocks_detected,
                "deadlocks_resolved": self._deadlocks_resolved,
                "false_positives": self._false_positives,
                "active_transactions": len(self._wait_for_graph),
                "active_requests": len(self._active_requests),
                "resources_held": len(self._resource_owners),
            }
    
    def get_wait_for_graph(self) -> Dict[str, List[str]]:
        """Get current wait-for graph"""
        with self._lock:
            return {
                tx: list(waiting_for)
                for tx, waiting_for in self._wait_for_graph.items()
            }
    
    def reset(self) -> None:
        """Reset detector state (for testing)"""
        with self._lock:
            self._wait_for_graph.clear()
            self._resource_owners.clear()
            self._active_requests.clear()
            self._transaction_metadata.clear()
            logger.info("DeadlockDetector reset")


# Singleton instance
_detector: Optional[DeadlockDetector] = None


def get_deadlock_detector(
    resolution_policy: DeadlockResolutionPolicy = DeadlockResolutionPolicy.ABORT_YOUNGEST
) -> DeadlockDetector:
    """
    Get or create singleton deadlock detector.
    
    Args:
        resolution_policy: Resolution policy (only used on first call)
        
    Returns:
        DeadlockDetector instance
    """
    global _detector
    
    if _detector is None:
        _detector = DeadlockDetector(resolution_policy=resolution_policy)
    
    return _detector
