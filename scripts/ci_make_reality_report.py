#!/usr/bin/env python3
"""
Gate 6: Reality Report Generator
==================================
Generates comprehensive CI/CD artifacts and traceability reports.
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib

# Colors
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
NC = '\033[0m'


def run_command(cmd: list, capture=True) -> dict:
    """Run a command and return result."""
    try:
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        else:
            result = subprocess.run(cmd, timeout=30)
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'returncode': -1
        }


def get_git_info() -> dict:
    """Get Git information."""
    info = {}
    
    # Commit SHA
    result = run_command(['git', 'rev-parse', 'HEAD'])
    info['commit_sha'] = result['stdout'].strip() if result['success'] else 'unknown'
    
    # Short SHA
    result = run_command(['git', 'rev-parse', '--short', 'HEAD'])
    info['commit_sha_short'] = result['stdout'].strip() if result['success'] else 'unknown'
    
    # Branch
    result = run_command(['git', 'branch', '--show-current'])
    info['branch'] = result['stdout'].strip() if result['success'] else 'unknown'
    
    # Commit message
    result = run_command(['git', 'log', '-1', '--pretty=%B'])
    info['commit_message'] = result['stdout'].strip() if result['success'] else ''
    
    # Author
    result = run_command(['git', 'log', '-1', '--pretty=%an <%ae>'])
    info['commit_author'] = result['stdout'].strip() if result['success'] else ''
    
    # Commit date
    result = run_command(['git', 'log', '-1', '--pretty=%ci'])
    info['commit_date'] = result['stdout'].strip() if result['success'] else ''
    
    return info


def get_python_info() -> dict:
    """Get Python environment information."""
    info = {}
    
    # Python version
    result = run_command(['python3', '--version'])
    info['python_version'] = result['stdout'].strip() if result['success'] else 'unknown'
    
    # Pip version
    result = run_command(['pip', '--version'])
    info['pip_version'] = result['stdout'].strip() if result['success'] else 'unknown'
    
    return info


def get_dependency_hash() -> str:
    """Get hash of requirements files for dependency tracking."""
    hasher = hashlib.sha256()
    
    for req_file in ['requirements.txt', 'requirements-full.txt', 'pyproject.toml']:
        path = Path(req_file)
        if path.exists():
            hasher.update(path.read_bytes())
    
    return hasher.hexdigest()[:16]


def parse_junit_xml(xml_path: Path) -> dict:
    """Parse JUnit XML to extract test statistics."""
    if not xml_path.exists():
        return {}
    
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Get testsuite element
        testsuite = root.find('.//testsuite')
        if testsuite is not None:
            return {
                'tests': int(testsuite.get('tests', 0)),
                'failures': int(testsuite.get('failures', 0)),
                'errors': int(testsuite.get('errors', 0)),
                'skipped': int(testsuite.get('skipped', 0)),
                'time': float(testsuite.get('time', 0)),
            }
    except Exception as e:
        print(f"{YELLOW}Warning: Could not parse JUnit XML: {e}{NC}", file=sys.stderr)
    
    return {}


def generate_reality_report() -> dict:
    """Generate comprehensive reality report."""
    print("📊 Generating reality report...")
    
    report = {
        'version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        'git': get_git_info(),
        'environment': {
            **get_python_info(),
            'dependency_hash': get_dependency_hash(),
        },
        'gates': {},
        'tests': {},
        'artifacts': [],
    }
    
    # Check for gate results (from previous runs)
    artifacts_dir = Path('artifacts')
    if artifacts_dir.exists():
        # Parse junit.xml
        junit_path = artifacts_dir / 'junit.xml'
        if junit_path.exists():
            report['tests']['first_run'] = parse_junit_xml(junit_path)
        
        # Parse junit_rerun.xml
        junit_rerun_path = artifacts_dir / 'junit_rerun.xml'
        if junit_rerun_path.exists():
            report['tests']['second_run'] = parse_junit_xml(junit_rerun_path)
        
        # Check determinism
        if junit_path.exists() and junit_rerun_path.exists():
            first = report['tests'].get('first_run', {})
            second = report['tests'].get('second_run', {})
            
            if first and second:
                deterministic = (
                    first.get('tests') == second.get('tests') and
                    first.get('failures') == second.get('failures') and
                    first.get('errors') == second.get('errors')
                )
                report['tests']['deterministic'] = deterministic
    
    # Overall status
    total_tests = report['tests'].get('first_run', {}).get('tests', 0)
    failures = report['tests'].get('first_run', {}).get('failures', 0)
    errors = report['tests'].get('first_run', {}).get('errors', 0)
    
    if failures == 0 and errors == 0 and total_tests > 0:
        report['status'] = 'PASS'
    elif failures > 0 or errors > 0:
        report['status'] = 'FAIL'
    else:
        report['status'] = 'UNKNOWN'
    
    return report


def generate_markdown_summary(report: dict) -> str:
    """Generate human-readable markdown summary."""
    md = []
    
    md.append("# CI/CD Reality Report")
    md.append("")
    
    # Git info
    git = report.get('git', {})
    md.append("## Git Information")
    md.append("")
    md.append(f"- **Commit:** `{git.get('commit_sha_short', 'unknown')}`")
    md.append(f"- **Branch:** `{git.get('branch', 'unknown')}`")
    md.append(f"- **Author:** {git.get('commit_author', 'unknown')}")
    md.append(f"- **Message:** {git.get('commit_message', '')[:100]}")
    md.append("")
    
    # Environment
    env = report.get('environment', {})
    md.append("## Environment")
    md.append("")
    md.append(f"- **Python:** {env.get('python_version', 'unknown')}")
    md.append(f"- **Dependencies Hash:** `{env.get('dependency_hash', 'unknown')}`")
    md.append(f"- **Generated:** {report.get('generated_at', 'unknown')}")
    md.append("")
    
    # Test results
    tests = report.get('tests', {})
    first_run = tests.get('first_run', {})
    
    if first_run:
        md.append("## Test Results")
        md.append("")
        md.append(f"- **Total Tests:** {first_run.get('tests', 0)}")
        md.append(f"- **Failures:** {first_run.get('failures', 0)}")
        md.append(f"- **Errors:** {first_run.get('errors', 0)}")
        md.append(f"- **Skipped:** {first_run.get('skipped', 0)}")
        md.append(f"- **Duration:** {first_run.get('time', 0):.2f}s")
        md.append("")
        
        # Determinism
        if 'deterministic' in tests:
            deterministic = tests['deterministic']
            status = "✅ YES" if deterministic else "❌ NO"
            md.append(f"- **Deterministic:** {status}")
            md.append("")
    
    # Overall status
    status = report.get('status', 'UNKNOWN')
    status_emoji = {
        'PASS': '✅',
        'FAIL': '❌',
        'UNKNOWN': '❓'
    }
    
    md.append("## Overall Status")
    md.append("")
    md.append(f"**{status_emoji.get(status, '❓')} {status}**")
    md.append("")
    
    return '\n'.join(md)


def main():
    """Main entry point."""
    print("=" * 60)
    print("📦 Gate 6: Reality Report Generator")
    print("=" * 60)
    print()
    
    # Create artifacts directory
    artifacts_dir = Path('artifacts')
    artifacts_dir.mkdir(exist_ok=True)
    
    # Generate report
    report = generate_reality_report()
    
    # Write JSON report
    json_path = artifacts_dir / 'reality_report.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"{GREEN}✓{NC} Generated: {json_path}")
    
    # Generate markdown summary
    md_content = generate_markdown_summary(report)
    md_path = artifacts_dir / 'ci_summary.md'
    with open(md_path, 'w') as f:
        f.write(md_content)
    print(f"{GREEN}✓{NC} Generated: {md_path}")
    
    # Print summary to console
    print()
    print("=" * 60)
    print("📊 Summary")
    print("=" * 60)
    print()
    print(md_content)
    
    # List all artifacts
    print()
    print("📦 Artifacts created:")
    for artifact in sorted(artifacts_dir.glob('*')):
        size = artifact.stat().st_size
        print(f"  - {artifact.name} ({size:,} bytes)")
    
    print()
    print(f"{GREEN}✅ Gate 6: PASSED{NC}")
    print()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())






