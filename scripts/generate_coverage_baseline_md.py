#!/usr/bin/env python3
"""
Generate TEST_COVERAGE_BASELINE.md from measured pytest-cov output.

No estimates — only values parsed from coverage.json.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def pct(covered: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((covered / total) * 100, 2)


def main() -> int:
    coverage_path = Path("coverage.json")
    output_path = Path("TEST_COVERAGE_BASELINE.md")
    collect_path = Path("artifacts/collect_baseline.txt")

    if not coverage_path.exists():
        print(f"Missing {coverage_path}. Run pytest with --cov-report=json first.", file=sys.stderr)
        return 1

    data = json.loads(coverage_path.read_text(encoding="utf-8"))
    totals = data.get("totals", {})
    overall = pct(totals.get("covered_lines", 0), totals.get("num_statements", 0))

    packages: dict[str, dict[str, int]] = {}
    files: list[tuple[str, float, int, int]] = []

    for file_path, file_data in data.get("files", {}).items():
        if not (file_path.startswith("mahoun/") or file_path.startswith("api/")):
            continue
        summary = file_data.get("summary", {})
        statements = summary.get("num_statements", 0)
        missed = summary.get("missing_lines", 0)
        if isinstance(missed, list):
            missed = len(missed)
        covered = statements - missed
        file_cov = pct(covered, statements)
        files.append((file_path, file_cov, statements, missed))

        parts = file_path.split("/")
        pkg = parts[0] if len(parts) == 1 else f"{parts[0]}/{parts[1]}"
        if pkg not in packages:
            packages[pkg] = {"statements": 0, "missed": 0}
        packages[pkg]["statements"] += statements
        packages[pkg]["missed"] += missed

    test_count = "unknown"
    if collect_path.exists():
        import re

        match = re.search(r"collected (\d+) items?", collect_path.read_text(encoding="utf-8"))
        if match:
            test_count = match.group(1)

    files.sort(key=lambda x: x[1])
    pkg_rows = sorted(
        ((name, pct(v["statements"] - v["missed"], v["statements"]), v["statements"], v["missed"]) for name, v in packages.items()),
        key=lambda x: x[1],
    )

    critical_modules = ["governance", "ledger", "reasoning", "fortress"]
    module_cov: dict[str, float] = {}
    for mod in critical_modules:
        stats = packages.get(f"mahoun/{mod}")
        if stats:
            module_cov[mod] = pct(stats["statements"] - stats["missed"], stats["statements"])

    lines = [
        "# TEST Coverage Baseline",
        "",
        f"**Measurement date:** {datetime.now(UTC).isoformat()}",
        f"**Collected tests:** {test_count}",
        f"**Overall coverage:** {overall}%",
        "",
        "## Package Coverage",
        "",
        "| Package | Statements | Missed | Coverage |",
        "|---------|------------|--------|----------|",
    ]
    for name, cov, stmts, missed in pkg_rows:
        lines.append(f"| `{name}` | {stmts} | {missed} | {cov}% |")

    lines.extend(
        [
            "",
            "## Critical Module Thresholds (measured)",
            "",
            "| Module | Measured | Gate Threshold |",
            "|--------|----------|----------------|",
        ]
    )
    thresholds = {"governance": 80, "ledger": 75, "reasoning": 70, "fortress": 80}
    for mod, threshold in thresholds.items():
        measured = module_cov.get(mod)
        measured_str = f"{measured}%" if measured is not None else "N/A (no files)"
        lines.append(f"| `{mod}` | {measured_str} | {threshold}% |")

    lines.extend(["", "## Lowest Coverage Files (bottom 25)", "", "| File | Coverage | Statements | Missed |", "|------|----------|------------|--------|"])
    for file_path, file_cov, stmts, missed in files[:25]:
        lines.append(f"| `{file_path}` | {file_cov}% | {stmts} | {missed} |")

    lines.extend(["", "## Uncovered Critical Paths", ""])
    low_critical = [
        (fp, c, s, m)
        for fp, c, s, m in files
        if c < 50.0 and any(f"/{mod}/" in fp for mod in critical_modules)
    ]
    if low_critical:
        for file_path, file_cov, stmts, missed in low_critical[:20]:
            lines.append(f"- `{file_path}` — {file_cov}% ({missed}/{stmts} lines missed)")
    else:
        lines.append("- None below 50% in critical modules")

    lines.extend(
        [
            "",
            "## Measurement Command",
            "",
            "```bash",
            "pytest tests/ --cov=mahoun --cov=api --cov-report=term-missing --cov-report=html --cov-report=json",
            "```",
            "",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
