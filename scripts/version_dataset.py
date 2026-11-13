#!/usr/bin/env python3
"""
Dataset Versioning Script for Mahoun Platform
==============================================

Version training datasets with cryptographic hashes for reproducibility.

Usage:
    python scripts/version_dataset.py DATASET_DIR [--description DESC]
    python scripts/version_dataset.py --list DATASET_NAME
    python scripts/version_dataset.py --verify DATASET_DIR VERSION
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatasetVersion(BaseModel):
    """Version metadata for a training dataset."""
    
    dataset_name: str = Field(..., description="Name of the dataset")
    version: int = Field(..., description="Auto-incremented version number")
    hash: str = Field(..., description="SHA256 hash of dataset contents")
    timestamp: str = Field(..., description="When version was created")
    description: str = Field(..., description="Human-readable version notes")
    file_count: int = Field(..., description="Number of files in dataset")


def compute_dataset_hash(dataset_dir: Path) -> str:
    """
    Compute SHA256 hash of all files in dataset directory.
    
    Args:
        dataset_dir: Path to dataset directory
        
    Returns:
        Hexadecimal SHA256 hash string
        
    Algorithm:
        1. List all files recursively, sorted by path
        2. For each file, hash (relative_path + file_content)
        3. Combine all file hashes into final hash
    """
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")
    
    # Get all files sorted by relative path
    all_files = sorted(dataset_dir.rglob("*"))
    files = [f for f in all_files if f.is_file()]
    
    if not files:
        logger.warning(f"No files found in {dataset_dir}")
    
    # Create combined hash
    combined_hasher = hashlib.sha256()
    
    for file_path in files:
        # Get relative path
        rel_path = file_path.relative_to(dataset_dir)
        
        # Hash relative path
        combined_hasher.update(str(rel_path).encode('utf-8'))
        
        # Hash file content
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                combined_hasher.update(chunk)
    
    return combined_hasher.hexdigest()


def get_next_version_number(dataset_name: str, versions_dir: Path) -> int:
    """
    Get the next version number for a dataset.
    
    Args:
        dataset_name: Name of the dataset
        versions_dir: Directory containing version metadata files
        
    Returns:
        Next version number (1 if no versions exist)
    """
    if not versions_dir.exists():
        return 1
    
    # Find all version files for this dataset
    version_files = list(versions_dir.glob(f"{dataset_name}_v*.json"))
    
    if not version_files:
        return 1
    
    # Extract version numbers
    versions = []
    for vf in version_files:
        try:
            # Parse version from filename like "dataset_v3.json"
            version_str = vf.stem.split('_v')[-1]
            versions.append(int(version_str))
        except (ValueError, IndexError):
            continue
    
    return max(versions) + 1 if versions else 1


def create_version_metadata(
    dataset_name: str,
    dataset_hash: str,
    file_count: int,
    description: str,
    version: int
) -> Dict:
    """
    Create version metadata dictionary.
    
    Args:
        dataset_name: Name of the dataset
        dataset_hash: SHA256 hash of the dataset
        file_count: Number of files in the dataset
        description: Human-readable version description
        version: Version number
        
    Returns:
        Dictionary with version metadata
    """
    metadata = DatasetVersion(
        dataset_name=dataset_name,
        version=version,
        hash=dataset_hash,
        timestamp=datetime.now().isoformat(),
        description=description,
        file_count=file_count
    )
    
    return metadata.model_dump()


def save_version_metadata(metadata: Dict, output_dir: Path) -> Path:
    """
    Save version metadata to JSON file.
    
    Args:
        metadata: Version metadata dictionary
        output_dir: Directory to store metadata file
        
    Returns:
        Path to the created metadata file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    dataset_name = metadata['dataset_name']
    version = metadata['version']
    filename = f"{dataset_name}_v{version}.json"
    output_path = output_dir / filename
    
    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Saved version metadata to {output_path}")
    return output_path


def list_versions(dataset_name: str, versions_dir: Path) -> List[Dict]:
    """
    List all versions of a dataset sorted by timestamp.
    
    Args:
        dataset_name: Name of the dataset
        versions_dir: Directory containing version metadata files
        
    Returns:
        List of version metadata dictionaries, newest first
    """
    if not versions_dir.exists():
        return []
    
    # Find all version files for this dataset
    version_files = list(versions_dir.glob(f"{dataset_name}_v*.json"))
    
    versions = []
    for vf in version_files:
        try:
            with open(vf, 'r') as f:
                metadata = json.load(f)
                versions.append(metadata)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read {vf}: {e}")
            continue
    
    # Sort by timestamp (newest first)
    versions.sort(key=lambda v: v.get('timestamp', ''), reverse=True)
    
    return versions


def verify_dataset(dataset_dir: Path, expected_hash: str) -> Tuple[bool, List[str]]:
    """
    Verify dataset matches expected hash.
    
    Args:
        dataset_dir: Path to dataset directory
        expected_hash: Expected SHA256 hash
        
    Returns:
        Tuple of (matches, changed_files)
        - matches: True if hash matches
        - changed_files: List of files that differ (empty if matches)
    """
    current_hash = compute_dataset_hash(dataset_dir)
    
    if current_hash == expected_hash:
        return (True, [])
    
    # If hashes don't match, we can't easily determine which files changed
    # without storing individual file hashes (which we don't do for simplicity)
    logger.warning("Dataset hash mismatch - dataset has been modified")
    return (False, ["Dataset contents have changed (run version command to see new hash)"])


def main():
    """Main entry point for dataset versioning script."""
    parser = argparse.ArgumentParser(
        description="Version training datasets with cryptographic hashes"
    )
    parser.add_argument(
        "dataset_path",
        nargs='?',
        type=Path,
        help="Path to dataset directory"
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Human-readable version description"
    )
    parser.add_argument(
        "--list",
        type=str,
        metavar="DATASET_NAME",
        help="List all versions of a dataset"
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="VERSION",
        help="Verify dataset matches stored version"
    )
    parser.add_argument(
        "--versions-dir",
        type=Path,
        default=Path("dataset_versions"),
        help="Directory to store version metadata (default: dataset_versions/)"
    )
    
    args = parser.parse_args()
    
    exit_code = 0
    
    try:
        # List versions mode
        if args.list:
            versions = list_versions(args.list, args.versions_dir)
            if not versions:
                print(f"No versions found for dataset: {args.list}")
            else:
                print(f"\nVersions for {args.list}:")
                print("-" * 80)
                for v in versions:
                    print(f"Version {v['version']} - {v['timestamp']}")
                    print(f"  Hash: {v['hash']}")
                    print(f"  Files: {v['file_count']}")
                    print(f"  Description: {v['description']}")
                    print()
            return
        
        # Verify mode
        if args.verify:
            if not args.dataset_path:
                print("Error: dataset_path required for --verify")
                sys.exit(1)
            
            # Load version metadata
            version_file = args.versions_dir / f"{args.dataset_path.name}_v{args.verify}.json"
            if not version_file.exists():
                print(f"Error: Version {args.verify} not found for dataset {args.dataset_path.name}")
                sys.exit(1)
            
            with open(version_file, 'r') as f:
                metadata = json.load(f)
            
            matches, changed_files = verify_dataset(args.dataset_path, metadata['hash'])
            
            if matches:
                print(f"✓ Dataset matches version {args.verify}")
                print(f"  Hash: {metadata['hash']}")
            else:
                print(f"✗ Dataset does NOT match version {args.verify}")
                print(f"  Expected hash: {metadata['hash']}")
                print(f"  Changes detected")
                exit_code = 2
            return
        
        # Version creation mode
        if not args.dataset_path:
            parser.print_help()
            sys.exit(1)
        
        dataset_dir = args.dataset_path
        dataset_name = dataset_dir.name
        
        # Compute hash
        logger.info(f"Computing hash for {dataset_dir}...")
        dataset_hash = compute_dataset_hash(dataset_dir)
        
        # Count files
        file_count = sum(1 for f in dataset_dir.rglob("*") if f.is_file())
        
        # Get next version number
        version = get_next_version_number(dataset_name, args.versions_dir)
        
        # Create metadata
        metadata = create_version_metadata(
            dataset_name=dataset_name,
            dataset_hash=dataset_hash,
            file_count=file_count,
            description=args.description,
            version=version
        )
        
        # Save metadata
        metadata_path = save_version_metadata(metadata, args.versions_dir)
        
        # Print results
        print(f"\nDataset versioned successfully!")
        print(f"  Dataset: {dataset_name}")
        print(f"  Version: {version}")
        print(f"  Hash: {dataset_hash}")
        print(f"  Files: {file_count}")
        print(f"  Metadata: {metadata_path.absolute()}")
        
    except FileNotFoundError as e:
        logger.error(str(e))
        exit_code = 1
    except PermissionError as e:
        logger.error(str(e))
        exit_code = 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        exit_code = 1
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
