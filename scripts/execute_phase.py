#!/usr/bin/env python3
"""
Production-Grade Phase Execution Engine.

Automated, safe, and reversible phase execution.
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Callable, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OperationStatus(Enum):
    """Status of operation."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PhaseStatus(Enum):
    """Status of phase."""
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Operation:
    """Single atomic operation."""
    name: str
    description: str
    execute: Callable[[], bool]
    rollback: Optional[Callable[[], bool]] = None
    status: OperationStatus = OperationStatus.PENDING
    duration: float = 0.0
    error: Optional[str] = None


class PhaseExecutor:
    """Phase executor with rollback."""
    
    def __init__(self, phase: int, name: str, dry_run: bool = False):
        self.phase = phase
        self.name = name
        self.dry_run = dry_run
        self.operations: List[Operation] = []
        self.start_time = datetime.now()
    
    def add_operation(
        self,
        name: str,
        description: str,
        execute: Callable[[], bool],
        rollback: Optional[Callable[[], bool]] = None
    ) -> None:
        """Add operation to phase."""
        self.operations.append(Operation(
            name=name,
            description=description,
            execute=execute,
            rollback=rollback
        ))
    
    def execute(self) -> bool:
        """Execute all operations."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Phase {self.phase}: {self.name}")
        logger.info(f"{'='*60}\n")
        
        for i, op in enumerate(self.operations, 1):
            logger.info(f"[{i}/{len(self.operations)}] {op.name}")
            
            if self.dry_run:
                logger.info(f"  [DRY RUN] {op.description}")
                op.status = OperationStatus.SKIPPED
                continue
            
            start = time.time()
            try:
                success = op.execute()
                op.duration = time.time() - start
                
                if success:
                    op.status = OperationStatus.SUCCESS
                    logger.info(f"  ✓ {op.description} ({op.duration:.2f}s)")
                else:
                    op.status = OperationStatus.FAILED
                    logger.error(f"  ✗ {op.description} failed")
                    self.rollback_all()
                    return False
                    
            except Exception as e:
                op.duration = time.time() - start
                op.status = OperationStatus.FAILED
                op.error = str(e)
                logger.error(f"  ✗ {op.description}: {e}")
                self.rollback_all()
                return False
        
        logger.info(f"\n✅ Phase {self.phase} completed\n")
        return True
    
    def rollback_all(self) -> None:
        """Rollback all successful operations."""
        logger.warning("🔄 Rolling back...")
        
        for op in reversed(self.operations):
            if op.status == OperationStatus.SUCCESS and op.rollback:
                logger.info(f"  ↶ {op.name}")
                try:
                    op.rollback()
                except Exception as e:
                    logger.error(f"  ✗ Rollback failed: {e}")


def execute_phase_0(executor: PhaseExecutor) -> None:
    """Phase 0: Preparation."""
    
    def create_backup_script() -> bool:
        # Already exists
        return Path("scripts/backup_core.py").exists()
    
    def create_restore_script() -> bool:
        # Already exists
        return Path("scripts/restore.py").exists()
    
    def create_validation_script() -> bool:
        # Already exists
        return Path("scripts/validate_phase.py").exists()
    
    def create_backup_dir() -> bool:
        Path("backups").mkdir(exist_ok=True)
        return True
    
    def run_baseline_tests() -> bool:
        result = subprocess.run(
            ["pytest", "tests/", "-q", "--tb=no"],
            capture_output=True,
            timeout=300
        )
        return result.returncode == 0
    
    executor.add_operation(
        "backup_script",
        "Verify backup script exists",
        create_backup_script
    )
    executor.add_operation(
        "restore_script",
        "Verify restore script exists",
        create_restore_script
    )
    executor.add_operation(
        "validation_script",
        "Verify validation script exists",
        create_validation_script
    )
    executor.add_operation(
        "backup_dir",
        "Create backup directory",
        create_backup_dir
    )
    executor.add_operation(
        "baseline_tests",
        "Run baseline test suite",
        run_baseline_tests
    )


def execute_phase_1(executor: PhaseExecutor) -> None:
    """Phase 1: Create directories."""
    
    def create_infrastructure() -> bool:
        path = Path("mahoun/infrastructure")
        path.mkdir(exist_ok=True)
        (path / "__init__.py").write_text('"""Infrastructure layer."""\n')
        return True
    
    def rollback_infrastructure() -> bool:
        path = Path("mahoun/infrastructure")
        if path.exists():
            import shutil
            shutil.rmtree(path)
        return True
    
    def create_monitoring() -> bool:
        path = Path("mahoun/infrastructure/monitoring")
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").write_text('"""Monitoring infrastructure."""\n')
        return True
    
    def create_observability() -> bool:
        path = Path("mahoun/infrastructure/observability")
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").write_text('"""Observability infrastructure."""\n')
        return True
    
    def create_llm() -> bool:
        path = Path("mahoun/infrastructure/llm")
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").write_text('"""LLM infrastructure."""\n')
        return True
    
    def create_rag() -> bool:
        path = Path("mahoun/infrastructure/rag")
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").write_text('"""RAG infrastructure."""\n')
        return True
    
    executor.add_operation(
        "infrastructure_dir",
        "Create infrastructure directory",
        create_infrastructure,
        rollback_infrastructure
    )
    executor.add_operation(
        "monitoring_dir",
        "Create monitoring subdirectory",
        create_monitoring
    )
    executor.add_operation(
        "observability_dir",
        "Create observability subdirectory",
        create_observability
    )
    executor.add_operation(
        "llm_dir",
        "Create LLM subdirectory",
        create_llm
    )
    executor.add_operation(
        "rag_dir",
        "Create RAG subdirectory",
        create_rag
    )


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Execute phase")
    parser.add_argument("phase", type=int, help="Phase number")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    
    args = parser.parse_args()
    
    phase_map = {
        0: ("Preparation", execute_phase_0),
        1: ("Create Directories", execute_phase_1),
    }
    
    if args.phase not in phase_map:
        logger.error(f"Phase {args.phase} not implemented")
        return 1
    
    name, setup_func = phase_map[args.phase]
    executor = PhaseExecutor(args.phase, name, args.dry_run)
    setup_func(executor)
    
    success = executor.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
