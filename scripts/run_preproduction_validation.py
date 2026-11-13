#!/usr/bin/env python3
"""
Pre-Production Validation Runner
=================================

Orchestrates all preproduction validators and generates compliance report.

Usage:
    python scripts/run_preproduction_validation.py --profile production --fail-fast
    python scripts/run_preproduction_validation.py --profile staging
    python scripts/run_preproduction_validation.py --list-validators

Requirements:
    - Run from repository root
    - Virtual environment activated (venv/)
    - All dependencies installed (pip install -e ".[dev]")

Exit Codes:
    0: All validators passed (compliance ≥ 95%)
    1: Validation failed (blockers found or compliance < 95%)
    2: Configuration error (manifest not found, invalid config)
    3: Execution error (unexpected exception)
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any
import json

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mahoun.preproduction.orchestrator import ValidationOrchestrator
from mahoun.preproduction.validators import (
    ExceptionHierarchyValidator,
    TestClassificationValidator,
    CoverageValidator,
    SecurityHardeningValidator,
    InfrastructureValidator,
)
from mahoun.preproduction.models import ValidationStatus


def create_orchestrator(profile: str, workspace_root: Path) -> ValidationOrchestrator:
    """
    Create and configure orchestrator with all validators.
    
    Args:
        profile: Validation profile (development/staging/production)
        workspace_root: Repository root path
    
    Returns:
        Configured ValidationOrchestrator
    """
    from mahoun.preproduction.models import ValidationManifest, ValidatorConfig
    
    # Define validators
    validator_configs = [
        ValidatorConfig(
            validator_id="exception_hierarchy",
            class_name="ExceptionHierarchyValidator",
            domain="exception_handling",
            enabled=True,
            dependencies=[],
            timeout_seconds=30,
            fail_fast=True,
            config={
                "max_hierarchy_depth": 4,
                "require_docstrings": True,
            },
        ),
        ValidatorConfig(
            validator_id="test_classification",
            class_name="TestClassificationValidator",
            domain="testing",
            enabled=True,
            dependencies=[],
            timeout_seconds=60,
            fail_fast=False,
            config={
                "require_markers": ["unit", "integration", "slow"],
                "max_unmarked_tests": 0,
            },
        ),
        ValidatorConfig(
            validator_id="coverage",
            class_name="CoverageValidator",
            domain="testing",
            enabled=True,
            dependencies=["test_classification"],
            timeout_seconds=120,
            fail_fast=False,
            config={
                "min_coverage_percent": 61.0 if profile == "production" else 50.0,
                "p0_modules": [
                    "mahoun/ledger/writer.py",
                    "mahoun/reasoning/evidence_linked_verdict.py",
                    "mahoun/graph/neo4j/operations.py",
                ],
                "min_p0_coverage": 80.0,
            },
        ),
        ValidatorConfig(
            validator_id="security",
            class_name="SecurityHardeningValidator",
            domain="security",
            enabled=True,
            dependencies=[],
            timeout_seconds=90,
            fail_fast=True,
            config={
                "check_secrets": True,
                "check_dependencies": True,
                "check_permissions": True,
            },
        ),
        ValidatorConfig(
            validator_id="infrastructure",
            class_name="InfrastructureValidator",
            domain="infrastructure",
            enabled=True,
            dependencies=[],
            timeout_seconds=60,
            fail_fast=False,
            config={
                "max_image_size_mb": 500,
                "max_critical_cves": 0,
                "require_health_checks": True,
            },
        ),
    ]
    
    manifest = ValidationManifest(
        version="1.0",
        profile=profile,
        validators=validator_configs,
        thresholds={
            "min_compliance_score": 0.95,
            "max_p0_findings": 0,
            "max_p1_findings": 5,
        },
    )
    
    orchestrator = ValidationOrchestrator(
        manifest=manifest,
        workspace_root=workspace_root,
    )
    
    # Register validators with flexible factory pattern
    # NOTE: This is a workaround for inconsistent __init__ signatures
    # See PHASE_5_VALIDATOR_SIGNATURE_ISSUE.md for details
    # TODO: Fix validator signatures to match DomainValidator base class
    
    from mahoun.preproduction.evidence_collector import EvidenceCollector
    evidence = EvidenceCollector(workspace_root=workspace_root)
    
    # Helper function to handle different constructor signatures
    def try_register(validator_class, name):
        """Try multiple instantiation patterns until one works"""
        patterns = [
            # Pattern 1: Full signature (ideal)
            lambda: validator_class(name, evidence, workspace_root),
            # Pattern 2: project_root only
            lambda: validator_class(project_root=workspace_root),
            # Pattern 3: evidence + workspace_root
            lambda: validator_class(evidence, workspace_root),
            # Pattern 4: evidence only
            lambda: validator_class(evidence),
            # Pattern 5: No args (unlikely but try it)
            lambda: validator_class(),
        ]
        
        for i, pattern in enumerate(patterns, 1):
            try:
                validator = pattern()
                orchestrator.register_validator(validator)
                return True
            except TypeError as e:
                if i == len(patterns):
                    # All patterns failed
                    raise RuntimeError(
                        f"Could not instantiate {validator_class.__name__} with any known pattern. "
                        f"Last error: {e}. See PHASE_5_VALIDATOR_SIGNATURE_ISSUE.md"
                    )
                continue  # Try next pattern
        return False
    
    # Register each validator (will auto-detect correct signature)
    try_register(ExceptionHierarchyValidator, "exception_hierarchy")
    try_register(TestClassificationValidator, "test_classification")
    try_register(CoverageValidator, "coverage")
    try_register(SecurityHardeningValidator, "security")
    try_register(InfrastructureValidator, "infrastructure")
    
    return orchestrator


def list_validators(orchestrator: ValidationOrchestrator) -> None:
    """Print all registered validators"""
    print("📋 Registered Validators:")
    print()
    
    for validator_id, validator in orchestrator.validators.items():
        deps = validator.get_dependencies()
        deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
        print(f"  • {validator_id}{deps_str}")
    
    print()
    print(f"Total: {len(orchestrator.validators)} validators")


def print_summary(result: Any) -> None:
    """Print concise summary to stdout"""
    status_emoji = {
        ValidationStatus.PASS: "✅",
        ValidationStatus.WARNING: "⚠️",
        ValidationStatus.FAIL: "❌",
        ValidationStatus.BLOCKED: "🚫",
    }
    
    print()
    print("=" * 70)
    print("PRE-PRODUCTION VALIDATION SUMMARY")
    print("=" * 70)
    print()
    
    print(f"Profile: {result.profile}")
    print(f"Compliance Score: {result.compliance_score:.1%}")
    print(f"Execution Time: {result.execution_time_ms:.0f}ms")
    print()
    
    print("Validator Results:")
    for res in result.results:
        emoji = status_emoji.get(res.status, "❓")
        findings_str = f" ({len(res.findings)} findings)" if res.findings else ""
        print(f"  {emoji} {res.validator_id}: {res.status.value}{findings_str}")
    
    print()
    
    if result.blockers:
        print(f"❌ BLOCKERS: {len(result.blockers)} P0 issues found")
        for i, blocker in enumerate(result.blockers, 1):
            print(f"   {i}. {blocker.message}")
        print()
    
    if result.warnings:
        p1 = sum(1 for w in result.warnings if w.severity.value == "P1_HIGH")
        p2 = sum(1 for w in result.warnings if w.severity.value == "P2_MEDIUM")
        p3 = sum(1 for w in result.warnings if w.severity.value == "P3_LOW")
        print(f"⚠️  WARNINGS: {len(result.warnings)} issues (P1: {p1}, P2: {p2}, P3: {p3})")
        print()
    
    print("=" * 70)
    print(f"PRODUCTION READY: {'✅ YES' if result.is_production_ready else '❌ NO'}")
    print("=" * 70)
    print()


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run pre-production validation suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--profile",
        choices=["development", "staging", "production"],
        default="production",
        help="Validation profile (default: production)",
    )
    
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first P0 failure",
    )
    
    parser.add_argument(
        "--list-validators",
        action="store_true",
        help="List all validators and exit",
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        help="Write report to file (markdown format)",
    )
    
    parser.add_argument(
        "--json",
        type=Path,
        help="Write results to JSON file",
    )
    
    args = parser.parse_args()
    
    try:
        # Create orchestrator
        workspace_root = REPO_ROOT
        orchestrator = create_orchestrator(
            profile=args.profile,
            workspace_root=workspace_root,
        )
        
        # List validators if requested
        if args.list_validators:
            list_validators(orchestrator)
            return 0
        
        # Run validation
        print(f"🚀 Running pre-production validation (profile: {args.profile})...")
        print()
        
        result = orchestrator.run_validation(
            profile=args.profile,
            fail_fast=args.fail_fast,
        )
        
        # Print summary
        print_summary(result)
        
        # Write report if requested
        if args.output:
            report = orchestrator.generate_report(result)
            args.output.write_text(report, encoding="utf-8")
            print(f"📄 Report written to: {args.output}")
            print()
        
        # Write JSON if requested
        if args.json:
            json_data = {
                "profile": result.profile,
                "timestamp": result.timestamp.isoformat(),
                "overall_status": result.overall_status.value,
                "compliance_score": result.compliance_score,
                "is_production_ready": result.is_production_ready,
                "execution_time_ms": result.execution_time_ms,
                "blockers_count": len(result.blockers),
                "warnings_count": len(result.warnings),
                "results": [
                    {
                        "validator_id": r.validator_id,
                        "status": r.status.value,
                        "findings_count": len(r.findings),
                        "execution_time_ms": r.execution_time_ms,
                    }
                    for r in result.results
                ],
            }
            args.json.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
            print(f"📊 JSON results written to: {args.json}")
            print()
        
        # Return exit code
        if result.compliance_score < 0.95:
            print("❌ FAIL: Compliance score below 95% threshold")
            return 1
        
        if result.blockers:
            print(f"❌ FAIL: {len(result.blockers)} P0 blockers found")
            return 1
        
        if result.overall_status == ValidationStatus.BLOCKED:
            print("❌ FAIL: Validation blocked")
            return 1
        
        print("✅ SUCCESS: All validation gates passed!")
        return 0
    
    except FileNotFoundError as e:
        print(f"❌ Configuration Error: {e}", file=sys.stderr)
        return 2
    
    except Exception as e:
        print(f"❌ Execution Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
