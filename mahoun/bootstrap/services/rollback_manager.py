"""
Rollback Manager for Transaction Cleanup

Extracted from: mahoun/bootstrap/executors/ai_ml_components.py 
                (lines 463-505, 821-864, 1284-1351)
Responsibility: Manage transactional rollback for failed model loads, 
               ensuring clean state and resource cleanup.

Architecture:
- Savepoint/checkpoint pattern for rollback
- Resource cleanup tracking (models, connections, temp files)
- Async/await for non-blocking operations
- Comprehensive logging for audit trail
"""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class RollbackStatus(str, Enum):
    """Rollback operation status"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"  # Some cleanup failed
    FAILED = "failed"


class ResourceType(str, Enum):
    """Types of resources that can be rolled back"""
    MODEL = "model"
    FILE = "file"
    DIRECTORY = "directory"
    CONNECTION = "connection"
    MEMORY = "memory"
    CUSTOM = "custom"


@dataclass
class ResourceHandle:
    """Handle to a resource that can be rolled back"""
    resource_type: ResourceType
    identifier: str
    cleanup_func: Callable[[], Any]  # Can be sync or async
    metadata: Dict[str, Any] = field(default_factory=dict)
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False


@dataclass
class Checkpoint:
    """Savepoint for rollback"""
    checkpoint_id: str
    timestamp: datetime
    resources: List[ResourceHandle] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackResult:
    """Result of a rollback operation"""
    status: RollbackStatus
    checkpoint_id: str
    resources_cleaned: int
    resources_failed: int
    duration_seconds: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class RollbackManager:
    """
    Production-grade rollback manager for transactional cleanup
    
    Features:
    - Savepoint/checkpoint pattern
    - Resource tracking (models, files, connections)
    - Async/await cleanup
    - Comprehensive error handling
    - Audit trail logging
    
    Example:
        manager = RollbackManager()
        
        # Create checkpoint
        checkpoint = manager.create_checkpoint("model-load-v1")
        
        # Register resources
        manager.register_resource(
            checkpoint_id=checkpoint.checkpoint_id,
            resource_type=ResourceType.MODEL,
            identifier="embedding-model",
            cleanup_func=lambda: model.unload()
        )
        
        try:
            # ... do work ...
            pass
        except Exception:
            # Rollback on failure
            result = await manager.rollback(checkpoint.checkpoint_id)
            print(f"Rolled back {result.resources_cleaned} resources")
    """
    
    def __init__(self):
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._resource_registry: Dict[str, List[ResourceHandle]] = defaultdict(list)
        self._cleanup_order: List[ResourceType] = [
            ResourceType.MEMORY,      # Free memory first
            ResourceType.MODEL,        # Unload models
            ResourceType.CONNECTION,   # Close connections
            ResourceType.FILE,         # Delete files
            ResourceType.DIRECTORY,    # Remove directories
            ResourceType.CUSTOM        # Custom cleanup last
        ]
    
    def create_checkpoint(
        self,
        checkpoint_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Checkpoint:
        """
        Create a new checkpoint/savepoint
        
        Args:
            checkpoint_id: Unique identifier for checkpoint
            metadata: Additional context
        
        Returns:
            Checkpoint object
        """
        if checkpoint_id in self._checkpoints:
            raise ValueError(f"Checkpoint '{checkpoint_id}' already exists")
        
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )
        
        self._checkpoints[checkpoint_id] = checkpoint
        logger.info(f"Checkpoint created: {checkpoint_id}")
        
        return checkpoint
    
    def register_resource(
        self,
        checkpoint_id: str,
        resource_type: ResourceType,
        identifier: str,
        cleanup_func: Callable[[], Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> ResourceHandle:
        """
        Register a resource for potential rollback
        
        Args:
            checkpoint_id: Checkpoint to associate resource with
            resource_type: Type of resource
            identifier: Human-readable resource identifier
            cleanup_func: Function to cleanup resource (sync or async)
            metadata: Additional context
        
        Returns:
            ResourceHandle
        """
        if checkpoint_id not in self._checkpoints:
            raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
        
        handle = ResourceHandle(
            resource_type=resource_type,
            identifier=identifier,
            cleanup_func=cleanup_func,
            metadata=metadata or {}
        )
        
        self._checkpoints[checkpoint_id].resources.append(handle)
        self._resource_registry[checkpoint_id].append(handle)
        
        logger.debug(
            f"Resource registered: {resource_type.value}:{identifier} "
            f"(checkpoint={checkpoint_id})"
        )
        
        return handle
    
    async def rollback(
        self,
        checkpoint_id: str,
        ignore_errors: bool = False
    ) -> RollbackResult:
        """
        Rollback to checkpoint by cleaning up all registered resources
        
        Args:
            checkpoint_id: Checkpoint to rollback to
            ignore_errors: Continue cleanup even if some resources fail
        
        Returns:
            RollbackResult with cleanup status
        """
        if checkpoint_id not in self._checkpoints:
            raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
        
        checkpoint = self._checkpoints[checkpoint_id]
        resources = checkpoint.resources
        
        logger.info(
            f"Rolling back checkpoint '{checkpoint_id}' "
            f"({len(resources)} resources)"
        )
        
        start_time = datetime.utcnow()
        cleaned_count = 0
        failed_count = 0
        errors: List[str] = []
        warnings: List[str] = []
        
        # Group resources by type
        resources_by_type: Dict[ResourceType, List[ResourceHandle]] = defaultdict(list)
        for resource in resources:
            resources_by_type[resource.resource_type].append(resource)
        
        # Cleanup in defined order
        for resource_type in self._cleanup_order:
            if resource_type not in resources_by_type:
                continue
            
            type_resources = resources_by_type[resource_type]
            logger.info(
                f"Cleaning up {len(type_resources)} {resource_type.value} resources"
            )
            
            for resource in type_resources:
                try:
                    resource.cleanup_attempted = True
                    
                    # Run cleanup function (sync or async)
                    if asyncio.iscoroutinefunction(resource.cleanup_func):
                        await resource.cleanup_func()
                    else:
                        # Run sync function in executor
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, resource.cleanup_func)
                    
                    resource.cleanup_succeeded = True
                    cleaned_count += 1
                    
                    logger.debug(
                        f"Cleaned up: {resource.resource_type.value}:{resource.identifier}"
                    )
                
                except Exception as e:
                    resource.cleanup_succeeded = False
                    failed_count += 1
                    error_msg = (
                        f"Failed to cleanup {resource.resource_type.value}:"
                        f"{resource.identifier}: {e}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)
                    
                    if not ignore_errors:
                        # Stop rollback on first error
                        break
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Determine overall status
        if failed_count == 0:
            status = RollbackStatus.SUCCESS
        elif cleaned_count > 0:
            status = RollbackStatus.PARTIAL_SUCCESS
            warnings.append(
                f"{failed_count}/{len(resources)} resources failed to cleanup"
            )
        else:
            status = RollbackStatus.FAILED
        
        logger.info(
            f"Rollback complete: {status.value} "
            f"(cleaned={cleaned_count}, failed={failed_count}, "
            f"duration={duration:.2f}s)"
        )
        
        return RollbackResult(
            status=status,
            checkpoint_id=checkpoint_id,
            resources_cleaned=cleaned_count,
            resources_failed=failed_count,
            duration_seconds=duration,
            errors=errors,
            warnings=warnings
        )
    
    def remove_checkpoint(self, checkpoint_id: str):
        """
        Remove checkpoint and cleanup registry
        
        Use this after successful operation (no rollback needed)
        """
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
        
        if checkpoint_id in self._resource_registry:
            del self._resource_registry[checkpoint_id]
        
        logger.debug(f"Checkpoint removed: {checkpoint_id}")
    
    def exists(self, checkpoint_id: str) -> bool:
        """Check if a checkpoint exists"""
        return checkpoint_id in self._checkpoints
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get checkpoint by ID"""
        return self._checkpoints.get(checkpoint_id)
    
    def list_checkpoints(self) -> List[str]:
        """List all active checkpoint IDs"""
        return list(self._checkpoints.keys())
    
    def cleanup_all_checkpoints(self) -> int:
        """
        Emergency cleanup: remove all checkpoints
        
        Returns:
            Number of checkpoints removed
        """
        count = len(self._checkpoints)
        self._checkpoints.clear()
        self._resource_registry.clear()
        logger.warning(f"Emergency cleanup: removed {count} checkpoints")
        return count


# Convenience functions for common cleanup patterns

async def cleanup_model(model: Any) -> None:
    """Standard model cleanup"""
    if hasattr(model, 'unload'):
        if asyncio.iscoroutinefunction(model.unload):
            await model.unload()
        else:
            model.unload()
    elif hasattr(model, 'close'):
        if asyncio.iscoroutinefunction(model.close):
            await model.close()
        else:
            model.close()
    elif hasattr(model, '__del__'):
        del model


async def cleanup_file(file_path: Path) -> None:
    """Standard file cleanup"""
    if file_path.exists():
        file_path.unlink()
        logger.debug(f"Deleted file: {file_path}")


async def cleanup_directory(dir_path: Path) -> None:
    """Standard directory cleanup"""
    if dir_path.exists() and dir_path.is_dir():
        shutil.rmtree(dir_path)
        logger.debug(f"Deleted directory: {dir_path}")


async def cleanup_connection(connection: Any) -> None:
    """Standard connection cleanup"""
    if hasattr(connection, 'close'):
        if asyncio.iscoroutinefunction(connection.close):
            await connection.close()
        else:
            connection.close()
    elif hasattr(connection, 'disconnect'):
        if asyncio.iscoroutinefunction(connection.disconnect):
            await connection.disconnect()
        else:
            connection.disconnect()
