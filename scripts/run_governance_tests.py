#!/usr/bin/env python3
"""Run governance tests and report results"""
import subprocess
import sys

def run_test(test_path, description):
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "-x"],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0

def main():
    tests = [
        ("tests/governance/test_governance_context.py", "Governance Context Tests"),
        ("tests/governance/test_direct_driver_bypass.py", "Direct Driver Bypass Prevention"),
        ("tests/governance/test_api_database_firewall.py", "API Database Firewall"),
        ("tests/graph/test_wiring_verify.py", "Enhanced Graph Wiring Verification"),
    ]
    
    results = {}
    for test_path, description in tests:
        try:
            results[description] = run_test(test_path, description)
        except Exception as e:
            print(f"ERROR running {description}: {e}")
            results[description] = False
    
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for desc, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {desc}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} test suites passed")
    
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
