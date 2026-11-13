#!/usr/bin/env python3
"""
Restore Script for Mahoun Platform
===================================

Restore ledger and Neo4j database from backup archives.

Usage:
    python scripts/restore.py ARCHIVE_PATH [--force] [--backup-existing]
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def detect_archive_type(archive_path: Path) -> str:
    """
    Determine if archive is ledger or neo4j backup.
    
    Args:
        archive_path: Path to the backup archive
        
    Returns:
        'ledger' or 'neo4j'
        
    Raises:
        ValueError: If archive type cannot be determined
    """
    filename = archive_path.name
    
    if filename.startswith("ledger_backup_") and filename.endswith(".tar.gz"):
        return "ledger"
    elif filename.startswith("neo4j_backup_") and filename.endswith(".dump"):
        return "neo4j"
    else:
        raise ValueError(
            f"Cannot determine archive type from filename: {filename}. "
            "Expected format: ledger_backup_YYYYMMDD_HHMMSS.tar.gz or neo4j_backup_YYYYMMDD_HHMMSS.dump"
        )


def verify_archive_integrity(archive_path: Path) -> bool:
    """
    Check if tar.gz archive is valid and not corrupted.
    
    Args:
        archive_path: Path to the backup archive
        
    Returns:
        True if archive is valid
        
    Raises:
        tarfile.ReadError: If archive is corrupted
    """
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            # Try to list members to verify integrity
            tar.getmembers()
        return True
    except tarfile.ReadError as e:
        logger.error(f"Archive is corrupted or invalid: {archive_path}")
        raise tarfile.ReadError(f"Archive is corrupted or invalid: {archive_path}") from e


def create_safety_backup(target_dir: Path) -> Optional[Path]:
    """
    Create a safety backup of existing directory before overwriting.
    
    Args:
        target_dir: Directory to backup
        
    Returns:
        Path to safety backup, or None if target doesn't exist
    """
    if not target_dir.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_backup_name = f"{target_dir.name}_safety_backup_{timestamp}"
    safety_backup_path = target_dir.parent / safety_backup_name
    
    logger.info(f"Creating safety backup: {safety_backup_path}")
    shutil.copytree(target_dir, safety_backup_path)
    
    return safety_backup_path


def restore_ledger(archive_path: Path, force: bool = False, backup_existing: bool = True) -> None:
    """
    Extract ledger backup to ledger directory.
    
    Args:
        archive_path: Path to the ledger backup archive
        force: If True, overwrite existing ledger without confirmation
        backup_existing: If True, create safety backup before overwriting
        
    Raises:
        FileExistsError: If ledger exists and force=False
        tarfile.ReadError: If archive is corrupted
    """
    ledger_dir = Path("ledger")
    
    # Check if ledger directory exists
    if ledger_dir.exists() and not force:
        logger.error(f"Ledger directory exists at {ledger_dir}. Use --force to overwrite")
        raise FileExistsError(f"Target directory exists. Use --force to overwrite")
    
    # Verify archive integrity
    logger.info("Verifying archive integrity...")
    verify_archive_integrity(archive_path)
    
    # Create safety backup if requested
    safety_backup = None
    if ledger_dir.exists() and backup_existing:
        safety_backup = create_safety_backup(ledger_dir)
    
    # Remove existing ledger directory
    if ledger_dir.exists():
        logger.info(f"Removing existing ledger directory: {ledger_dir}")
        shutil.rmtree(ledger_dir)
    
    # Extract archive
    logger.info(f"Restoring ledger from {archive_path}")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=".")
        
        # Count restored files
        file_count = sum(1 for _ in ledger_dir.rglob("*") if _.is_file())
        
        logger.info(f"Ledger restore completed successfully")
        print(f"\nRestore Summary:")
        print(f"  Restored files: {file_count}")
        print(f"  Target directory: {ledger_dir.absolute()}")
        if safety_backup:
            print(f"  Safety backup: {safety_backup.absolute()}")
        
    except Exception as e:
        logger.error(f"Failed to restore ledger: {e}")
        # Try to restore from safety backup
        if safety_backup and safety_backup.exists():
            logger.info(f"Attempting to restore from safety backup...")
            if ledger_dir.exists():
                shutil.rmtree(ledger_dir)
            shutil.copytree(safety_backup, ledger_dir)
            logger.info("Restored from safety backup")
        raise


def restore_neo4j(archive_path: Path, force: bool = False) -> None:
    """
    Restore Neo4j database from dump file.
    
    Args:
        archive_path: Path to the Neo4j dump file
        force: If True, overwrite existing database without confirmation
        
    Raises:
        RuntimeError: If Neo4j is currently running
        RuntimeError: If neo4j-admin load fails
    """
    # Check if Neo4j is configured
    neo4j_uri = os.getenv("NEO4J_URI")
    if not neo4j_uri:
        logger.error("NEO4J_URI not set. Cannot restore Neo4j backup")
        raise RuntimeError("NEO4J_URI not set. Cannot restore Neo4j backup")
    
    # Check if neo4j-admin command exists
    result = subprocess.run(
        ["which", "neo4j-admin"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        logger.error("neo4j-admin command not found. Is Neo4j installed?")
        raise RuntimeError("neo4j-admin command not found. Is Neo4j installed?")
    
    # Check if Neo4j is running (simplified check)
    logger.warning("Please ensure Neo4j is stopped before restoring")
    logger.warning("This is a placeholder - implement actual Neo4j restore logic based on your setup")
    
    logger.info(f"Neo4j restore from {archive_path} would be performed here")
    print(f"\nRestore Summary:")
    print(f"  Archive: {archive_path.absolute()}")
    print(f"  Note: Neo4j restore requires neo4j-admin load command")


def main():
    """Main entry point for restore script."""
    parser = argparse.ArgumentParser(
        description="Restore Mahoun ledger or Neo4j database from backup"
    )
    parser.add_argument(
        "archive_path",
        type=Path,
        help="Path to backup archive"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing data without confirmation"
    )
    parser.add_argument(
        "--backup-existing",
        action="store_true",
        default=True,
        help="Create safety backup before overwriting (default: True)"
    )
    
    args = parser.parse_args()
    
    # Check if archive exists
    if not args.archive_path.exists():
        logger.error(f"Backup archive not found: {args.archive_path}")
        print(f"Error: Backup archive not found: {args.archive_path}")
        sys.exit(1)
    
    exit_code = 0
    
    try:
        # Detect archive type
        archive_type = detect_archive_type(args.archive_path)
        logger.info(f"Detected archive type: {archive_type}")
        
        # Restore based on type
        if archive_type == "ledger":
            restore_ledger(args.archive_path, args.force, args.backup_existing)
        elif archive_type == "neo4j":
            restore_neo4j(args.archive_path, args.force)
        
    except ValueError as e:
        logger.error(str(e))
        exit_code = 1
    except FileNotFoundError as e:
        logger.error(str(e))
        exit_code = 1
    except FileExistsError as e:
        logger.error(str(e))
        exit_code = 3
    except tarfile.ReadError as e:
        logger.error(str(e))
        exit_code = 2
    except RuntimeError as e:
        logger.error(str(e))
        exit_code = 4
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        exit_code = 1
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
