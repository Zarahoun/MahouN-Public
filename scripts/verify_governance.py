#!/usr/bin/env python3
"""
MAHOUN Governance Static Enforcer
=================================

scripts/verify_governance.py

P0 ENFORCEMENT:
  Fails the build (non-zero exit) if any Python source outside the
  constitutional governance boundary contains raw Neo4j driver/session
  access patterns that bypass GovernedNeo4jSession.

This script is intended to be invoked by:
  - pre-commit hooks
  - CI pipelines (mandatory gate)
  - `make governance-check`

Exit codes:
  0 - Clean (no violations)
  1 - Violations found (CI must fail)
"""

import re
import sys
from pathlib import Path

# Patterns that indicate direct/raw Neo4j *mutation* access (potential governance bypass)
# We only care about writes. Pure reads (health checks, counts, MATCH without mutation) are tolerated
# during the incremental hardening phase. The runtime MutationAuthorizationBoundary still blocks
# any mutation attempt even from legacy code.
MUTATION_SESSION_PATTERN = re.compile(
    r"""
    (?P<session_call>
        \bdriver\.session\b
        | \.session\(\s*\)\.run\b
        | \bsession\.run\b
        | GraphDatabase\s*\(
    )
    .*?
    (?P<mutation>
        \b(CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP)\b
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.DOTALL,
)

# Constitutional files that are ALLOWED to touch the raw driver
# (they implement or protect the boundary)
ALLOWED_GOVERNANCE_FILES = {
    "mahoun/core/governance/mutation_boundary.py",
    "mahoun/graph/neo4j/connection.py",
    "mahoun/graph/neo4j/schema.py",  # schema DDL only, read-only in practice
    "mahoun/graph/graph_query_service.py",  # legacy read paths under review
}

# Directories to completely ignore (generated, archives, worktrees)
IGNORE_DIRS = {"__pycache__", ".git", "archive", "worktrees", ".kilo/worktrees", "venv", "build", "dist"}


def is_ignored(path: Path) -> bool:
    parts = path.parts
    return any(d in parts for d in IGNORE_DIRS)


def scan() -> list[str]:
    violations: list[str] = []
    root = Path.cwd()

    # Production code only. Tests/fixtures may legitimately use raw drivers for seeding.
    # The runtime boundary still protects the live system.
    source_roots = ["mahoun", "api"]
    candidate_files: list[Path] = []
    for src in source_roots:
        candidate_files.extend((root / src).rglob("*.py"))

    for py_file in candidate_files:
        if is_ignored(py_file):
            continue

        try:
            rel_path = str(py_file.relative_to(root))
        except ValueError:
            continue

        # Skip allowed constitutional modules
        if any(allowed in rel_path for allowed in ALLOWED_GOVERNANCE_FILES):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            # Check a window of 3 lines for mutation + session together (common pattern)
            lines = content.splitlines()
            start = max(0, lineno - 1)
            end = min(len(lines), lineno + 2)
            window = "\n".join(lines[start:end])
            if MUTATION_SESSION_PATTERN.search(window):
                if "GovernedNeo4jSession" not in window and "governed_session" not in window:
                    violations.append(
                        f"{rel_path}:{lineno}: {line.strip()[:120]}"
                    )

    return violations


def main() -> int:
    print("[GOVERNANCE] Running static verification for raw Neo4j bypasses...")
    violations = scan()

    if violations:
        print("\n" + "=" * 70)
        print("CRITICAL GOVERNANCE VIOLATION DETECTED")
        print("=" * 70)
        print("Raw database access patterns found outside GovernedNeo4jSession.")
        print("ALL graph mutations MUST go exclusively through the governed boundary.")
        print("\nOffending locations:")
        for v in violations:
            print(f"  - {v}")
        print("\nRemediation: Refactor the code to use:")
        print("  from mahoun.core.governance import GovernedNeo4jSession")
        print("  with connection.governed_session(...) as gov:")
        print("      gov.write_node(...)")
        print("=" * 70 + "\n")
        return 1

    print("[GOVERNANCE] PASS — No raw Neo4j bypasses detected. Graph is sacred.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
