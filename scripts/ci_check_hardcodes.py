#!/usr/bin/env python3
"""
CI Gate: Check for Hardcoded Values
====================================
Fails if hardcoded paths or credentials are found in Python code.

Usage:
    python scripts/ci_check_hardcodes.py

Exit codes:
    0 = Clean
    1 = Hardcoded paths found
    2 = Hardcoded credentials found
    4 = Split-authority patterns found
    ... = Combination of above (bitwise OR)
"""

import re
import sys
from pathlib import Path

# Patterns that should NEVER appear in code
FORBIDDEN_PATH_PATTERNS = [
    r"/home/\w+/",  # Linux home directories
    r"/Users/\w+/",  # macOS home directories
    r"C:\\Users\\",  # Windows home directories
    r"D:\\",  # Windows D: drive
    r"/mnt/\w+/",  # Linux mounts
]

FORBIDDEN_CREDENTIAL_PATTERNS = [
    r"password\s*=\s*['\"](?!.*\{)(?!dev_)[^'\"]{4,}['\"]",  # Hardcoded password (not placeholder)
    r"os\.getenv\(['\"].*PASSWORD['\"],\s*['\"](?!dev_)[^'\"]{4,}['\"]",  # getenv with real default
    r"api[_-]?key\s*=\s*['\"](?!your-|sk-test)[^'\"]{10,}['\"]",  # API keys
    r"AKIA[0-9A-Z]{16}",  # AWS access keys
    r"secret\s*=\s*['\"][^'\"]{10,}['\"]",  # Generic secrets
]

FORBIDDEN_AUTHORITY_PATTERNS = [
    r"os\.getenv\(['\"]MAHOUN_ENV['\"]",  # Direct read of MAHOUN_ENV
    r"os\.environ\.get\(['\"]MAHOUN_ENV['\"]",  # Direct read via environ.get
    r"os\.environ\[['\"]MAHOUN_ENV['\"]\]",  # Direct read via environ[...]
]

# Directories to skip
SKIP_DIRS = {
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "*.egg-info",
    "migrations",
    ".kilo",
    "MAHOUN_v2_clean",
    "build",
    "dist",
    "archive",
    "backups",
}

# Files to skip
SKIP_FILES = {
    "ci_check_hardcodes.py",  # This file
    "secrets.py",  # Our secrets module with dev defaults
    "paths.py",  # Path validation module contains patterns as strings
    "environment.py",  # The canonical authority itself MUST read the environment
}


def should_skip(path: Path) -> bool:
    """Check if path should be skipped"""
    parts = path.parts
    for skip in SKIP_DIRS:
        if skip in parts:
            return True
    if path.name in SKIP_FILES:
        return True
    # Skip test files (they often contain example patterns for validation)
    if "tests" in parts or path.name.startswith("test_"):
        return True
    return False


def scan_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Scan a file for forbidden patterns. Returns list of (line_num, line, pattern_type)"""
    issues = []

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # Check path patterns
            for pattern in FORBIDDEN_PATH_PATTERNS:
                if re.search(pattern, line):
                    issues.append((i, line.strip()[:100], "PATH"))
                    break

            # Check credential patterns
            for pattern in FORBIDDEN_CREDENTIAL_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Extra check: skip if it's in a comment or docstring context
                    if '"""' in line or "'''" in line or "# " in line:
                        continue
                    issues.append((i, line.strip()[:100], "CREDENTIAL"))
                    break

            # Check authority patterns
            for pattern in FORBIDDEN_AUTHORITY_PATTERNS:
                if re.search(pattern, line):
                    if '"""' in line or "'''" in line or "# " in line:
                        continue
                    issues.append((i, line.strip()[:100], "AUTHORITY"))
                    break

    except Exception as e:
        print(f"⚠️ Could not scan {filepath}: {e}", file=sys.stderr)

    return issues


def main() -> int:
    """Main entry point"""
    print("🔍 Scanning for hardcoded values...")
    print()

    repo_root = Path(__file__).parent.parent

    path_issues = []
    cred_issues = []
    auth_issues = []

    # Scan all Python files
    for filepath in repo_root.rglob("*.py"):
        if should_skip(filepath):
            continue

        issues = scan_file(filepath)
        for line_num, line, issue_type in issues:
            rel_path = filepath.relative_to(repo_root)
            if issue_type == "PATH":
                path_issues.append((rel_path, line_num, line))
            elif issue_type == "CREDENTIAL":
                cred_issues.append((rel_path, line_num, line))
            elif issue_type == "AUTHORITY":
                auth_issues.append((rel_path, line_num, line))

    # Report
    exit_code = 0

    if path_issues:
        print("❌ HARDCODED PATHS FOUND:")
        print("-" * 60)
        for path, line_num, line in path_issues:
            print(f"  {path}:{line_num}")
            print(f"    {line}")
        print()
        exit_code |= 1
    else:
        print("✅ No hardcoded paths found")

    if cred_issues:
        print("❌ HARDCODED CREDENTIALS FOUND:")
        print("-" * 60)
        for path, line_num, line in cred_issues:
            print(f"  {path}:{line_num}")
            print(f"    {line[:80]}...")
        print()
        exit_code |= 2
    else:
        print("✅ No hardcoded credentials found")

    if auth_issues:
        print("❌ SPLIT-AUTHORITY PATTERNS FOUND:")
        print("-" * 60)
        for path, line_num, line in auth_issues:
            print(f"  {path}:{line_num}")
            print(f"    {line}")
        print()
        exit_code |= 4
    else:
        print("✅ No split-authority patterns found")

    print()
    if exit_code == 0:
        print("🎉 All checks passed!")
    else:
        print("💥 Gate FAILED - fix the issues above")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
