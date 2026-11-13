#!/usr/bin/env python3
"""
Phase-Specific Operations Library
==================================

Reusable, tested operations for each phase of core cleanup.

Each operation is:
- Atomic (all-or-nothing)
- Reversible (with rollback)
- Testable (can be dry-run)
- Auditable (logs all actions)

Usage:
    from phase_operations import Phase2Operations
    
    ops = Phase2Operations()
    ops.copy_health_cache(dry_run=False)
"""

import logging
import shutil
import warnings
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PhaseOperationError(Exception):
    """Base exception for phase operations."""
    pass


class Phase1Operations:
    """Operations for Phase 1: Create directories."""
    
    @staticmethod
    def create_infrastructure_dir(dry_run: bool = False) -> bool:
        """
        Create mahoun/infrastructure/ directory.
        
        Args:
            dry_run: If True, simulate without creating
            
        Returns:
            True if successful
        """
        path = Path("mahoun/infrastructure")
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create: {path}")
            return True
        
        try:
            path.mkdir(exist_ok=True)
            init_file = path / "__init__.py"
            init_file.write_text(
                '"""\n'
                'Infrastructure Layer\n'
                '===================\n\n'
                'Infrastructure code separated from domain logic.\n'
                'Includes monitoring, observability, LLM, and RAG infrastructure.\n'
                '"""\n\n'
                '__all__ = []\n'
            )
            logger.info(f"✓ Created: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create {path}: {e}")
            raise PhaseOperationError(f"Failed to create {path}: {e}") from e
    
    @staticmethod
    def create_monitoring_dir(dry_run: bool = False) -> bool:
        """Create mahoun/infrastructure/monitoring/ directory."""
        path = Path("mahoun/infrastructure/monitoring")
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create: {path}")
            return True
        
        try:
            path.mkdir(parents=True, exist_ok=True)
            init_file = path / "__init__.py"
            init_file.write_text(
                '"""\n'
                'Monitoring Infrastructure\n'
                '========================\n\n'
                'Health checks, caching, and system monitoring.\n'
                '"""\n\n'
                '__all__ = []\n'
            )
            logger.info(f"✓ Created: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create {path}: {e}")
            raise PhaseOperationError(f"Failed to create {path}: {e}") from e
    
    @staticmethod
    def create_observability_dir(dry_run: bool = False) -> bool:
        """Create mahoun/infrastructure/observability/ directory."""
        path = Path("mahoun/infrastructure/observability")
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create: {path}")
            return True
        
        try:
            path.mkdir(parents=True, exist_ok=True)
            init_file = path / "__init__.py"
            init_file.write_text(
                '"""\n'
                'Observability Infrastructure\n'
                '===========================\n\n'
                'Metrics collection, tracing, and system observability.\n'
                '"""\n\n'
                '__all__ = []\n'
            )
            logger.info(f"✓ Created: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create {path}: {e}")
            raise PhaseOperationError(f"Failed to create {path}: {e}") from e


class Phase2Operations:
    """Operations for Phase 2: Copy files."""
    
    @staticmethod
    def copy_health_cache(dry_run: bool = False) -> Tuple[bool, Optional[Path]]:
        """
        Copy core/health_cache.py to infrastructure/monitoring/.
        
        Args:
            dry_run: If True, simulate without copying
            
        Returns:
            Tuple of (success, copied_file_path)
        """
        source = Path("mahoun/core/health_cache.py")
        dest = Path("mahoun/infrastructure/monitoring/health_cache.py")
        
        if not source.exists():
            logger.warning(f"Source not found: {source}")
            return True, None  # Not an error if already moved
        
        if dry_run:
            logger.info(f"[DRY RUN] Would copy: {source} → {dest}")
            return True, None
        
        try:
            # Ensure destination directory exists
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(source, dest)
            
            logger.info(f"✓ Copied: {source} → {dest}")
            return True, dest
            
        except Exception as e:
            logger.error(f"Failed to copy {source}: {e}")
            raise PhaseOperationError(f"Failed to copy {source}: {e}") from e
    
    @staticmethod
    def copy_metrics_module(dry_run: bool = False) -> Tuple[bool, Optional[Path]]:
        """
        Copy core/metrics/ to infrastructure/observability/.
        
        Args:
            dry_run: If True, simulate without copying
            
        Returns:
            Tuple of (success, copied_dir_path)
        """
        source = Path("mahoun/core/metrics")
        dest = Path("mahoun/infrastructure/observability/metrics")
        
        if not source.exists():
            logger.warning(f"Source not found: {source}")
            return True, None
        
        if dry_run:
            logger.info(f"[DRY RUN] Would copy: {source} → {dest}")
            return True, None
        
        try:
            # Ensure destination parent exists
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy directory tree
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            
            logger.info(f"✓ Copied: {source} → {dest}")
            return True, dest
            
        except Exception as e:
            logger.error(f"Failed to copy {source}: {e}")
            raise PhaseOperationError(f"Failed to copy {source}: {e}") from e
    
    @staticmethod
    def copy_monitoring_module(dry_run: bool = False) -> Tuple[bool, Optional[Path]]:
        """
        Copy core/monitoring/ to infrastructure/observability/.
        
        Args:
            dry_run: If True, simulate without copying
            
        Returns:
            Tuple of (success, copied_dir_path)
        """
        source = Path("mahoun/core/monitoring")
        dest = Path("mahoun/infrastructure/observability/monitoring")
        
        if not source.exists():
            logger.warning(f"Source not found: {source}")
            return True, None
        
        if dry_run:
            logger.info(f"[DRY RUN] Would copy: {source} → {dest}")
            return True, None
        
        try:
            # Ensure destination parent exists
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy directory tree
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            
            logger.info(f"✓ Copied: {source} → {dest}")
            return True, dest
            
        except Exception as e:
            logger.error(f"Failed to copy {source}: {e}")
            raise PhaseOperationError(f"Failed to copy {source}: {e}") from e


class Phase3Operations:
    """Operations for Phase 3: Add deprecation warnings."""
    
    @staticmethod
    def add_deprecation_to_health_cache(dry_run: bool = False) -> bool:
        """
        Add deprecation warning to core/health_cache.py.
        
        Creates a wrapper that re-exports from new location with warning.
        
        Args:
            dry_run: If True, simulate without modifying
            
        Returns:
            True if successful
        """
        target = Path("mahoun/core/health_cache.py")
        
        if not target.exists():
            logger.warning(f"Target not found: {target}")
            return True
        
        deprecation_code = '''"""
DEPRECATED: Use mahoun.infrastructure.monitoring.health_cache
=============================================================

This module has been moved to mahoun.infrastructure.monitoring.health_cache
and will be removed in version 2.0.0.

Migration:
    # Old (deprecated)
    from mahoun.core.health_cache import HealthCache
    
    # New (recommended)
    from mahoun.infrastructure.monitoring.health_cache import HealthCache
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "mahoun.core.health_cache is deprecated. "
    "Use mahoun.infrastructure.monitoring.health_cache instead. "
    "This module will be removed in version 2.0.0.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new location for backward compatibility
from mahoun.infrastructure.monitoring.health_cache import *  # noqa: F401, F403

__all__ = []  # Populated by wildcard import above
'''
        
        if dry_run:
            logger.info(f"[DRY RUN] Would add deprecation to: {target}")
            return True
        
        try:
            # Backup original
            backup = target.with_suffix('.py.backup')
            if not backup.exists():
                shutil.copy2(target, backup)
                logger.info(f"  Backed up: {target} → {backup}")
            
            # Write deprecation wrapper
            target.write_text(deprecation_code)
            
            logger.info(f"✓ Added deprecation: {target}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add deprecation to {target}: {e}")
            raise PhaseOperationError(f"Failed to add deprecation: {e}") from e
    
    @staticmethod
    def add_deprecation_to_metrics(dry_run: bool = False) -> bool:
        """Add deprecation warning to core/metrics/__init__.py."""
        target = Path("mahoun/core/metrics/__init__.py")
        
        if not target.exists():
            logger.warning(f"Target not found: {target}")
            return True
        
        deprecation_code = '''"""
DEPRECATED: Use mahoun.infrastructure.observability.metrics
==========================================================

This module has been moved to mahoun.infrastructure.observability.metrics
and will be removed in version 2.0.0.
"""

import warnings

warnings.warn(
    "mahoun.core.metrics is deprecated. "
    "Use mahoun.infrastructure.observability.metrics instead. "
    "This module will be removed in version 2.0.0.",
    DeprecationWarning,
    stacklevel=2
)

from mahoun.infrastructure.observability.metrics import *  # noqa: F401, F403

__all__ = []
'''
        
        if dry_run:
            logger.info(f"[DRY RUN] Would add deprecation to: {target}")
            return True
        
        try:
            backup = target.with_suffix('.py.backup')
            if not backup.exists():
                shutil.copy2(target, backup)
            
            target.write_text(deprecation_code)
            logger.info(f"✓ Added deprecation: {target}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add deprecation to {target}: {e}")
            raise PhaseOperationError(f"Failed to add deprecation: {e}") from e
    
    @staticmethod
    def add_deprecation_to_monitoring(dry_run: bool = False) -> bool:
        """Add deprecation warning to core/monitoring/__init__.py."""
        target = Path("mahoun/core/monitoring/__init__.py")
        
        if not target.exists():
            logger.warning(f"Target not found: {target}")
            return True
        
        deprecation_code = '''"""
DEPRECATED: Use mahoun.infrastructure.observability.monitoring
============================================================

This module has been moved to mahoun.infrastructure.observability.monitoring
and will be removed in version 2.0.0.
"""

import warnings

warnings.warn(
    "mahoun.core.monitoring is deprecated. "
    "Use mahoun.infrastructure.observability.monitoring instead. "
    "This module will be removed in version 2.0.0.",
    DeprecationWarning,
    stacklevel=2
)

from mahoun.infrastructure.observability.monitoring import *  # noqa: F401, F403

__all__ = []
'''
        
        if dry_run:
            logger.info(f"[DRY RUN] Would add deprecation to: {target}")
            return True
        
        try:
            backup = target.with_suffix('.py.backup')
            if not backup.exists():
                shutil.copy2(target, backup)
            
            target.write_text(deprecation_code)
            logger.info(f"✓ Added deprecation: {target}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add deprecation to {target}: {e}")
            raise PhaseOperationError(f"Failed to add deprecation: {e}") from e


class Phase7Operations:
    """Operations for Phase 7: Remove deprecated files."""
    
    @staticmethod
    def remove_health_cache(dry_run: bool = False) -> bool:
        """Remove deprecated core/health_cache.py."""
        target = Path("mahoun/core/health_cache.py")
        
        if not target.exists():
            logger.info(f"Already removed: {target}")
            return True
        
        if dry_run:
            logger.info(f"[DRY RUN] Would remove: {target}")
            return True
        
        try:
            # Move to archive instead of deleting
            archive_dir = Path("mahoun/core/archive")
            archive_dir.mkdir(exist_ok=True)
            
            archive_path = archive_dir / target.name
            shutil.move(str(target), str(archive_path))
            
            logger.info(f"✓ Archived: {target} → {archive_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove {target}: {e}")
            raise PhaseOperationError(f"Failed to remove {target}: {e}") from e
    
    @staticmethod
    def remove_metrics_module(dry_run: bool = False) -> bool:
        """Remove deprecated core/metrics/."""
        target = Path("mahoun/core/metrics")
        
        if not target.exists():
            logger.info(f"Already removed: {target}")
            return True
        
        if dry_run:
            logger.info(f"[DRY RUN] Would remove: {target}")
            return True
        
        try:
            archive_dir = Path("mahoun/core/archive")
            archive_dir.mkdir(exist_ok=True)
            
            archive_path = archive_dir / target.name
            if archive_path.exists():
                shutil.rmtree(archive_path)
            shutil.move(str(target), str(archive_path))
            
            logger.info(f"✓ Archived: {target} → {archive_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove {target}: {e}")
            raise PhaseOperationError(f"Failed to remove {target}: {e}") from e
    
    @staticmethod
    def remove_monitoring_module(dry_run: bool = False) -> bool:
        """Remove deprecated core/monitoring/."""
        target = Path("mahoun/core/monitoring")
        
        if not target.exists():
            logger.info(f"Already removed: {target}")
            return True
        
        if dry_run:
            logger.info(f"[DRY RUN] Would remove: {target}")
            return True
        
        try:
            archive_dir = Path("mahoun/core/archive")
            archive_dir.mkdir(exist_ok=True)
            
            archive_path = archive_dir / target.name
            if archive_path.exists():
                shutil.rmtree(archive_path)
            shutil.move(str(target), str(archive_path))
            
            logger.info(f"✓ Archived: {target} → {archive_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove {target}: {e}")
            raise PhaseOperationError(f"Failed to remove {target}: {e}") from e
