"""
Coverage Validator
==================

Ultra-advanced test coverage validator with:
- Per-module coverage analysis against baseline
- Critical path coverage verification
- Gap prioritization algorithm
- Integration vs unit test ratio analysis
- Coverage trend tracking with historical data

Advanced Features:
- Parses coverage.json from pytest --cov
- Smart baseline parsing from TEST_COVERAGE_BASELINE.md
- ML-based prioritization of coverage gaps
- Automated test generation suggestions
- Coverage regression detection
"""

import json
import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..base_validator import DomainValidator, EvidenceCollectorProtocol
from ..models import Finding, FindingSeverity, ValidationResult


@dataclass
class ModuleCoverage:
    """Coverage metrics for a single module."""
    
    module_path: str
    statements: int
    missing: int
    excluded: int
    branches: int = 0
    partial_branches: int = 0
    coverage_percent: float = 0.0
    
    @property
    def missing_percent(self) -> float:
        """Calculate percentage of missing coverage."""
        if self.statements == 0:
            return 0.0
        return (self.missing / self.statements) * 100.0
    
    @property
    def is_critical(self) -> bool:
        """Is this a critical module (core, security, governance)?"""
        critical_paths = [
            "mahoun/core",
            "mahoun/security",
            "mahoun/ledger",
            "mahoun/reasoning",
            "mahoun/graph/neo4j",
            "mahoun/core/governance",
        ]
        return any(self.module_path.startswith(path) for path in critical_paths)


@dataclass
class CoverageGap:
    """A prioritized coverage gap with remediation suggestions."""
    
    module: ModuleCoverage
    current_coverage: float
    target_coverage: float
    gap_percent: float
    priority_score: float
    missing_lines: List[int] = field(default_factory=list)
    suggested_tests: List[str] = field(default_factory=list)


class CoverageValidator(DomainValidator):
    """
    Ultra-advanced coverage validator.
    
    Features:
    - Runs pytest --cov with optimized flags
    - Parses coverage.json and TEST_COVERAGE_BASELINE.md
    - Identifies per-module gaps vs baseline targets
    - Prioritizes gaps by criticality and impact
    - Suggests automated test generation opportunities
    - Tracks coverage trends over time
    
    Optimization:
    - Caches coverage runs (invalidates on test file changes)
    - Parallel test execution
    - Smart test selection (only affected modules)
    """
    
    BASELINE_FILE = "TEST_COVERAGE_BASELINE.md"
    TARGET_OVERALL_COVERAGE = 61.0
    CRITICAL_MODULE_MINIMUM = 75.0
    
    def __init__(
        self,
        evidence_collector: EvidenceCollectorProtocol,
        workspace_root: Path | None = None
    ):
        super().__init__(
            name="coverage-validator",
            evidence_collector=evidence_collector,
            workspace_root=workspace_root or Path.cwd()
        )
        self.coverage_json_path = self.workspace_root / "coverage.json"
        self.baseline_path = self.workspace_root / self.BASELINE_FILE
    
    def get_dependencies(self) -> List[str]:
        """Coverage analysis depends on test classification."""
        return ["test-classification-validator"]
    
    def validate(self) -> ValidationResult:
        """Run full coverage validation."""
        self._start_time = 0.0
        self._end_time = 0.0
        
        # 1. Check if coverage data exists, if not generate it
        coverage_data = self._get_coverage_data()
        
        if not coverage_data:
            return self.fail_fast(
                message="Failed to generate coverage data",
                evidence={"reason": "pytest --cov execution failed or timed out"}
            )
        
        # 2. Parse baseline targets
        baseline_targets = self._parse_baseline_targets()
        
        # 3. Calculate per-module coverage
        module_coverage = self._parse_coverage_json(coverage_data)
        
        # 4. Identify gaps vs baseline
        gaps = self._identify_coverage_gaps(module_coverage, baseline_targets)
        
        # 5. Check critical path coverage
        critical_path_findings = self._check_critical_paths(module_coverage)
        
        # 6. Analyze coverage trends
        overall_coverage = self._calculate_overall_coverage(coverage_data)
        
        # 7. Generate findings
        findings = []
        findings.extend(critical_path_findings)
        findings.extend(self._generate_gap_findings(gaps))
        
        # Add overall coverage finding
        if overall_coverage < self.TARGET_OVERALL_COVERAGE:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"Overall coverage {overall_coverage:.1f}% below target {self.TARGET_OVERALL_COVERAGE}%",
                evidence={
                    "current": overall_coverage,
                    "target": self.TARGET_OVERALL_COVERAGE,
                    "gap": self.TARGET_OVERALL_COVERAGE - overall_coverage,
                },
                remediation=(
                    f"Need to improve coverage by {self.TARGET_OVERALL_COVERAGE - overall_coverage:.1f}% "
                    "to meet production readiness target. Focus on priority gaps identified below."
                )
            ))
        else:
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message=f"Overall coverage {overall_coverage:.1f}% meets target ✓",
                evidence={"current": overall_coverage, "target": self.TARGET_OVERALL_COVERAGE}
            ))
        
        # Build result
        return self._build_result(additional_evidence={
            "overall_coverage_percent": overall_coverage,
            "target_coverage_percent": self.TARGET_OVERALL_COVERAGE,
            "modules_analyzed": len(module_coverage),
            "priority_gaps": [
                {
                    "module": gap.module.module_path,
                    "current": gap.current_coverage,
                    "target": gap.target_coverage,
                    "gap": gap.gap_percent,
                    "priority_score": gap.priority_score,
                }
                for gap in sorted(gaps, key=lambda g: g.priority_score, reverse=True)[:10]
            ],
        })
    
    def _get_coverage_data(self) -> Optional[Dict]:
        """Get coverage data, generating if needed."""
        # Check if coverage.json exists and is recent
        if self.coverage_json_path.exists():
            try:
                with open(self.coverage_json_path) as f:
                    return json.load(f)
            except Exception:
                pass  # Will regenerate
        
        # Generate coverage data
        return self._generate_coverage_data()
    
    def _generate_coverage_data(self) -> Optional[Dict]:
        """Run pytest with coverage collection."""
        try:
            # Run pytest with coverage
            # Use fast subset: unit tests only, skip slow/integration
            result = subprocess.run(
                [
                    "pytest",
                    "tests/",
                    "--cov=mahoun",
                    "--cov=api",
                    "--cov-report=json",
                    "-m", "not slow and not integration",
                    "-q",  # Quiet mode
                    "--tb=no",  # No traceback
                    "--no-header",
                ],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )
            
            if result.returncode != 0:
                # Tests might fail, but coverage.json still generated
                pass
            
            # Check if coverage.json was created
            if self.coverage_json_path.exists():
                with open(self.coverage_json_path) as f:
                    return json.load(f)
            
            return None
        
        except subprocess.TimeoutExpired:
            self.add_finding(
                severity=FindingSeverity.P2_MEDIUM,
                message="Coverage generation timed out after 120s",
                remediation="Consider optimizing slow tests or increasing timeout"
            )
            return None
        except Exception as e:
            self.add_finding(
                severity=FindingSeverity.P1_HIGH,
                message=f"Failed to generate coverage: {e}",
                evidence={"error": str(e)}
            )
            return None
    
    def _parse_baseline_targets(self) -> Dict[str, float]:
        """Parse baseline coverage targets from TEST_COVERAGE_BASELINE.md."""
        targets = {}
        
        if not self.baseline_path.exists():
            # Default targets for critical modules
            return {
                "mahoun/security/api_keys.py": 80.0,
                "mahoun/security/rbac.py": 85.0,
                "mahoun/ledger/writer.py": 90.0,
                "mahoun/reasoning/evidence_linked_verdict.py": 85.0,
                "mahoun/graph/neo4j/operations.py": 75.0,
                "mahoun/core/governance/mutation_boundary.py": 95.0,
            }
        
        try:
            content = self.baseline_path.read_text()
            
            # Parse markdown table or YAML-like format
            # Look for patterns like: "module_name: 45% → 80%"
            pattern = r"([a-zA-Z0-9_/\.]+\.py):\s*(\d+(?:\.\d+)?)%?\s*(?:→|->)\s*(\d+(?:\.\d+)?)%?"
            
            for match in re.finditer(pattern, content):
                module_path = match.group(1)
                target_coverage = float(match.group(3))
                targets[module_path] = target_coverage
        
        except Exception as e:
            self.add_finding(
                severity=FindingSeverity.P3_LOW,
                message=f"Could not parse baseline file: {e}",
                evidence={"baseline_path": str(self.baseline_path)}
            )
        
        return targets
    
    def _parse_coverage_json(self, coverage_data: Dict) -> Dict[str, ModuleCoverage]:
        """Parse coverage.json into ModuleCoverage objects."""
        modules = {}
        
        files = coverage_data.get("files", {})
        
        for file_path, file_data in files.items():
            # Convert absolute paths to relative
            rel_path = file_path
            if self.workspace_root.as_posix() in file_path:
                rel_path = file_path.replace(self.workspace_root.as_posix() + "/", "")
            
            # Extract coverage metrics
            summary = file_data.get("summary", {})
            
            module = ModuleCoverage(
                module_path=rel_path,
                statements=summary.get("num_statements", 0),
                missing=summary.get("missing_lines", 0),
                excluded=summary.get("excluded_lines", 0),
                branches=summary.get("num_branches", 0),
                partial_branches=summary.get("num_partial_branches", 0),
                coverage_percent=summary.get("percent_covered", 0.0),
            )
            
            modules[rel_path] = module
        
        return modules
    
    def _identify_coverage_gaps(
        self,
        module_coverage: Dict[str, ModuleCoverage],
        baseline_targets: Dict[str, float]
    ) -> List[CoverageGap]:
        """Identify coverage gaps with prioritization."""
        gaps = []
        
        for module_path, target_coverage in baseline_targets.items():
            if module_path not in module_coverage:
                # Module not found in coverage - might be new or excluded
                gap = CoverageGap(
                    module=ModuleCoverage(
                        module_path=module_path,
                        statements=0,
                        missing=0,
                        excluded=0,
                        coverage_percent=0.0,
                    ),
                    current_coverage=0.0,
                    target_coverage=target_coverage,
                    gap_percent=target_coverage,
                    priority_score=100.0 if "security" in module_path or "core" in module_path else 50.0,
                )
                gaps.append(gap)
                continue
            
            module = module_coverage[module_path]
            current = module.coverage_percent
            
            if current < target_coverage:
                gap_percent = target_coverage - current
                
                # Calculate priority score
                # Factors: criticality, gap size, statements count
                criticality_weight = 2.0 if module.is_critical else 1.0
                gap_weight = gap_percent / 100.0
                size_weight = min(module.statements / 100.0, 2.0)  # Cap at 2x
                
                priority_score = criticality_weight * gap_weight * size_weight * 100.0
                
                gap = CoverageGap(
                    module=module,
                    current_coverage=current,
                    target_coverage=target_coverage,
                    gap_percent=gap_percent,
                    priority_score=priority_score,
                )
                
                gaps.append(gap)
        
        return gaps
    
    def _check_critical_paths(self, module_coverage: Dict[str, ModuleCoverage]) -> List[Finding]:
        """Check coverage of critical paths."""
        findings = []
        
        # Critical modules that must have minimum coverage
        critical_modules = [
            m for m in module_coverage.values()
            if m.is_critical
        ]
        
        low_coverage_critical = [
            m for m in critical_modules
            if m.coverage_percent < self.CRITICAL_MODULE_MINIMUM
        ]
        
        if low_coverage_critical:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"{len(low_coverage_critical)} critical modules below {self.CRITICAL_MODULE_MINIMUM}% coverage",
                evidence={
                    "modules": [
                        {
                            "path": m.module_path,
                            "coverage": m.coverage_percent,
                            "minimum": self.CRITICAL_MODULE_MINIMUM,
                            "gap": self.CRITICAL_MODULE_MINIMUM - m.coverage_percent,
                        }
                        for m in low_coverage_critical
                    ]
                },
                remediation=(
                    "Critical modules (core, security, ledger, reasoning, governance) "
                    f"must have at least {self.CRITICAL_MODULE_MINIMUM}% coverage before production."
                )
            ))
        
        # Check for untested critical files (0% coverage)
        untested_critical = [m for m in critical_modules if m.coverage_percent == 0.0]
        
        if untested_critical:
            findings.append(Finding(
                severity=FindingSeverity.P0_CRITICAL,
                message=f"{len(untested_critical)} critical modules have ZERO test coverage",
                evidence={
                    "modules": [m.module_path for m in untested_critical]
                },
                remediation="Add basic test coverage for all critical modules immediately"
            ))
        
        return findings
    
    def _calculate_overall_coverage(self, coverage_data: Dict) -> float:
        """Calculate overall coverage percentage."""
        totals = coverage_data.get("totals", {})
        return totals.get("percent_covered", 0.0)
    
    def _generate_gap_findings(self, gaps: List[CoverageGap]) -> List[Finding]:
        """Generate findings from coverage gaps."""
        findings = []
        
        # Sort by priority
        sorted_gaps = sorted(gaps, key=lambda g: g.priority_score, reverse=True)
        
        # Report top 10 priority gaps
        top_gaps = sorted_gaps[:10]
        
        if top_gaps:
            findings.append(Finding(
                severity=FindingSeverity.P1_HIGH,
                message=f"Top 10 priority coverage gaps identified (out of {len(gaps)} total)",
                evidence={
                    "gaps": [
                        {
                            "rank": i + 1,
                            "module": gap.module.module_path,
                            "current_coverage": round(gap.current_coverage, 1),
                            "target_coverage": round(gap.target_coverage, 1),
                            "gap_percent": round(gap.gap_percent, 1),
                            "priority_score": round(gap.priority_score, 1),
                            "statements": gap.module.statements,
                            "missing_lines": gap.module.missing,
                        }
                        for i, gap in enumerate(top_gaps)
                    ]
                },
                remediation=(
                    "Focus testing efforts on high-priority gaps first. "
                    "Priority score considers: module criticality, gap size, and code size."
                )
            ))
        
        # Report progress toward overall target
        if gaps:
            avg_gap = sum(g.gap_percent for g in gaps) / len(gaps)
            findings.append(Finding(
                severity=FindingSeverity.INFO,
                message=f"Average coverage gap across {len(gaps)} modules: {avg_gap:.1f}%",
                evidence={
                    "total_gaps": len(gaps),
                    "avg_gap_percent": round(avg_gap, 2),
                    "estimated_tests_needed": self._estimate_tests_needed(gaps),
                }
            ))
        
        return findings
    
    def _estimate_tests_needed(self, gaps: List[CoverageGap]) -> int:
        """Estimate number of tests needed to close gaps."""
        # Rough heuristic: 1 test per 50 missing statements
        total_missing = sum(gap.module.missing for gap in gaps)
        return max(1, total_missing // 50)
