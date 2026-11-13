#!/usr/bin/env python3
"""
Serial Test Classification (no multiprocessing)
"""
import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

CRITICAL_MODULES = {
    "fortress_validator",
    "FortressValidator",
    "unified_reasoning_service",
    "governance_kernel",
    "mutation_boundary",
}


def analyze_test_file(file_path: Path):
    """Analyze a single test file"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        print(f"  ⚠️  Parse error: {file_path.name}", file=sys.stderr)
        return [], [], 0.0

    test_functions = []
    imported_modules = []

    # Extract imports
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("mahoun."):
                imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("mahoun."):
                    imported_modules.append(alias.name)

    # Extract test functions
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                test_functions.append(node.name)

    return test_functions, imported_modules, 1.0


def classify_test(file_path: Path, rel_path: str, content: str):
    """Classify a single test file"""
    
    # Read and analyze
    test_functions, imported_modules, _ = analyze_test_file(file_path)
    
    if not test_functions:
        return None
    
    # Check for critical dependencies
    has_critical = any(crit in mod for mod in imported_modules for crit in CRITICAL_MODULES)
    critical_found = [m for m in imported_modules if any(c in m for c in CRITICAL_MODULES)]
    
    # P3: Explicitly marked slow, benchmark
    if any(m in content for m in ["@pytest.mark.slow", "@pytest.mark.benchmark", "SLOW=True"]):
        return ("p3", f"Explicit slow/benchmark", len(test_functions))
    
    # P0: Critical path tests
    p0_patterns = [
        "contracts/test_fortress",
        "governance/test_api_integration",
        "test_fortress_validator",
        "test_proof_carrying",
    ]
    if any(p in rel_path for p in p0_patterns):
        return ("p0", f"Critical path", len(test_functions))
    
    # P0: Critical dependencies
    if has_critical:
        return ("p0", f"Critical: {', '.join(critical_found[:2])}", len(test_functions))
    
    # P1: Core business logic
    p1_patterns = [
        "tests/reasoning/",
        "tests/ledger/",
        "tests/core/",
        "tests/security/",
    ]
    if any(p in rel_path for p in p1_patterns):
        return ("p1", "Core business logic", len(test_functions))
    
    # P2: Integration tests  
    if "integration" in rel_path.lower() or "@pytest.mark.integration" in content:
        return ("p2", "Integration test", len(test_functions))
    
    # P2: Infrastructure
    p2_patterns = [
        "tests/graph/",
        "tests/pipelines/",
        "tests/agents/",
        "tests/rag/",
    ]
    if any(p in rel_path for p in p2_patterns):
        return ("p2", "Infrastructure", len(test_functions))
    
    # Default
    return ("p2", "Default tier", len(test_functions))


def add_marker(file_path: Path, tier: str) -> int:
    """Add pytest marker to test file"""
    try:
        content = file_path.read_text()
    except Exception:
        return 0
    
    marker = f"@pytest.mark.{tier}"
    if marker in content:
        return 0
    
    try:
        tree = ast.parse(content)
    except Exception:
        return 0
    
    lines = content.splitlines(keepends=True)
    markers_added = 0
    insertions = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                func_line = node.lineno - 1
                check_start = max(0, func_line - 10)
                preceding = "".join(lines[check_start:func_line])
                
                if marker not in preceding:
                    indent = len(lines[func_line]) - len(lines[func_line].lstrip())
                    marker_line = " " * indent + marker + "\n"
                    insertions.append((func_line, marker_line))
    
    for line_num, marker_line in sorted(insertions, reverse=True):
        lines.insert(line_num, marker_line)
        markers_added += 1
    
    if markers_added > 0:
        try:
            file_path.write_text("".join(lines))
        except Exception:
            return 0
    
    return markers_added


def main():
    repo_root = Path("/home/haji/Desktop/KingMahouN")
    tests_dir = repo_root / "tests"
    
    # Search tests directory (98% of all tests are here)
    test_files = sorted(tests_dir.rglob("test_*.py"))
    
    print(f"📊 Found {len(test_files)} test files")
    print()
    
    tier_dist = defaultdict(int)
    test_dist = defaultdict(int)
    results = []
    markers_total = 0
    
    for i, tf in enumerate(test_files, 1):
        rel_path = str(tf.relative_to(repo_root))
        
        try:
            content = tf.read_text()
        except Exception:
            continue
        
        result = classify_test(tf, rel_path, content)
        if not result:
            continue
        
        tier, rationale, test_count = result
        markers_added = add_marker(tf, tier)
        
        tier_dist[tier] += 1
        test_dist[tier] += test_count
        markers_total += markers_added
        
        results.append({
            "path": rel_path,
            "tier": tier,
            "test_count": test_count,
            "markers_added": markers_added,
        })
        
        if i % 50 == 0:
            print(f"  [{i}/{len(test_files)}] Processing... ({markers_total} markers added so far)")
    
    print()
    print("=" * 80)
    print("TEST CLASSIFICATION SUMMARY")
    print("=" * 80)
    print(f"{'Tier':<6} {'Files':>8} {'Tests':>8}")
    print("-" * 80)
    for tier in ["p0", "p1", "p2", "p3"]:
        print(f"{tier.upper():<6} {tier_dist[tier]:>8} {test_dist[tier]:>8}")
    
    print()
    print(f"Total Markers Added: {markers_total}")
    print()
    
    # Save manifest
    manifest = {
        "tier_distribution": dict(tier_dist),
        "test_distribution": dict(test_dist),
        "total_files": len(results),
        "total_tests": sum(test_dist.values()),
        "markers_added": markers_total,
        "classifications": results[:100],  # Save sample
    }
    
    with open(repo_root / "test_classification_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    print("✅ Classification complete!")


if __name__ == "__main__":
    main()
