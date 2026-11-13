#!/usr/bin/env python3
"""
Backup Script for Mahoun Platform
==================================

Backup ledger and Neo4j database to timestamped archives.

Usage:
    python scripts/backup.py [--ledger] [--neo4j] [--output-dir DIR] [--dry-run]
"""

import argparse
import logging
import os
import subprocess
import sys
import tarfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_backup_filename(backup_type: str) -> str:
    """
    Generate timestamped backup filename.

    Args:
        backup_type: 'ledger' or 'neo4j'

    Returns:
        Filename like 'ledger_backup_20250214_143022.tar.gz'
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = ".tar.gz" if backup_type == "ledger" else ".dump"
    return f"{backup_type}_backup_{timestamp}{extension}"


def backup_ledger(output_dir: Path, dry_run: bool = False) -> Optional[Path]:
    """
    Create a tar.gz archive of the ledger directory.

    Args:
        output_dir: Directory to store the backup archive
        dry_run: If True, don't create archive, just show what would be done

    Returns:
        Path to the created archive, or None if dry_run

    Raises:
        FileNotFoundError: If ledger directory does not exist
        PermissionError: If cannot write to output directory
    """
    ledger_dir = Path("ledger")

    # Check if ledger directory exists
    if not ledger_dir.exists():
        logger.error(f"Ledger directory not found at {ledger_dir.absolute()}")
        raise FileNotFoundError(
            f"Ledger directory not found at {ledger_dir.absolute()}"
        )

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate backup filename
    backup_filename = generate_backup_filename("ledger")
    backup_path = output_dir / backup_filename

    if dry_run:
        logger.info(f"[DRY RUN] Would backup {ledger_dir} to {backup_path}")
        return None

    logger.info(f"Backing up ledger from {ledger_dir} to {backup_path}")

    try:
        # Create tar.gz archive
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(ledger_dir, arcname=ledger_dir.name)

        logger.info(f"Ledger backup completed: {backup_path}")
        return backup_path

    except PermissionError as e:
        logger.error(f"Cannot write to {output_dir}: Permission denied")
        raise PermissionError(f"Cannot write to {output_dir}: Permission denied") from e
    except Exception as e:
        logger.error(f"Failed to create ledger backup: {e}")
        raise


def backup_neo4j(output_dir: Path, dry_run: bool = False) -> Optional[Path]:
    """
    Create a Neo4j database dump using neo4j-admin.

    Args:
        output_dir: Directory to store the backup file
        dry_run: If True, don't create backup, just show what would be done

    Returns:
        Path to the created dump file, or None if dry_run or Neo4j not configured

    Raises:
        ConnectionError: If cannot connect to Neo4j
        RuntimeError: If neo4j-admin command fails
    """
    # Check if Neo4j is configured
    neo4j_uri = os.getenv("NEO4J_URI")
    if not neo4j_uri:
        logger.warning("NEO4J_URI not set, skipping Neo4j backup")
        return None

    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate backup filename
    backup_filename = generate_backup_filename("neo4j")
    backup_path = output_dir / backup_filename

    if dry_run:
        logger.info(f"[DRY RUN] Would backup Neo4j to {backup_path}")
        return None

    logger.info(f"Backing up Neo4j database to {backup_path}")

    try:
        neo4j_admin = shutil.which("neo4j-admin")
        if neo4j_admin is None:
            logger.error("neo4j-admin command not found. Is Neo4j installed?")
            raise RuntimeError("neo4j-admin command not found. Is Neo4j installed?")

        # neo4j-admin writes the archive into a directory, using the database
        # name as the filename. Never report success for an empty placeholder.
        dump_dir = output_dir / f".{backup_filename}.tmp"
        dump_dir.mkdir(parents=True, exist_ok=False)
        try:
            subprocess.run(
                [
                    neo4j_admin,
                    "database",
                    "dump",
                    os.getenv("NEO4J_DATABASE", "neo4j"),
                    f"--to-path={dump_dir}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            generated_dump = dump_dir / f"{os.getenv('NEO4J_DATABASE', 'neo4j')}.dump"
            if not generated_dump.is_file() or generated_dump.stat().st_size == 0:
                raise RuntimeError("neo4j-admin produced an empty or missing dump")
            generated_dump.replace(backup_path)
        finally:
            shutil.rmtree(dump_dir, ignore_errors=True)

        logger.info(f"Neo4j backup completed: {backup_path}")
        return backup_path

    except subprocess.CalledProcessError as e:
        logger.error(f"neo4j-admin command failed: {e}")
        raise RuntimeError(f"neo4j-admin command failed: {e}") from e
    except Exception as e:
        logger.error(f"Failed to create Neo4j backup: {e}")
        raise


def main():
    """Main entry point for backup script."""
    parser = argparse.ArgumentParser(
        description="Backup Mahoun ledger and Neo4j database"
    )
    parser.add_argument("--ledger", action="store_true", help="Backup ledger only")
    parser.add_argument("--neo4j", action="store_true", help="Backup Neo4j only")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backups"),
        help="Output directory for backups (default: backups/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be backed up without creating archives",
    )

    args = parser.parse_args()

    # Determine what to backup
    backup_ledger_flag = args.ledger
    backup_neo4j_flag = args.neo4j

    # If no flags specified, backup both
    if not backup_ledger_flag and not backup_neo4j_flag:
        backup_ledger_flag = True
        backup_neo4j_flag = True

    exit_code = 0
    created_archives = []

    try:
        # Backup ledger
        if backup_ledger_flag:
            ledger_archive = backup_ledger(args.output_dir, args.dry_run)
            if ledger_archive:
                created_archives.append(ledger_archive)
                print(f"Ledger backup: {ledger_archive.absolute()}")

        # Backup Neo4j
        if backup_neo4j_flag:
            neo4j_archive = backup_neo4j(args.output_dir, args.dry_run)
            if neo4j_archive:
                created_archives.append(neo4j_archive)
                print(f"Neo4j backup: {neo4j_archive.absolute()}")

        if args.dry_run:
            print("[DRY RUN] No archives were created")
        elif not created_archives:
            print("No backups were created")

    except FileNotFoundError as e:
        logger.error(str(e))
        exit_code = 1
    except PermissionError as e:
        logger.error(str(e))
        exit_code = 1
    except ConnectionError as e:
        logger.error(str(e))
        exit_code = 2
    except RuntimeError as e:
        logger.error(str(e))
        exit_code = 3
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()