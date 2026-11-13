#!/usr/bin/env python3
"""
Contract Ownership Validator
============================

Validates that each schema contract has exactly one canonical owner and that
the ownership registry matches the code.

Usage:
    python scripts/validate_contract_ownership.py
    python scripts/validate_contract_ownership.py --write-fingerprints
"""

import argparse
import ast
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_CONTRACTS_DIR = REPO_ROOT / "mahoun" / "schemas" / "contracts"
DEFAULT_REGISTRY_PATH = REPO_ROOT / "mahoun" / "contracts" / "ownership.yaml"


@dataclass(frozen=True)
class Occurrence:
    file_path: Path
    class_name: str
    fingerprint: str


def _fingerprint_classdef(node: ast.ClassDef) -> str:
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(_read_text(path), filename=str(path))


def discover_contract_occurrences(contracts_dir: Path) -> Dict[str, List[Occurrence]]:
    occurrences: Dict[str, List[Occurrence]] = {}
    for file_path in sorted(contracts_dir.glob("*.py")):
        module = _parse_module(file_path)
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not node.name.endswith("Contract"):
                continue
            fp = _fingerprint_classdef(node)
            occurrences.setdefault(node.name, []).append(
                Occurrence(file_path=file_path, class_name=node.name, fingerprint=fp)
            )
    return occurrences


def load_registry(registry_path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(_read_text(registry_path))
    if not isinstance(data, dict):
        raise ValueError("ownership registry must be a mapping")
    return data


def _expected_module_for_owner(owner_file: str) -> str:
    stem = Path(owner_file).stem
    return f"mahoun.schemas.contracts.{stem}"


def validate_registry(
    registry: Dict[str, Any],
    occurrences: Dict[str, List[Occurrence]],
    contracts_dir: Path,
) -> List[str]:
    errors: List[str] = []

    version = registry.get("version")
    if version != 1:
        errors.append(f"registry version must be 1, got {version!r}")

    contracts = registry.get("contracts")
    if not isinstance(contracts, dict):
        errors.append("registry contracts must be a mapping")
        return errors

    registry_names = set(contracts.keys())
    discovered_names = set(occurrences.keys())

    missing = sorted(discovered_names - registry_names)
    extra = sorted(registry_names - discovered_names)
    if missing:
        errors.append(f"registry missing contracts: {', '.join(missing)}")
    if extra:
        errors.append(f"registry has unknown contracts: {', '.join(extra)}")

    for name, occs in sorted(occurrences.items()):
        if len(occs) <= 1:
            continue
        locs = ", ".join(str(o.file_path.relative_to(REPO_ROOT)) for o in occs)
        unique_fps = sorted({o.fingerprint for o in occs})
        errors.append(
            f"duplicate contract definition: {name} in {locs} (fingerprints={unique_fps})"
        )

    for name, entry in sorted(contracts.items()):
        if name not in occurrences:
            continue
        if not isinstance(entry, dict):
            errors.append(f"{name}: registry entry must be a mapping")
            continue

        owner = entry.get("owner")
        module = entry.get("module")
        fingerprint = entry.get("fingerprint")

        if not owner or not isinstance(owner, str):
            errors.append(f"{name}: owner must be a non-empty string")
            continue
        if not module or not isinstance(module, str):
            errors.append(f"{name}: module must be a non-empty string")
        if not fingerprint or not isinstance(fingerprint, str) or not fingerprint.strip():
            errors.append(f"{name}: fingerprint must be a non-empty string")

        owner_path = contracts_dir / owner
        if not owner_path.exists():
            errors.append(f"{name}: owner file does not exist: {owner_path}")
            continue

        expected_module = _expected_module_for_owner(owner)
        if module and module != expected_module:
            errors.append(f"{name}: module must be {expected_module}, got {module}")

        occ = occurrences[name][0]
        if occ.file_path.name != owner:
            errors.append(
                f"{name}: canonical owner mismatch (registry={owner}, code={occ.file_path.name})"
            )

        if fingerprint and occ.fingerprint != fingerprint:
            errors.append(
                f"{name}: fingerprint mismatch (registry={fingerprint}, code={occ.fingerprint})"
            )

    return errors


def write_fingerprints(
    registry_path: Path,
    registry: Dict[str, Any],
    occurrences: Dict[str, List[Occurrence]],
) -> None:
    contracts = registry.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("registry contracts must be a mapping")

    updated: Dict[str, Any] = dict(registry)
    updated_contracts: Dict[str, Any] = {}
    for name, entry in contracts.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{name}: registry entry must be a mapping")
        if name not in occurrences:
            raise ValueError(f"{name}: not found in code")
        if len(occurrences[name]) != 1:
            raise ValueError(f"{name}: must have exactly one definition in code")
        new_entry = dict(entry)
        new_entry["fingerprint"] = occurrences[name][0].fingerprint
        updated_contracts[name] = new_entry

    updated["contracts"] = updated_contracts
    registry_path.write_text(
        yaml.safe_dump(updated, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate contract ownership registry")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--write-fingerprints", action="store_true")
    args = parser.parse_args(argv)

    registry_path = Path(args.registry).resolve()
    if not registry_path.exists():
        print(f"registry not found: {registry_path}", file=sys.stderr)
        return 2

    occurrences = discover_contract_occurrences(SCHEMAS_CONTRACTS_DIR)
    registry = load_registry(registry_path)

    if args.write_fingerprints:
        write_fingerprints(registry_path, registry, occurrences)
        print(f"updated fingerprints: {registry_path}")
        return 0

    errors = validate_registry(registry, occurrences, SCHEMAS_CONTRACTS_DIR)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("OK: contract ownership registry is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

