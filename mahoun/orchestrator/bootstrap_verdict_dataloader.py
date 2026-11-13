"""
Bootstrap Verdict DataLoader - CLI Orchestrator
================================================
Batch-process raw verdict text files into structured JSON.

This orchestrator:
  1. Scans a directory for .txt verdict files
  2. Parses each file using minimal_verdict_parser
  3. Saves structured .parsed.json outputs
  4. Optionally pushes to VectorStore and/or Graph backend

Usage:
    python -m mahoun.orchestrator.bootstrap_verdict_dataloader \
      --input-dir /path/to/raw_verdicts \
      [--output-dir /path/to/parsed_json] \
      [--overwrite] \
      [--limit N] \
      [--with-vectorstore] \
      [--with-graph]

Example:
    # Parse all files in a directory
    python -m mahoun.orchestrator.bootstrap_verdict_dataloader \
      --input-dir $MAHOUN_DATA_DIR/raw_verdicts
    
    # Parse first 5 files with VectorStore indexing
    python -m mahoun.orchestrator.bootstrap_verdict_dataloader \
      --input-dir $MAHOUN_DATA_DIR/raw_verdicts \
      --limit 5 \
      --with-vectorstore

Constraints:
  - NO LLM calls (pure rule-based parsing)
  - Graceful degradation if VectorStore/Graph not available
  - Patch-only: does not modify existing orchestrator flows
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import the verdict parser
from mahoun.pipelines.ingestion.minimal_verdict_parser import (
    parse_verdict_file,
    validate_verdict_struct,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Optional: tqdm for progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    tqdm = None


# ============================================================================
# VectorStore Hook (Optional, Graceful)
# ============================================================================

def index_in_vectorstore(verdict_struct: Dict[str, Any], source_id: str) -> bool:
    """
    Optional: Index the parsed verdict in VectorStore.
    
    Args:
        verdict_struct: Parsed verdict dictionary
        source_id: Unique identifier (e.g., filename stem)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from mahoun.pipelines.vector_store.manager import index_verdict_struct
        index_verdict_struct(verdict_struct, source_id=source_id)
        logger.info(f"VectorStore: Indexed {source_id}")
        return True
    except ImportError:
        logger.warning("VectorStore module not available - skipping vector indexing")
        return False
    except AttributeError as e:
        logger.warning(f"VectorStore method not found: {e}")
        return False
    except Exception as e:
        logger.error(f"VectorStore indexing failed for {source_id}: {e}")
        return False


# ============================================================================
# Graph Hook (Optional, Graceful)
# ============================================================================

def push_to_graph(verdict_struct: Dict[str, Any]) -> bool:
    """
    Reject the legacy graph hook.

    Parsed verdicts must be submitted through the authenticated server
    ingestion route and ``GovernedIngestionRuntime``. This hook remains only
    to fail closed for stale callers.
    """
    raise RuntimeError(
        "Legacy graph ingestion hook is blocked; use the canonical server "
        "ingestion route."
    )


# ============================================================================
# File Processing Helpers
# ============================================================================

def iter_input_files(input_dir: Path) -> List[Path]:
    """
    Iterate over all .txt files in input directory.
    
    Args:
        input_dir: Path to directory containing verdict files
    
    Returns:
        List of .txt file paths (sorted by name)
    """
    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        return []
    
    if not input_dir.is_dir():
        logger.error(f"Input path is not a directory: {input_dir}")
        return []
    
    txt_files = sorted(input_dir.glob("*.txt"))
    return txt_files


def ensure_dir(path: Path) -> Path:
    """
    Ensure directory exists, create if needed.
    
    Args:
        path: Directory path
    
    Returns:
        The path (for chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_output_path(output_dir: Path, input_file: Path) -> Path:
    """
    Build output path for a given input file.
    
    Example:
        input: /path/to/raaye_01.txt
        output: /output/raaye_01.parsed.json
    
    Args:
        output_dir: Output directory
        input_file: Input file path
    
    Returns:
        Output file path (.parsed.json)
    """
    stem = input_file.stem  # raaye_01
    output_filename = f"{stem}.parsed.json"
    return output_dir / output_filename


def process_single_file(
    input_file: Path,
    output_file: Path,
    overwrite: bool,
    with_vectorstore: bool,
    with_graph: bool,
) -> Tuple[bool, Optional[str]]:
    """
    Process a single verdict file.
    
    Args:
        input_file: Path to input .txt file
        output_file: Path to output .parsed.json file
        overwrite: Whether to overwrite existing output
        with_vectorstore: Whether to push to VectorStore
        with_graph: Whether to push to Graph
    
    Returns:
        (success: bool, error_message: Optional[str])
    """
    # Check if output already exists
    if output_file.exists() and not overwrite:
        logger.debug(f"Skipping {input_file.name} (already exists)")
        return True, "skipped"
    
    try:
        # Parse verdict file
        verdict_struct = parse_verdict_file(input_file)
        
        # Validate structure
        is_valid, errors = validate_verdict_struct(verdict_struct)
        if not is_valid:
            error_msg = f"Validation failed: {'; '.join(errors)}"
            logger.error(f"{input_file.name}: {error_msg}")
            return False, error_msg
        
        # Write JSON output
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(verdict_struct, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Parsed {input_file.name} → {output_file.name}")
        
        # Optional: VectorStore indexing
        if with_vectorstore:
            source_id = input_file.stem
            index_in_vectorstore(verdict_struct, source_id)
        
        # Optional: Graph ingestion
        if with_graph:
            push_to_graph(verdict_struct)
        
        return True, None
    
    except FileNotFoundError as e:
        error_msg = f"File not found: {e}"
        logger.error(f"{input_file.name}: {error_msg}")
        return False, error_msg
    
    except UnicodeDecodeError as e:
        error_msg = f"Encoding error (expected UTF-8): {e}"
        logger.error(f"{input_file.name}: {error_msg}")
        return False, error_msg
    
    except json.JSONDecodeError as e:
        error_msg = f"JSON serialization error: {e}"
        logger.error(f"{input_file.name}: {error_msg}")
        return False, error_msg
    
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {e}"
        logger.error(f"{input_file.name}: {error_msg}")
        return False, error_msg


# ============================================================================
# Main Orchestrator
# ============================================================================

def run_bootstrap_dataloader(
    input_dir: str,
    output_dir: Optional[str] = None,
    overwrite: bool = False,
    limit: Optional[int] = None,
    with_vectorstore: bool = False,
    with_graph: bool = False,
) -> None:
    """
    Run the bootstrap verdict data loader.
    
    Args:
        input_dir: Directory containing .txt verdict files
        output_dir: Directory for .parsed.json outputs (or None for auto)
        overwrite: Whether to overwrite existing outputs
        limit: Maximum number of files to process (or None for all)
        with_vectorstore: Whether to push to VectorStore
        with_graph: Whether to push to Graph backend
    """
    start_time = time.time()
    
    # Convert to Path objects
    input_path = Path(input_dir).resolve()
    
    # Determine output directory
    if output_dir:
        output_path = Path(output_dir).resolve()
    else:
        # Create sibling directory: <input-dir-name>_parsed
        output_path = input_path.parent / f"{input_path.name}_parsed"
    
    # Ensure output directory exists
    ensure_dir(output_path)
    
    # Print configuration
    print("=" * 70)
    print("📡 MAHOUN Bootstrap Verdict DataLoader")
    print("=" * 70)
    print(f"Input directory:  {input_path}")
    print(f"Output directory: {output_path}")
    print(f"Overwrite:        {overwrite}")
    print(f"Limit:            {limit if limit else 'None (all files)'}")
    print(f"VectorStore:      {'ENABLED' if with_vectorstore else 'DISABLED'}")
    print(f"Graph:            {'ENABLED' if with_graph else 'DISABLED'}")
    print("=" * 70)
    print()
    
    # Get list of input files
    input_files = iter_input_files(input_path)
    
    if not input_files:
        logger.error("No .txt files found in input directory")
        return
    
    logger.info(f"Found {len(input_files)} .txt file(s)")
    
    # Apply limit if specified
    if limit:
        input_files = input_files[:limit]
        logger.info(f"Processing first {len(input_files)} file(s) (--limit {limit})")
    
    print()
    
    # Process each file
    results = {
        "total": len(input_files),
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }
    
    # Use tqdm if available, otherwise simple iteration
    if HAS_TQDM:
        iterator = tqdm(input_files, desc="Processing verdicts", unit="file")
    else:
        iterator = input_files
    
    for input_file in iterator:
        output_file = build_output_path(output_path, input_file)
        
        success, error = process_single_file(
            input_file,
            output_file,
            overwrite,
            with_vectorstore,
            with_graph,
        )
        
        if error == "skipped":
            results["skipped"] += 1
        elif success:
            results["success"] += 1
        else:
            results["failed"] += 1
            results["errors"].append({
                "file": input_file.name,
                "error": error,
            })
    
    # Print summary
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Total files:      {results['total']}")
    print(f"✓ Successful:     {results['success']}")
    print(f"❌ Failed:         {results['failed']}")
    print(f"⊘ Skipped:        {results['skipped']}")
    print(f"⏱ Elapsed time:   {elapsed_time:.2f}s")
    if results['success'] > 0:
        print(f"⚡ Avg time/file:  {elapsed_time/results['success']:.2f}s")
    print("=" * 70)
    
    # Print errors if any
    if results["errors"]:
        print()
        print("❌ ERRORS:")
        for error_info in results["errors"]:
            print(f"  - {error_info['file']}: {error_info['error']}")
    
    print()
    print(f"✓ Output written to: {output_path}")
    print()


# ============================================================================
# CLI Argument Parser
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    """
    Build CLI argument parser.
    
    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="Bootstrap Verdict DataLoader - Batch parse verdict files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Parse all files in a directory
  python -m mahoun.orchestrator.bootstrap_verdict_dataloader \\
    --input-dir $MAHOUN_DATA_DIR/raw_verdicts

  # Parse first 5 files with overwrite
  python -m mahoun.orchestrator.bootstrap_verdict_dataloader \\
    --input-dir /path/to/verdicts \\
    --limit 5 \\
    --overwrite

  # Parse with VectorStore and Graph integration
  python -m mahoun.orchestrator.bootstrap_verdict_dataloader \\
    --input-dir /path/to/verdicts \\
    --with-vectorstore \\
    --with-graph
        """
    )
    
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory containing .txt verdict files (required)",
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for .parsed.json outputs (default: <input-dir>_parsed)",
    )
    
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .parsed.json files",
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of files to process (for testing)",
    )
    
    parser.add_argument(
        "--with-vectorstore",
        action="store_true",
        help="Push parsed verdicts to VectorStore (requires pipelines.vector_store.manager)",
    )
    
    parser.add_argument(
        "--with-graph",
        action="store_true",
        help="Push parsed verdicts to Graph backend (requires graph.neo4j.operations)",
    )
    
    return parser


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    
    run_bootstrap_dataloader(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        limit=args.limit,
        with_vectorstore=args.with_vectorstore,
        with_graph=args.with_graph,
    )


if __name__ == "__main__":
    main()
