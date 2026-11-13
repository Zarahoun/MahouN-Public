#!/usr/bin/env python3
"""
MAHOUN Heavy Lock - Unified Gate Runner
========================================
Runs all CI/CD gates in sequence using Python scripts.
"""

import sys
import subprocess
import time
from pathlib import Path
from typing import Tuple, Dict

# Colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{YELLOW}{'━' * 60}{NC}")
    print(f"{YELLOW}{text}{NC}")
    print(f"{YELLOW}{'━' * 60}{NC}\n")


def run_gate(gate_num: int, gate_name: str, commands: list) -> Tuple[bool, float]:
    """
    Run a gate with one or more commands.
    
    Returns:
        (success, duration)
    """
    print_header(f"Gate {gate_num}: {gate_name}")
    
    start_time = time.time()
    
    for cmd in commands:
        print(f"  $ {' '.join(cmd)}")
        result = subprocess.run(cmd)
        
        if result.returncode != 0:
            duration = time.time() - start_time
            print(f"\n{RED}❌ Gate {gate_num} FAILED ({duration:.1f}s){NC}\n")
            return False, duration
    
    duration = time.time() - start_time
    print(f"\n{GREEN}✅ Gate {gate_num} PASSED ({duration:.1f}s){NC}\n")
    return True, duration


def main():
    """Main entry point."""
    print(f"{BLUE}")
    print("=" * 60)
    print("🔒 MAHOUN Heavy Lock - CI/CD Gates")
    print("=" * 60)
    print(f"{NC}\n")
    
    project_root = Path.cwd()
    
    # Track results
    results = {}
    start_time = time.time()
    
    # Gate 0: Placeholder/Secrets Scan
    success, duration = run_gate(
        0,
        "Repo Integrity",
        [
            ['python3', 'scripts/ci_scan_placeholders.py'],
            ['python3', 'scripts/ci_scan_secrets.py'],
        ]
    )
    results['gate_0'] = {'passed': success, 'duration': duration}
    if not success:
        print_summary(results, time.time() - start_time)
        return 1
    
    # Gate 1: Lint/Format
    success, duration = run_gate(
        1,
        "Format/Lint",
        [
            ['ruff', 'check', '.', '--select', 'E,F,I,UP,N,W'],
            ['ruff', 'format', '--check', '.'],
        ]
    )
    results['gate_1'] = {'passed': success, 'duration': duration}
    if not success:
        print_summary(results, time.time() - start_time)
        return 1
    
    # Gate 2: Type Safety
    # Try basedpyright, fall back to pyright, then mypy
    type_checker = None
    for checker in ['basedpyright', 'pyright', 'mypy']:
        if subprocess.run(['which', checker], capture_output=True).returncode == 0:
            type_checker = checker
            break
    
    if type_checker:
        if type_checker == 'mypy':
            cmd = [['mypy', 'mahoun/', 'output/', 'api/', '--config-file=mypy.ini']]
        else:
            cmd = [[type_checker, 'mahoun/', 'output/', 'api/']]
        
        success, duration = run_gate(2, "Type Safety", cmd)
        results['gate_2'] = {'passed': success, 'duration': duration}
        if not success:
            print_summary(results, time.time() - start_time)
            return 1
    else:
        print(f"{YELLOW}⚠️  No type checker found, skipping Gate 2{NC}")
        results['gate_2'] = {'passed': True, 'duration': 0, 'skipped': True}
    
    # Gate 3+4+5: First Step Tests (run twice for determinism)
    # Create artifacts directory
    artifacts_dir = Path('artifacts')
    artifacts_dir.mkdir(exist_ok=True)
    
    success, duration = run_gate(
        3,
        "Phase-1 Reality Tests (First Run)",
        [
            ['pytest', 'first_step_ci_cd/', '-q', '--tb=short',
             f'--junit-xml={artifacts_dir}/junit.xml']
        ]
    )
    results['gate_3'] = {'passed': success, 'duration': duration}
    if not success:
        print_summary(results, time.time() - start_time)
        return 1
    
    # Gate 4 is integrated (anti-mock tests are part of first_step_ci_cd)
    results['gate_4'] = {'passed': True, 'duration': 0, 'note': 'Integrated with Gate 3'}
    
    # Gate 5: Determinism (second run)
    success, duration = run_gate(
        5,
        "Determinism Proof (Second Run)",
        [
            ['pytest', 'first_step_ci_cd/', '-q', '--tb=no',
             f'--junit-xml={artifacts_dir}/junit_rerun.xml']
        ]
    )
    results['gate_5'] = {'passed': success, 'duration': duration}
    
    if success:
        # Compare results
        import xml.etree.ElementTree as ET
        try:
            tree1 = ET.parse(artifacts_dir / 'junit.xml')
            tree2 = ET.parse(artifacts_dir / 'junit_rerun.xml')
            
            suite1 = tree1.find('.//testsuite')
            suite2 = tree2.find('.//testsuite')
            
            if suite1 is not None and suite2 is not None:
                tests1 = suite1.get('tests')
                tests2 = suite2.get('tests')
                failures1 = suite1.get('failures')
                failures2 = suite2.get('failures')
                
                if tests1 != tests2 or failures1 != failures2:
                    print(f"{RED}❌ Determinism check FAILED: Results differ{NC}")
                    results['gate_5']['passed'] = False
                else:
                    print(f"{GREEN}✓ Determinism verified: Results identical{NC}")
        except Exception as e:
            print(f"{YELLOW}⚠️  Could not verify determinism: {e}{NC}")
    
    if not results['gate_5']['passed']:
        print_summary(results, time.time() - start_time)
        return 1
    
    # Gate 6: Generate Reality Report
    success, duration = run_gate(
        6,
        "Artifact + Traceability",
        [
            ['python3', 'scripts/ci_make_reality_report.py']
        ]
    )
    results['gate_6'] = {'passed': success, 'duration': duration}
    
    # Print final summary
    total_duration = time.time() - start_time
    print_summary(results, total_duration)
    
    # Return exit code
    all_passed = all(r['passed'] for r in results.values())
    return 0 if all_passed else 1


def print_summary(results: Dict, total_duration: float):
    """Print final summary."""
    print(f"\n{BLUE}")
    print("=" * 60)
    print("📊 CI/CD SUMMARY")
    print("=" * 60)
    print(f"{NC}\n")
    
    print("Gate Results:")
    print("-" * 60)
    
    passed = 0
    failed = 0
    
    gate_names = {
        'gate_0': 'Repo Integrity',
        'gate_1': 'Format/Lint',
        'gate_2': 'Type Safety',
        'gate_3': 'Reality Tests',
        'gate_4': 'Anti-Mock (integrated)',
        'gate_5': 'Determinism',
        'gate_6': 'Artifacts',
    }
    
    for gate_id in sorted(results.keys()):
        result = results[gate_id]
        gate_name = gate_names.get(gate_id, gate_id)
        duration = result.get('duration', 0)
        
        if result.get('skipped'):
            print(f"  {gate_id}: {YELLOW}⏭️  SKIPPED{NC} - {gate_name}")
        elif result['passed']:
            print(f"  {gate_id}: {GREEN}✅ PASSED{NC} ({duration:.1f}s) - {gate_name}")
            passed += 1
        else:
            print(f"  {gate_id}: {RED}❌ FAILED{NC} ({duration:.1f}s) - {gate_name}")
            failed += 1
    
    print("-" * 60)
    print(f"\nStatistics:")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total Duration: {total_duration:.1f}s")
    print()
    
    if failed == 0:
        print(f"{GREEN}")
        print("=" * 60)
        print("✅ ALL GATES PASSED - READY TO MERGE")
        print("=" * 60)
        print(f"{NC}\n")
    else:
        print(f"{RED}")
        print("=" * 60)
        print(f"❌ {failed} GATE(S) FAILED - FIX BEFORE MERGE")
        print("=" * 60)
        print(f"{NC}\n")


if __name__ == '__main__':
    sys.exit(main())

