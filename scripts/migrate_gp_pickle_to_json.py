#!/usr/bin/env python3
"""
Migrate Gaussian Process V2 models from legacy pickle to secure JSON+NPZ format.

SECURITY: This offline migration tool handles pickle ONLY for migration purposes.
          Runtime code MUST NOT import pickle in production.

Usage:
    python scripts/migrate_gp_pickle_to_json.py <input.pkl> <output.json>

The script will create:
    - output.json (metadata, config, scalars)
    - output.npz (numpy arrays: X_train, y_train, inducing_points)
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np


def migrate_gp_v2_pickle_to_json(pickle_path: Path, json_path: Path) -> None:
    """
    Migrate a GaussianProcessUncertainty (formerly V2) pickle file to JSON+NPZ.

    Args:
        pickle_path: Path to legacy .pkl file
        json_path: Path to output .json file (will also create .npz)

    Raises:
        ValueError: If pickle file is invalid or corrupted
    """
    if not pickle_path.exists():
        raise FileNotFoundError(f"Pickle file not found: {pickle_path}")

    print(f"[1/3] Loading legacy pickle: {pickle_path}")
    with open(pickle_path, "rb") as f:
        state = pickle.load(f)

    # Extract metadata
    metadata = {
        "config": state.get("config"),
        "calibration_temperature": float(state.get("calibration_temperature", 1.0)),
        "calibration_metrics": state.get("calibration_metrics", {}),
        "using_svgp": bool(state.get("using_svgp", False)),
        "backend": str(state.get("backend", "sklearn")),
        "is_fitted": True,
    }

    # Extract numpy arrays
    arrays = {
        "X_train": np.array(state.get("X_train", [])),
        "y_train": np.array(state.get("y_train", [])),
        "inducing_points": np.array(state.get("inducing_points", [])),
    }

    print(f"[2/3] Writing JSON metadata: {json_path}")
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    npz_path = json_path.with_suffix(".npz")
    print(f"[3/3] Writing NPZ arrays: {npz_path}")
    np.savez_compressed(npz_path, **arrays)

    print(f"✅ Migration complete!")
    print(f"   - Metadata: {json_path} ({json_path.stat().st_size} bytes)")
    print(f"   - Arrays:   {npz_path} ({npz_path.stat().st_size} bytes)")
    print(f"   - Original: {pickle_path} ({pickle_path.stat().st_size} bytes)")
    print(f"\n⚠️  You can now delete the legacy pickle file:")
    print(f"   rm {pickle_path}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", type=Path, help="Input .pkl file (legacy pickle)")
    parser.add_argument("output", type=Path, help="Output .json file (secure JSON+NPZ)")

    args = parser.parse_args()

    try:
        migrate_gp_v2_pickle_to_json(args.input, args.output)
        return 0
    except Exception as e:
        print(f"❌ Migration failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
