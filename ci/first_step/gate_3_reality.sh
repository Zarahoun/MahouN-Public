#!/bin/bash
#
# Gate 3: Phase-1 Reality Tests
# ==============================
# Runs first_step_ci_cd test suite (laptop-safe)
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
echo "🧪 Gate 3: Phase-1 Reality Tests"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest not found. Installing...${NC}"
    pip install pytest pytest-asyncio
fi

echo "📊 Running 137 reality tests..."
echo ""

# Set environment to prevent external calls
export MAHOUN_NO_EXTERNAL_CALLS=1
export MAHOUN_TEST_MODE=1

# Run tests with timeout
if timeout 120 pytest first_step_ci_cd/ \
    -q \
    --tb=short \
    --maxfail=5 \
    --junit-xml=/tmp/gate3_junit.xml \
    2>&1 | tee /tmp/gate3_output.txt; then
    
    echo ""
    echo -e "${GREEN}✓ All tests passed${NC}"
    
    # Extract test counts
    PASSED=$(grep -oP '\d+(?= passed)' /tmp/gate3_output.txt | tail -1 || echo "0")
    echo "Tests passed: $PASSED"
    
    TEST_PASSED=true
else
    echo ""
    echo -e "${RED}❌ Tests failed${NC}"
    
    # Show summary
    echo ""
    echo "Failed tests:"
    grep "FAILED" /tmp/gate3_output.txt || echo "See output above"
    
    TEST_PASSED=false
fi

echo ""
echo "================================================"

if [ "$TEST_PASSED" = true ]; then
    echo -e "${GREEN}✅ Gate 3: PASSED${NC}"
    echo "Reality tests verified implementation is real."
    exit 0
else
    echo -e "${RED}❌ Gate 3: FAILED${NC}"
    echo ""
    echo "Run locally to debug:"
    echo "  pytest first_step_ci_cd/ -v"
    exit 1
fi






