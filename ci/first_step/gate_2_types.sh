#!/bin/bash
#
# Gate 2: Type Safety
# ===================
# Enforces type safety with basedpyright/pyright
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================"
echo "🔒 Gate 2: Type Safety Check"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# Check if basedpyright is available, fall back to pyright, then mypy
TYPE_CHECKER=""
if [ -f "venv/bin/basedpyright" ]; then
    TYPE_CHECKER="venv/bin/basedpyright"
elif [ -f "venv/bin/pyright" ]; then
    TYPE_CHECKER="venv/bin/pyright"
elif [ -f "venv/bin/mypy" ]; then
    TYPE_CHECKER="venv/bin/mypy"
elif command -v basedpyright &> /dev/null; then
    TYPE_CHECKER="basedpyright"
elif command -v pyright &> /dev/null; then
    TYPE_CHECKER="pyright"
elif command -v mypy &> /dev/null; then
    TYPE_CHECKER="mypy"
else
    echo -e "${YELLOW}⚠️  No type checker found. Installing mypy inside venv...${NC}"
    venv/bin/pip install mypy
    TYPE_CHECKER="venv/bin/mypy"
fi

echo "📊 Using type checker: $TYPE_CHECKER"
echo ""

# Baseline file
BASELINE_FILE="${PROJECT_ROOT}/ci/mypy/baseline.txt"

if [ "$TYPE_CHECKER" = "mypy" ] || [ "${TYPE_CHECKER##*/}" = "mypy" ]; then
    echo "🔍 Running mypy non-regression check..."
    
    # Run python non-regression script
    if python3 ci/mypy/check_mypy_non_regression.py; then
        echo -e "${GREEN}✓ No new type errors${NC}"
        TYPE_CHECK_PASSED=true
    else
        echo -e "${RED}❌ Type check regression detected${NC}"
        TYPE_CHECK_PASSED=false
    fi
    
elif [ "$TYPE_CHECKER" = "basedpyright" ] || [ "$TYPE_CHECKER" = "pyright" ]; then
    echo "🔍 Running $TYPE_CHECKER..."
    
    # Run pyright
    if $TYPE_CHECKER mahoun/ output/ api/ --project pyproject.toml > /tmp/pyright_output.txt 2>&1; then
        echo -e "${GREEN}✓ No type errors${NC}"
        TYPE_CHECK_PASSED=true
    else
        # Show errors
        echo -e "${RED}❌ Type errors found:${NC}"
        cat /tmp/pyright_output.txt
        TYPE_CHECK_PASSED=false
    fi
fi

echo ""
echo "================================================"

if [ "$TYPE_CHECK_PASSED" = true ]; then
    echo -e "${GREEN}✅ Gate 2: PASSED${NC}"
    echo "Type safety verified."
    exit 0
else
    echo -e "${RED}❌ Gate 2: FAILED${NC}"
    echo ""
    echo "Fix type errors before merging."
    echo "Run locally:"
    echo "  $TYPE_CHECKER mahoun/ output/ api/"
    exit 1
fi






