#!/usr/bin/env python3
"""
Automated Execution: Phase 0-3
===============================

Safely execute Phase 0 through Phase 3 with full validation.

This script:
1. Creates backup before starting
2. Executes Phase 0 (Preparation)
3. Executes Phase 1 (Create directories)
4. Executes Phase 2 (Copy files)
5. Executes Phase 3 (Add deprecations)
6. Validates each phase
7. Creates git checkpoints
8. Provides rollback on failure

Usage:
    python scripts/execute_phases_0_to_3.py [--dry-run] [--skip-backup] [--auto-commit]
"""

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

from phase_operations import (
    Phase1Operations,
    Phase2Operations,
    Phase3Operations,
    PhaseOperationError,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('phase_0_to_3_execution.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


class PhaseExecutionError(Exception):
    """Phase execution error."""
    pass


class Phase0to3Executor:
    """Execute Phase 0-3 with full safety checks."""
    
    def __init__(
        self,
        dry_run: bool = False,
        skip_backup: bool = False,
        auto_commit: bool = False
    ):
        """
        Initialize executor.
        
        Args:
            dry_run: If True, simulate without making changes
            skip_backup: If True, skip backup creation
            auto_commit: If True, auto-commit after each phase
        """
        self.dry_run = dry_run
        self.skip_backup = skip_backup
        self.auto_commit = auto_commit
        self.start_time = datetime.now()
        self.backup_path: Optional[Path] = None
    
    def run_command(self, cmd: str, timeout: int = 300) -> bool:
        """Run shell command and return success."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd}")
            return False
        except Exception as e:
            logger.error(f"Command failed: {cmd}: {e}")
            return False
    
    def validate_preconditions(self) -> bool:
        """Validate system is ready for execution."""
        logger.info("🔍 Validating preconditions...")
        
        checks = [
            ("Git working directory clean", "git status --porcelain"),
            ("All tests passing", "pytest tests/ -q --tb=no -x"),
            ("Scripts exist", "test -f scripts/backup_core.py"),
        ]
        
        for check_name, cmd in checks:
            logger.info(f"  Checking: {check_name}...")
            
            if "Git working directory" in check_name:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if len(result.stdout.strip()) > 0:
                    logger.error(f"  ✗ {check_name}: Working directory not clean")
                    return False
            elif "tests passing" in check_name:
                if not self.run_command(cmd, timeout=300):
                    logger.error(f"  ✗ {check_name}: Tests failing")
                    return False
            else:
                if not self.run_command(cmd):
                    logger.error(f"  ✗ {check_name}")
                    return False
            
            logger.info(f"  ✓ {check_name}")
        
        logger.info("✓ All preconditions met\n")
        return True
    
    def create_backup(self) -> bool:
        """Create backup before execution."""
        if self.skip_backup:
            logger.info("⏭️  Skipping backup (--skip-backup)\n")
            return True
        
        if self.dry_run:
            logger.info("[DRY RUN] Would create backup\n")
            return True
        
        logger.info("📦 Creating backup...")
        
        try:
            result = subprocess.run(
                ["python", "scripts/backup_core.py"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Extract backup path from output
            for line in result.stdout.split('\n'):
                if "Backup created:" in line:
                    self.backup_path = Path(line.split(":")[-1].strip())
                    logger.info(f"✓ Backup created: {self.backup_path}\n")
                    return True
            
            logger.info("✓ Backup created\n")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ Backup failed: {e}")
            return False
    
    def execute_phase_0(self) -> bool:
        """Execute Phase 0: Preparation."""
        logger.info("="*60)
        logger.info("Phase 0: Preparation")
        logger.info("="*60 + "\n")
        
        if self.dry_run:
            logger.info("[DRY RUN] Phase 0 operations\n")
            return True
        
        # Phase 0 is mostly validation - scripts already exist
        checks = [
            "scripts/backup_core.py",
            "scripts/restore.py",
            "scripts/validate_phase.py",
            "scripts/phase_operations.py",
        ]
        
        for script in checks:
            if not Path(script).exists():
                logger.error(f"✗ Missing: {script}")
                return False
            logger.info(f"✓ Verified: {script}")
        
        # Create backups directory
        Path("backups").mkdir(exist_ok=True)
        logger.info("✓ Backups directory ready")
        
        logger.info("\n✅ Phase 0 completed\n")
        return True
    
    def execute_phase_1(self) -> bool:
        """Execute Phase 1: Create directories."""
        logger.info("="*60)
        logger.info("Phase 1: Create Directories")
        logger.info("="*60 + "\n")
        
        operations = [
            ("Infrastructure directory", Phase1Operations.create_infrastructure_dir),
            ("Monitoring subdirectory", Phase1Operations.create_monitoring_dir),
            ("Observability subdirectory", Phase1Operations.create_observability_dir),
        ]
        
        for name, operation in operations:
            logger.info(f"  Creating: {name}")
            try:
                if not operation(dry_run=self.dry_run):
                    logger.error(f"  ✗ Failed: {name}")
                    return False
                logger.info(f"  ✓ {name}")
            except PhaseOperationError as e:
                logger.error(f"  ✗ {name}: {e}")
                return False
        
        logger.info("\n✅ Phase 1 completed\n")
        
        if self.auto_commit and not self.dry_run:
            self.git_commit("feat(phase-1): create infrastructure directories", "PHASE_1_COMPLETE")
        
        return True
    
    def execute_phase_2(self) -> bool:
        """Execute Phase 2: Copy files."""
        logger.info("="*60)
        logger.info("Phase 2: Copy Files")
        logger.info("="*60 + "\n")
        
        operations = [
            ("health_cache.py", Phase2Operations.copy_health_cache),
            ("metrics module", Phase2Operations.copy_metrics_module),
            ("monitoring module", Phase2Operations.copy_monitoring_module),
        ]
        
        for name, operation in operations:
            logger.info(f"  Copying: {name}")
            try:
                success, dest = operation(dry_run=self.dry_run)
                if not success:
                    logger.error(f"  ✗ Failed: {name}")
                    return False
                if dest:
                    logger.info(f"  ✓ {name} → {dest}")
                else:
                    logger.info(f"  ✓ {name}")
            except PhaseOperationError as e:
                logger.error(f"  ✗ {name}: {e}")
                return False
        
        logger.info("\n✅ Phase 2 completed\n")
        
        if self.auto_commit and not self.dry_run:
            self.git_commit("feat(phase-2): copy infrastructure files", "PHASE_2_COMPLETE")
        
        return True
    
    def execute_phase_3(self) -> bool:
        """Execute Phase 3: Add deprecation warnings."""
        logger.info("="*60)
        logger.info("Phase 3: Add Deprecation Warnings")
        logger.info("="*60 + "\n")
        
        operations = [
            ("health_cache.py", Phase3Operations.add_deprecation_to_health_cache),
            ("metrics module", Phase3Operations.add_deprecation_to_metrics),
            ("monitoring module", Phase3Operations.add_deprecation_to_monitoring),
        ]
        
        for name, operation in operations:
            logger.info(f"  Adding deprecation: {name}")
            try:
                if not operation(dry_run=self.dry_run):
                    logger.error(f"  ✗ Failed: {name}")
                    return False
                logger.info(f"  ✓ {name}")
            except PhaseOperationError as e:
                logger.error(f"  ✗ {name}: {e}")
                return False
        
        logger.info("\n✅ Phase 3 completed\n")
        
        if self.auto_commit and not self.dry_run:
            self.git_commit("feat(phase-3): add deprecation warnings", "PHASE_3_COMPLETE")
        
        return True
    
    def validate_phase(self, phase: int) -> bool:
        """Validate phase completion."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would validate Phase {phase}\n")
            return True
        
        logger.info(f"🔍 Validating Phase {phase}...")
        
        result = subprocess.run(
            ["python", "scripts/validate_phase.py", str(phase)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"✓ Phase {phase} validation passed\n")
            return True
        else:
            logger.error(f"✗ Phase {phase} validation failed")
            logger.error(result.stdout)
            logger.error(result.stderr)
            return False
    
    def git_commit(self, message: str, tag: str) -> None:
        """Commit changes and create tag."""
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", message], check=True)
            subprocess.run(["git", "tag", "-f", tag], check=True)
            logger.info(f"✓ Committed: {message}")
            logger.info(f"✓ Tagged: {tag}\n")
        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠ Git operation failed: {e}\n")
    
    def execute_all(self) -> bool:
        """Execute all phases 0-3."""
        logger.info("\n" + "="*60)
        logger.info("MAHOUN CORE CLEANUP: Phase 0-3 Execution")
        logger.info("="*60)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Auto-commit: {self.auto_commit}")
        logger.info(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60 + "\n")
        
        # Validate preconditions
        if not self.validate_preconditions():
            logger.error("❌ Precondition validation failed")
            return False
        
        # Create backup
        if not self.create_backup():
            logger.error("❌ Backup creation failed")
            return False
        
        # Execute phases
        phases = [
            (0, self.execute_phase_0),
            (1, self.execute_phase_1),
            (2, self.execute_phase_2),
            (3, self.execute_phase_3),
        ]
        
        for phase_num, phase_func in phases:
            if not phase_func():
                logger.error(f"❌ Phase {phase_num} failed")
                self.show_rollback_instructions()
                return False
            
            # Validate phase (skip for Phase 0)
            if phase_num > 0:
                if not self.validate_phase(phase_num):
                    logger.error(f"❌ Phase {phase_num} validation failed")
                    self.show_rollback_instructions()
                    return False
        
        # Success summary
        duration = (datetime.now() - self.start_time).total_seconds()
        
        logger.info("="*60)
        logger.info("✅ ALL PHASES COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        logger.info(f"Duration: {duration:.1f}s")
        logger.info(f"Phases: 0, 1, 2, 3")
        if self.backup_path:
            logger.info(f"Backup: {self.backup_path}")
        logger.info("="*60 + "\n")
        
        return True
    
    def show_rollback_instructions(self) -> None:
        """Show rollback instructions on failure."""
        logger.error("\n" + "="*60)
        logger.error("ROLLBACK INSTRUCTIONS")
        logger.error("="*60)
        
        if self.backup_path:
            logger.error(f"\nOption 1: Restore from backup")
            logger.error(f"  python scripts/restore.py {self.backup_path}")
        
        logger.error(f"\nOption 2: Git rollback")
        logger.error(f"  git reset --hard HEAD~1")
        logger.error(f"  pytest tests/ -v")
        
        logger.error("\n" + "="*60 + "\n")


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Execute Phase 0-3 of core cleanup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without making changes"
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backup creation (not recommended)"
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Auto-commit after each phase"
    )
    
    args = parser.parse_args()
    
    executor = Phase0to3Executor(
        dry_run=args.dry_run,
        skip_backup=args.skip_backup,
        auto_commit=args.auto_commit
    )
    
    try:
        success = executor.execute_all()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Execution interrupted by user")
        executor.show_rollback_instructions()
        return 130
    except Exception as e:
        logger.exception(f"\n❌ Unexpected error: {e}")
        executor.show_rollback_instructions()
        return 1


if __name__ == "__main__":
    sys.exit(main())
