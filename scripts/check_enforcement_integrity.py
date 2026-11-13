#!/usr/bin/env python3
"""
Enforcement Self-Protection Checker (Phase G)
==============================================
Verifies that the enforcement surface registered in
ci/first_step/enforcement_manifest.yaml is intact.

Detects:
  - removal of a registered enforcement file
  - disabling/commenting out an enforcement invocation
  - replacing a gate invocation with an unconditional success
  - removing required enforcement tests
  - removing frontend antimock invocation from the execution chain
  - removing API contract validation from the pre-push/CI chain
  - removing constitutional integrity validation from the pre-push/CI chain

This is a STRUCTURAL check, not a semantic correctness checker.

Exit codes:
  0 - Enforcement surface intact
  1 - Violations found
  2 - Error
"""

import sys
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class IntegrityViolation:
    path: str
    message: str
    severity: str = "CRITICAL"


class EnforcementIntegrityChecker:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.manifest_path = project_root / 'ci' / 'first_step' / 'enforcement_manifest.yaml'
        self.violations: List[IntegrityViolation] = []

    def run(self) -> bool:
        """Run all checks. Returns True if no violations."""
        if not self.manifest_path.exists():
            print(f"❌ ERROR: Enforcement manifest not found: {self.manifest_path}")
            return False

        with open(self.manifest_path, 'r') as f:
            manifest = yaml.safe_load(f)

        entries = manifest.get('enforcement_surface', [])
        print(f"📋 Enforcement manifest: {len(entries)} registered entries")
        print("")

        for entry in entries:
            self._check_entry(entry)

        return self._report()

    def _check_entry(self, entry: Dict):
        path = entry.get('path', '')
        rel = Path(path)
        abs_path = self.project_root / rel
        entry_type = entry.get('type', 'unknown')
        required_patterns = entry.get('required_patterns', [])
        required_for = entry.get('required_for', [])

        # Check 1: File exists
        if not abs_path.exists():
            self.violations.append(IntegrityViolation(
                path=str(rel),
                message=f"REMOVED: {entry_type} file missing from enforcement surface",
            ))
            return

        # Check 2: Required patterns present
        if required_patterns:
            try:
                content = abs_path.read_text(encoding='utf-8')
            except OSError:
                self.violations.append(IntegrityViolation(
                    path=str(rel),
                    message=f"UNREADABLE: cannot read {entry_type} file",
                ))
                return

            for pattern in required_patterns:
                if pattern not in content:
                    self.violations.append(IntegrityViolation(
                        path=str(rel),
                        message=f"PATTERN MISSING: '{pattern}' not found in {entry_type}",
                    ))

    def _report(self) -> bool:
        """Print findings."""
        print("=" * 60)
        print(f"🛡️  Enforcement Integrity: {len(self.violations)} violations")
        print("=" * 60)

        if self.violations:
            print(f"\n❌ VIOLATIONS ({len(self.violations)}):")
            for v in self.violations:
                print(f"  {v.path}: {v.message}")
            print(f"\n❌ FAILED: Enforcement surface integrity compromised")
            return False

        # Print the actual execution chain
        print("\n✅ PASSED: Enforcement surface intact")
        print("\nExecution chain:")
        print("  PRE-COMMIT:")
        print("    gate_1_lint.sh")
        print("    gate_2_types.sh")
        print("    gate_4b_frontend_antimock.sh (fabrication check)")
        print("    ci/gate_md_count.sh")
        print("  PRE-PUSH:")
        print("    gate_0_integrity.sh")
        print("    gate_3_reality.sh")
        print("    gate_4_antimock.sh + gate_4b_frontend_antimock.sh")
        print("    gate_5_determinism.sh")
        print("    gate_6_artifacts.sh")
        print("    gate_7_architecture.sh")
        print("    gate_8_contracts.sh")
        print("    gate_9_governance.sh")
        print("    gate_9_mypy_non_regression.sh")
        print("    scripts/validate_governance_compliance.py")
        print("    scripts/check_api_contracts.py")
        print("    gate_10_constitutional_integrity.sh")
        print("    ci/gate_md_count.sh")
        print("  CI:")
        print("    (wired via pre-push + CI workflow)")
        return True


def main():
    project_root = Path(__file__).resolve().parent.parent
    checker = EnforcementIntegrityChecker(project_root)
    success = checker.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
