#!/bin/bash
#
# Gate 0: Repo Integrity
# ======================
# Blocks placeholder patterns and secrets from reaching main
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "🔒 Gate 0: Repo Integrity Check"
echo "================================================"
echo ""

VIOLATIONS=0

# Paths to check (ONLY critical runtime paths)
CORE_PATHS=(
    "mahoun/core/"
    "mahoun/domain/"
    "mahoun/schemas/"
    "mahoun/orchestrator/"
    "mahoun/mcp/"
    "api/"
)

# Paths to exclude
EXCLUDE_PATTERNS=(
    "*/tests/*"
    "*/test_*"
    "*/__pycache__/*"
    "*.pyc"
    "*/venv/*"
    "*/venv.old.conda/*"
)

echo "📁 Checking core paths..."
for path in "${CORE_PATHS[@]}"; do
    if [ -d "${PROJECT_ROOT}/${path}" ]; then
        echo "  ✓ ${path}"
    fi
done
echo ""

# Build exclude args for grep
EXCLUDE_ARGS=()
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS+=(--exclude="$pattern")
done

# Check 1: "pass" as sole function body (ONLY in critical paths)
echo "🔍 Check 1: Detecting 'pass' stubs in critical paths (AST scanner)..."
if python3 "${PROJECT_ROOT}/scripts/ci_check_pass_stubs.py" > /tmp/gate0_pass_$$.txt 2>&1; then
    echo -e "${GREEN}✓ No 'pass' stubs in critical paths${NC}"
else
    echo -e "${RED}❌ FAIL: Found 'pass' stubs in critical paths${NC}"
    cat /tmp/gate0_pass_$$.txt 2>/dev/null | head -10
    ((VIOLATIONS++))
fi
echo ""

# Check 2: TODO/FIXME/XXX in critical paths only
echo "🔍 Check 2: Detecting TODO/FIXME/XXX in critical paths..."
TODO_FOUND=0
for path in "${CRITICAL_CHECK_PATHS[@]}"; do
    if [ -d "$path" ]; then
        if grep -r "${EXCLUDE_ARGS[@]}" \
            -nE "(TODO|FIXME|XXX)" \
            --include="*.py" \
            "$path" 2>/dev/null | \
            grep -vE '(^|/)(tests?/|.*test_.*\.py:)' | \
            grep -vE 'TODO-ALLOW\(PR-[0-9]+\)' \
            > /tmp/gate0_todo_$$.txt 2>/dev/null; then
            if [ -s /tmp/gate0_todo_$$.txt ]; then
                TODO_FOUND=1
            fi
        fi
    fi
done

if [ $TODO_FOUND -eq 1 ]; then
    echo -e "${RED}❌ FAIL: Found TODO/FIXME in critical paths${NC}"
    cat /tmp/gate0_todo_$$.txt 2>/dev/null | head -10
    ((VIOLATIONS++))
else
    echo -e "${GREEN}✓ No TODO/FIXME in critical paths${NC}"
fi
echo ""

# Check 3: "raise NotImplementedError" in critical paths
echo "🔍 Check 3: Detecting NotImplementedError stubs..."
NOTIMPL_FOUND=0
for path in "${CRITICAL_CHECK_PATHS[@]}"; do
    if [ -d "$path" ]; then
        if grep -r "${EXCLUDE_ARGS[@]}" \
            -E "raise\s+NotImplementedError" \
            --include="*.py" \
            "$path" 2>/dev/null | \
            grep -v "test_" | \
            grep -v "tests/" | \
            grep -v "def _.*_impl" | \
            grep -v "class.*ABC" | \
            grep -v "@abstractmethod" | \
            grep -v "base_engine.py" > /tmp/gate0_notimpl_$$.txt 2>/dev/null; then  # Skip base_engine.py (abstract base)
            if [ -s /tmp/gate0_notimpl_$$.txt ]; then
                NOTIMPL_FOUND=1
            fi
        fi
    fi
done

if [ $NOTIMPL_FOUND -eq 1 ]; then
    echo -e "${RED}❌ FAIL: Found NotImplementedError in critical paths${NC}"
    cat /tmp/gate0_notimpl_$$.txt 2>/dev/null | head -10
    ((VIOLATIONS++))
else
    echo -e "${GREEN}✓ No NotImplementedError in critical paths${NC}"
fi
echo ""

# Check 4: "return {}" or "return None" as sole body in critical paths
echo "🔍 Check 4: Detecting empty return stubs..."
EMPTY_RETURN_FOUND=0
for path in "${CRITICAL_CHECK_PATHS[@]}"; do
    if [ -d "$path" ]; then
        if grep -r "${EXCLUDE_ARGS[@]}" \
            -E "^\s+return\s+(\{\}|None)\s*$" \
            --include="*.py" \
            "$path" 2>/dev/null | \
            grep -v "test_" | \
            grep -v "tests/" | \
            grep -v "Optional" | \
            head -10 > /tmp/gate0_empty_return_$$.txt 2>/dev/null; then
            if [ -s /tmp/gate0_empty_return_$$.txt ]; then
                EMPTY_RETURN_FOUND=1
            fi
        fi
    fi
done

if [ $EMPTY_RETURN_FOUND -eq 1 ]; then
    echo -e "${YELLOW}⚠️  WARNING: Found empty return stubs${NC}"
    cat /tmp/gate0_empty_return_$$.txt 2>/dev/null | head -5
else
    echo -e "${GREEN}✓ No empty return stubs${NC}"
fi
echo ""

# Check 5: Secrets patterns
echo "🔍 Check 5: Detecting hardcodes & secrets (Python scanner)..."
cd "${PROJECT_ROOT}"
if python3 scripts/ci_check_hardcodes.py > /tmp/gate0_hardcodes.txt 2>&1; then
    echo -e "${GREEN}✓ No hardcodes or secrets detected${NC}"
else
    echo -e "${RED}❌ CRITICAL: Hardcoded values found:${NC}"
    cat /tmp/gate0_hardcodes.txt
    ((VIOLATIONS+=10))  # Heavy penalty
fi
echo ""

# Summary
echo "================================================"
if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✅ Gate 0: PASSED${NC}"
    echo "Repository integrity verified."
    exit 0
else
    echo -e "${RED}❌ Gate 0: FAILED${NC}"
    echo "Found $VIOLATIONS violation(s)."
    echo ""
    echo "Fix these issues before merging:"
    echo "1. Remove placeholder 'pass' statements"
    echo "2. Remove inappropriate NotImplementedError"
    echo "3. Remove hardcoded secrets"
    echo "4. Replace empty returns with real implementations"
    exit 1
fi



