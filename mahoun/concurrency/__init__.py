"""
Concurrency Management
======================

Production-grade concurrency primitives for distributed systems.

Components:
- DistributedLock: Redis-based distributed locks
- DeadlockDetector: Runtime deadlock detection
"""

from .distributed_lock import DistributedLock, LockConfig, LockAcquisitionError
from .deadlock_detector import (
    DeadlockDetector,
    DeadlockInfo,
    DeadlockResolutionPolicy,
    ResourceRequest,
    get_deadlock_detector,
)

__all__ = [
    "DistributedLock",
    "LockConfig",
    "LockAcquisitionError",
    "DeadlockDetector",
    "DeadlockInfo",
    "DeadlockResolutionPolicy",
    "ResourceRequest",
    "get_deadlock_detector",
]
