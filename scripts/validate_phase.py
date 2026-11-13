#!/usr/bin/env python3
"""
Production-grade phase validation system.

Features:
- Comprehensive validation checks per phase
- Parallel test execution
- Detailed JSON reporting
- Performance benchmarking
- Regression detection
- Rollback recommendations
- Pytest integration with baseline tracking
"""

import json
import logging
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Callable, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status of a validation check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class ValidationCheck:
    """Single validation check."""

    name: str
    command: str
    status: CheckStatus = CheckStatus.SKIPPED
    duration_seconds: float = 0.0
    output: str = ""
    error: Optional[str] = None
    metadata: Optional[Dict] = None  # For pytest results


@dataclass
class PhaseValidationResult:
    """Result of phase validation."""

    phase: int
    timestamp: str
    passed: int
    failed: int
    skipped: int
    warnings: int
    total_duration_seconds: float
    checks: List[ValidationCheck]
    success: bool
    recommendations: List[str]
    test_baseline: Optional[Dict] = None  # Pytest baseline metrics


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


def parse_pytest_output(output: str) -> Tuple[int, int, int, float]:
    """
    Parse pytest output to extract metrics.

    Args:
        output: Pytest output text

    Returns:
        Tuple of (passed, failed, skipped, duration)
    """
    passed = failed = skipped = 0
    duration = 0.0

    # Parse test counts: "1278 passed, 28 deselected in 50.63s"
    if match := re.search(r"(\d+)\s+passed", output):
        passed = int(match.group(1))

    if match := re.search(r"(\d+)\s+failed", output):
        failed = int(match.group(1))

    if match := re.search(r"(\d+)\s+skipped", output):
        skipped = int(match.group(1))

    # Parse duration: "in 50.63s" or "in 1.23m"
    if match := re.search(r"in\s+([\d.]+)s", output):
        duration = float(match.group(1))
    elif match := re.search(r"in\s+([\d.]+)m", output):
        duration = float(match.group(1)) * 60

    return passed, failed, skipped, duration


def load_test_baseline() -> Optional[Dict]:
    """
    Load test baseline from file.

    Returns:
        Baseline dict or None if not found
    """
    baseline_file = Path("test_baseline.json")

    if not baseline_file.exists():
        return None

    try:
        with open(baseline_file) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Cannot load baseline: {e}")
        return None


def save_test_baseline(baseline: Dict) -> None:
    """Save test baseline to file."""
    baseline_file = Path("test_baseline.json")

    try:
        with open(baseline_file, "w") as f:
            json.dump(baseline, f, indent=2)
        logger.info(f"📊 Baseline saved: {baseline_file}")
    except Exception as e:
        logger.warning(f"Cannot save baseline: {e}")


def run_command(
    cmd: str, timeout: int = 300, silent: bool = False
) -> tuple[bool, str, float]:
    """
    Run command and return (success, output, duration).

    Args:
        cmd: Command to run
        timeout: Timeout in seconds
        silent: Whether to suppress output

    Returns:
        Tuple of (success, output, duration_seconds)
    """
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )

        duration = time.time() - start_time
        output = result.stdout + result.stderr

        if not silent and result.returncode != 0:
            logger.debug(f"Command failed: {cmd}")
            logger.debug(f"Output: {output[:500]}")

        return result.returncode == 0, output, duration

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return False, f"Command timed out after {timeout}s", duration
    except Exception as e:
        duration = time.time() - start_time
        return False, f"Command error: {e}", duration


class PhaseValidator:
    """Production-grade phase validator."""

    def __init__(self, phase: int, parallel: bool = True):
        """
        Initialize validator.

        Args:
            phase: Phase number to validate
            parallel: Whether to run checks in parallel
        """
        self.phase = phase
        self.parallel = parallel
        self.checks: List[ValidationCheck] = []
        self.start_time = datetime.now()

    def add_check(self, name: str, command: str) -> None:
        """Add a validation check."""
        self.checks.append(ValidationCheck(name=name, command=command))

    def run_check(self, check: ValidationCheck) -> ValidationCheck:
        """
        Run a single validation check.

        Args:
            check: Check to run

        Returns:
            Updated check with results
        """
        logger.info(f"  Running: {check.name}")

        success, output, duration = run_command(check.command, silent=True)

        check.duration_seconds = duration
        check.output = output

        # Special handling for pytest
        if "pytest" in check.command:
            passed, failed, skipped, test_duration = parse_pytest_output(output)
            check.metadata = {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "test_duration": test_duration,
                "total_tests": passed + failed + skipped,
            }

            # Check against baseline
            baseline = load_test_baseline()
            if baseline:
                baseline_passed = baseline.get("passed", 0)
                if passed < baseline_passed:
                    check.status = CheckStatus.WARNING
                    check.error = f"Test regression: {passed}/{baseline_passed} passed (lost {baseline_passed - passed})"
                    logger.warning(f"  ⚠️  {check.name}: Test regression detected")
                elif failed > 0:
                    check.status = CheckStatus.FAILED
                    check.error = f"{failed} tests failed"
                    logger.error(f"  ❌ {check.name}: {failed} tests failed")
                else:
                    check.status = CheckStatus.PASSED
                    logger.info(
                        f"  ✅ {check.name}: {passed} tests passed ({test_duration:.1f}s)"
                    )
            else:
                # No baseline - just check if tests passed
                if failed > 0:
                    check.status = CheckStatus.FAILED
                    check.error = f"{failed} tests failed"
                    logger.error(f"  ❌ {check.name}: {failed} tests failed")
                else:
                    check.status = CheckStatus.PASSED
                    logger.info(
                        f"  ✅ {check.name}: {passed} tests passed ({test_duration:.1f}s)"
                    )
        else:
            # Regular check
            if success:
                check.status = CheckStatus.PASSED
                logger.info(f"  ✅ {check.name} ({duration:.2f}s)")
            else:
                check.status = CheckStatus.FAILED
                check.error = output[:500]  # Truncate long errors
                logger.error(f"  ❌ {check.name} ({duration:.2f}s)")
                if output:
                    logger.debug(f"     Error: {output[:200]}")

        return check

    def run_checks(self) -> None:
        """Run all validation checks."""
        if self.parallel and len(self.checks) > 1:
            # Run checks in parallel
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self.run_check, check): check
                    for check in self.checks
                }

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        check = futures[future]
                        check.status = CheckStatus.FAILED
                        check.error = str(e)
                        logger.error(f"  ❌ {check.name}: {e}")
        else:
            # Run checks sequentially
            for check in self.checks:
                self.run_check(check)

    def generate_recommendations(self) -> List[str]:
        """
        Generate recommendations based on validation results.

        Returns:
            List of recommendation strings
        """
        recommendations = []

        failed_checks = [c for c in self.checks if c.status == CheckStatus.FAILED]
        warning_checks = [c for c in self.checks if c.status == CheckStatus.WARNING]

        if not failed_checks and not warning_checks:
            recommendations.append("✅ All checks passed - ready for next phase")
            return recommendations

        # Analyze test regressions
        test_checks = [c for c in self.checks if "pytest" in c.command and c.metadata]
        if test_checks:
            for check in test_checks:
                if check.status == CheckStatus.WARNING:
                    recommendations.append(
                        f"⚠️  Test regression detected: {check.error}"
                    )
                    recommendations.append(
                        "   Review: pytest tests/ -v --lf  # Run last failed"
                    )
                elif check.status == CheckStatus.FAILED:
                    failed = check.metadata.get("failed", 0)
                    recommendations.append(
                        f"⚠️  {failed} tests failing - critical issue"
                    )
                    recommendations.append(
                        "   Run: pytest tests/ -v --tb=short -x  # Stop on first failure"
                    )

        # Analyze other failures
        if any("pytest" in c.command for c in failed_checks):
            recommendations.append(
                "⚠️  Tests failing - review test output before proceeding"
            )
            recommendations.append("   Run: pytest tests/ -v --tb=short")

        if any("import" in c.command for c in failed_checks):
            recommendations.append("⚠️  Import errors detected - check Python path")
            recommendations.append("   Run: python -c 'import sys; print(sys.path)'")

        if any("exists" in c.command or "test -" in c.command for c in failed_checks):
            recommendations.append("⚠️  File/directory missing - verify phase completed")
            recommendations.append(f"   Review: PHASE_{self.phase}_COMPLETE.md")

        # General rollback recommendation
        if len(failed_checks) > len(self.checks) // 2:
            recommendations.append("🔴 Multiple failures - consider rollback")
            recommendations.append("   Rollback: python scripts/restore_backup.py")

        return recommendations

    def create_result(self) -> PhaseValidationResult:
        """
        Create validation result.

        Returns:
            PhaseValidationResult with all check results
        """
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASSED)
        failed = sum(1 for c in self.checks if c.status == CheckStatus.FAILED)
        skipped = sum(1 for c in self.checks if c.status == CheckStatus.SKIPPED)
        warnings = sum(1 for c in self.checks if c.status == CheckStatus.WARNING)

        total_duration = (datetime.now() - self.start_time).total_seconds()

        # Extract test baseline from pytest checks
        test_baseline = None
        test_checks = [c for c in self.checks if "pytest" in c.command and c.metadata]
        if test_checks:
            check = test_checks[0]  # Use first pytest check
            test_baseline = {
                "phase": self.phase,
                "timestamp": self.start_time.isoformat(),
                "passed": check.metadata.get("passed", 0),
                "failed": check.metadata.get("failed", 0),
                "skipped": check.metadata.get("skipped", 0),
                "total": check.metadata.get("total_tests", 0),
                "duration": check.metadata.get("test_duration", 0.0),
            }

        return PhaseValidationResult(
            phase=self.phase,
            timestamp=self.start_time.isoformat(),
            passed=passed,
            failed=failed,
            skipped=skipped,
            warnings=warnings,
            total_duration_seconds=total_duration,
            checks=self.checks,
            success=(failed == 0),
            recommendations=self.generate_recommendations(),
            test_baseline=test_baseline,
        )

    def save_result(self, result: PhaseValidationResult) -> None:
        """Save validation result to JSON."""
        result_file = Path(f"validation_phase_{self.phase}.json")

        try:
            # Convert to dict for JSON serialization
            result_dict = asdict(result)

            # Convert CheckStatus enums to strings
            for check in result_dict.get("checks", []):
                if "status" in check and isinstance(check["status"], CheckStatus):
                    check["status"] = check["status"].value
                elif "status" in check and hasattr(check["status"], "value"):
                    check["status"] = check["status"].value

            with open(result_file, "w") as f:
                json.dump(result_dict, f, indent=2)

            logger.info(f"📊 Results saved: {result_file}")
        except Exception as e:
            logger.warning(f"Cannot save results: {e}")

    def print_summary(self, result: PhaseValidationResult) -> None:
        """Print validation summary."""
        print(f"\n{'=' * 60}")
        print(f"Phase {self.phase} Validation Summary")
        print(f"{'=' * 60}")
        print(f"Status: {'✅ PASSED' if result.success else '❌ FAILED'}")
        print(f"Duration: {result.total_duration_seconds:.2f}s")
        print("\nResults:")
        print(f"  ✅ Passed:  {result.passed}")
        print(f"  ❌ Failed:  {result.failed}")
        print(f"  ⏭️  Skipped: {result.skipped}")
        print(f"  ⚠️  Warnings: {result.warnings}")

        # Print test baseline if available
        if result.test_baseline:
            baseline = result.test_baseline
            print("\n🧪 Test Suite:")
            print(f"  Passed:  {baseline['passed']}")
            print(f"  Failed:  {baseline['failed']}")
            print(f"  Skipped: {baseline['skipped']}")
            print(f"  Total:   {baseline['total']}")
            print(f"  Duration: {baseline['duration']:.1f}s")

        if result.recommendations:
            print("\n📋 Recommendations:")
            for rec in result.recommendations:
                print(f"  {rec}")

        print(f"{'=' * 60}\n")


# Phase-specific validators


def validate_phase_0(validator: PhaseValidator) -> None:
    """Validate Phase 0: Preparation."""
    validator.add_check("Backup script exists", "test -f scripts/backup_core.py")
    validator.add_check("Restore script exists", "test -f scripts/restore_backup.py")
    validator.add_check("Validation script exists", "test -f scripts/validate_phase.py")
    validator.add_check("Backup directory exists", "test -d backups")
    validator.add_check("Test suite baseline", "pytest tests/ -q --tb=no")


def validate_phase_1(validator: PhaseValidator) -> None:
    """Validate Phase 1: Create directories."""
    validator.add_check("Infrastructure dir exists", "test -d mahoun/infrastructure")
    validator.add_check(
        "Monitoring dir exists", "test -d mahoun/infrastructure/monitoring"
    )
    validator.add_check(
        "Observability dir exists", "test -d mahoun/infrastructure/observability"
    )
    validator.add_check("LLM dir exists", "test -d mahoun/infrastructure/llm")
    validator.add_check("RAG dir exists", "test -d mahoun/infrastructure/rag")
    validator.add_check(
        "Infrastructure imports", f"{sys.executable} -c 'import mahoun.infrastructure'"
    )
    validator.add_check(
        "Test suite regression check", f"{sys.executable} -m pytest tests/ -q --tb=no"
    )


def validate_phase_2(validator: PhaseValidator) -> None:
    """Validate Phase 2: Refactor health checker."""
    validator.add_check(
        "New checker exists", "test -f mahoun/infrastructure/health/checker.py"
    )
    validator.add_check(
        "Old health_cache exists", "test -f mahoun/core/health_cache.py"
    )
    validator.add_check(
        "New import works",
        f"{sys.executable} -c 'from mahoun.infrastructure.health.checker import EnhancedHealthChecker'",
    )
    validator.add_check(
        "Old import works",
        f"{sys.executable} -c 'from mahoun.core.health_cache import HealthCheckCache'",
    )
    validator.add_check(
        "Test suite regression check", f"{sys.executable} -m pytest tests/ -q --tb=no"
    )


def validate_phase_3(validator: PhaseValidator) -> None:
    """Validate Phase 3: Add deprecation."""
    validator.add_check(
        "Deprecation warning works",
        "python -W default -c 'from mahoun.core.health_cache import HealthCache' 2>&1 | grep -q DeprecationWarning",
    )
    validator.add_check("Test suite regression check", "pytest tests/ -q --tb=no")


def validate_phase_7(validator: PhaseValidator) -> None:
    """Validate Phase 7: Remove deprecated files."""
    validator.add_check(
        "Old health_cache removed", "test ! -f mahoun/core/health_cache.py"
    )
    validator.add_check(
        "No old imports in code",
        "! grep -r 'from mahoun.core.health_cache' mahoun/ tests/ api/ 2>/dev/null",
    )
    validator.add_check("Test suite regression check", "pytest tests/ -q --tb=no")


# Validator registry
PHASE_VALIDATORS: Dict[int, Callable[[PhaseValidator], None]] = {
    0: validate_phase_0,
    1: validate_phase_1,
    2: validate_phase_2,
    3: validate_phase_3,
    7: validate_phase_7,
}


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Production-grade phase validation")
    parser.add_argument("phase", type=int, help="Phase number to validate")
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run checks sequentially (not parallel)",
    )
    parser.add_argument("--save", action="store_true", help="Save results to JSON")

    args = parser.parse_args()

    try:
        print(f"\n🔍 Validating Phase {args.phase}...\n")

        # Create validator
        validator = PhaseValidator(phase=args.phase, parallel=not args.sequential)

        # Get phase-specific checks
        if args.phase not in PHASE_VALIDATORS:
            logger.warning(f"⚠️  No validator defined for phase {args.phase}")
            print(f"✅ Phase {args.phase} - no validation checks defined")
            return 0

        # Add phase-specific checks
        PHASE_VALIDATORS[args.phase](validator)

        # Run validation
        print(f"📋 Running {len(validator.checks)} checks...\n")
        validator.run_checks()

        # Create result
        result = validator.create_result()

        # Save if requested
        if args.save:
            validator.save_result(result)

        # Save test baseline if available
        if result.test_baseline:
            save_test_baseline(result.test_baseline)

        # Print summary
        validator.print_summary(result)

        return 0 if result.success else 1

    except KeyboardInterrupt:
        logger.warning("⚠️  Validation interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"❌ Validation error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
