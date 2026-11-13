#!/usr/bin/env python3
"""
Weak Module Analyzer
====================

Purpose: Identify production modules with minimal test coverage using AST-based import analysis

This script:
1. Scans all test files and extracts production module imports using AST
2. Classifies modules into: untested, weak, moderate, strong
3. Calculates priority scores for test development roadmap
4. Generates actionable recommendations

Requirements: R4 (Test Strengthening Roadmap)
Task: 2.2 Weak module analysis script
"""

import ast
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Set


@dataclass
class ModuleImportAnalysis:
    """Import analysis for a production module"""

    module_name: str
    source_file_count: int
    source_line_count: int
    test_import_count: int
    test_files_importing: list[str]
    classification: str  # "strong", "moderate", "weak", "untested"
    priority_score: float  # Based on criticality × (1 - coverage)


@dataclass
class WeakModuleReport:
    """Complete weak module analysis report"""

    analysis_date: str
    modules_analyzed: int
    classifications: dict[str, list[str]]  # tier -> [modules]
    priority_queue: list[ModuleImportAnalysis]
    corrections: dict[str, str]  # module -> correction note

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


class WeakModuleAnalyzer:
    """AST-based analyzer for test-to-module mapping"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.mahoun_dir = repo_root / "mahoun"
        self.tests_dir = repo_root / "tests"

    def scan_test_imports(self) -> dict[str, Set[str]]:
        """
        Scan all test files and extract production module imports using AST.

        Returns:
            Map of module_name -> set of test files importing it
        """
        imports: dict[str, Set[str]] = defaultdict(set)

        for test_file in self.tests_dir.rglob("test_*.py"):
            try:
                tree = ast.parse(test_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("mahoun."):
                            # Extract top-level module (e.g., mahoun.core -> core)
                            parts = node.module.split(".")
                            if len(parts) >= 2:
                                module = parts[1]
                                imports[module].add(str(test_file.relative_to(self.repo_root)))
            except Exception as e:
                print(f"Warning: Could not parse {test_file}: {e}", file=sys.stderr)

        return {k: v for k, v in imports.items()}

    def count_source_files(self, module_name: str) -> int:
        """Count Python source files in a module"""
        module_dir = self.mahoun_dir / module_name
        if not module_dir.exists() or not module_dir.is_dir():
            return 0

        return sum(1 for _ in module_dir.rglob("*.py"))

    def count_source_lines(self, module_name: str) -> int:
        """Count lines of code in a module"""
        module_dir = self.mahoun_dir / module_name
        if not module_dir.exists() or not module_dir.is_dir():
            return 0

        total_lines = 0
        for py_file in module_dir.rglob("*.py"):
            try:
                total_lines += len(py_file.read_text(encoding="utf-8").splitlines())
            except Exception:
                pass

        return total_lines

    def classify_module(self, import_count: int) -> str:
        """Classify module based on test import count"""
        if import_count == 0:
            return "untested"
        elif import_count <= 3:
            return "weak"
        elif import_count <= 15:
            return "moderate"
        else:
            return "strong"

    def calculate_priority(
        self,
        module: str,
        import_count: int,
        line_count: int,
    ) -> float:
        """
        Calculate test development priority score.

        Priority = criticality_weight × complexity_weight × (1 - coverage_proxy)
        """
        criticality = {
            "core": 1.0,
            "reasoning": 0.95,
            "security": 0.9,
            "ledger": 0.85,
            "graph": 0.8,
            "orchestrator": 0.75,
            "nlp": 0.7,
            "agents": 0.65,
            "domain": 0.65,
            "tracing": 0.5,
            "execution": 0.6,
            "concurrency": 0.6,
            "mcp": 0.5,
        }.get(module, 0.5)

        complexity = min(1.0, line_count / 5000)
        coverage_proxy = min(1.0, import_count / 50)

        return round(criticality * complexity * (1 - coverage_proxy), 3)

    def analyze(self) -> WeakModuleReport:
        """
        Perform complete weak module analysis.

        Returns:
            WeakModuleReport with classifications and priorities
        """
        print("Scanning test imports...")
        imports_map = self.scan_test_imports()

        print("Analyzing modules...")
        analyses: list[ModuleImportAnalysis] = []

        # Get all module directories
        module_dirs = [d for d in self.mahoun_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]

        for module_dir in sorted(module_dirs):
            module_name = module_dir.name
            import_count = len(imports_map.get(module_name, set()))
            test_files = sorted(imports_map.get(module_name, set()))

            source_file_count = self.count_source_files(module_name)
            source_line_count = self.count_source_lines(module_name)

            if source_file_count == 0:
                # Skip empty or non-code directories
                continue

            classification = self.classify_module(import_count)
            priority_score = self.calculate_priority(module_name, import_count, source_line_count)

            analyses.append(
                ModuleImportAnalysis(
                    module_name=module_name,
                    source_file_count=source_file_count,
                    source_line_count=source_line_count,
                    test_import_count=import_count,
                    test_files_importing=test_files,
                    classification=classification,
                    priority_score=priority_score,
                )
            )

        # Classify modules
        classifications: dict[str, list[str]] = {
            "untested": [],
            "weak": [],
            "moderate": [],
            "strong": [],
        }

        for analysis in analyses:
            classifications[analysis.classification].append(analysis.module_name)

        # Corrections for misclassifications
        corrections = {}
        for analysis in analyses:
            if analysis.module_name in ["agents", "domain"] and analysis.classification == "strong":
                corrections[analysis.module_name] = (
                    f"Reclassified from 'unknown' to 'strong' ({analysis.test_import_count} imports)"
                )

        # Sort by priority score (highest first)
        priority_queue = sorted(analyses, key=lambda x: x.priority_score, reverse=True)

        report = WeakModuleReport(
            analysis_date=datetime.now(UTC).isoformat(),
            modules_analyzed=len(analyses),
            classifications=classifications,
            priority_queue=priority_queue,
            corrections=corrections,
        )

        return report

    def print_report(self, report: WeakModuleReport):
        """Print human-readable report"""
        print("\n" + "=" * 80)
        print("WEAK MODULE ANALYSIS REPORT")
        print("=" * 80)
        print(f"Analysis Date:     {report.analysis_date}")
        print(f"Modules Analyzed:  {report.modules_analyzed}")
        print()

        print("CLASSIFICATION SUMMARY:")
        print("-" * 80)
        for classification, modules in report.classifications.items():
            print(f"{classification.upper():<12} ({len(modules):>2}): {', '.join(sorted(modules))}")
        print()

        print("PRIORITY RECOMMENDATIONS (Top 15):")
        print("-" * 80)
        print(
            f"{'Module':<20} {'Lines':>8} {'Imports':>8} {'Priority':>10} {'Classification':<12}"
        )
        print("-" * 80)

        for analysis in report.priority_queue[:15]:
            print(
                f"{analysis.module_name:<20} "
                f"{analysis.source_line_count:>8} "
                f"{analysis.test_import_count:>8} "
                f"{analysis.priority_score:>10.3f} "
                f"{analysis.classification:<12}"
            )

        print("-" * 80)
        print()

        if report.corrections:
            print("CORRECTIONS:")
            print("-" * 80)
            for module, note in report.corrections.items():
                print(f"  {module}: {note}")
            print()

        print("ACTIONABLE RECOMMENDATIONS:")
        print("-" * 80)

        # Focus on high-priority weak/untested modules
        weak_untested = [
            a
            for a in report.priority_queue
            if a.classification in ["weak", "untested"] and a.priority_score > 0.3
        ]

        if weak_untested:
            for analysis in weak_untested[:10]:
                print(f"  1. {analysis.module_name}")
                print(f"     - Lines: {analysis.source_line_count}, Imports: {analysis.test_import_count}")
                print(f"     - Priority: {analysis.priority_score:.3f}")
                print(f"     - Status: {analysis.classification}")
                print()
        else:
            print("  No critical weak modules detected!")

        print("=" * 80)


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze weak modules with minimal test coverage")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("weak_modules_report.json"),
        help="Output path for JSON report (default: weak_modules_report.json)",
    )

    args = parser.parse_args()

    try:
        analyzer = WeakModuleAnalyzer(repo_root=args.repo_root)
        report = analyzer.analyze()

        # Save JSON report
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report.to_json())

        print(f"✅ JSON report saved to {args.output}")

        # Print human-readable report
        analyzer.print_report(report)

        print(f"\n✅ Weak module analysis complete!")
        print(f"   Report: {args.output}")
        print(f"   Modules: {report.modules_analyzed}")
        print(f"   Untested: {len(report.classifications['untested'])}")
        print(f"   Weak: {len(report.classifications['weak'])}")

        return 0

    except Exception as e:
        print(f"❌ Error analyzing weak modules: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
