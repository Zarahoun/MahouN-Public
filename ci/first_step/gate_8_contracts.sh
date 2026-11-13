#!/usr/bin/env bash
# Gate 8: Contract Validation
# 
# This gate ensures all core module contracts are valid and tests pass.
# Contracts define formal input/output specifications for core modules.
#
# Exit codes:
#   0 - All contract tests pass
#   1 - Contract tests failed
#   2 - Contract files missing or invalid

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=================================================="
echo "Gate 8: Contract Validation"
echo "=================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if contract files exist
echo "Step 1: Verifying contract files exist..."
REQUIRED_CONTRACTS=(
    "mahoun/schemas/contracts/core_contracts.py"
    "mahoun/schemas/contracts/reasoning_contracts.py"
    "mahoun/schemas/contracts/graph_contracts.py"
    "mahoun/schemas/contracts/invariants_contracts.py"
    "mahoun/schemas/contracts/schemas_contracts.py"
    "mahoun/schemas/contracts/ledger_contracts.py"
)

MISSING_CONTRACTS=()
for contract in "${REQUIRED_CONTRACTS[@]}"; do
    if [ ! -f "$PROJECT_ROOT/$contract" ]; then
        MISSING_CONTRACTS+=("$contract")
    fi
done

if [ ${#MISSING_CONTRACTS[@]} -ne 0 ]; then
    echo -e "${RED}✗ FAILED: Missing contract files${NC}"
    echo ""
    echo "The following contract files are missing:"
    for contract in "${MISSING_CONTRACTS[@]}"; do
        echo "  - $contract"
    done
    echo ""
    echo "Contract files define formal specifications for core module interfaces."
    echo "All 6 core modules must have contract definitions."
    exit 2
fi

echo -e "${GREEN}✓ All 6 contract files exist${NC}"
echo ""

# Check if contract test files exist
echo "Step 2: Verifying contract test files exist..."
REQUIRED_TESTS=(
    "tests/contracts/test_core_contracts.py"
    "tests/contracts/test_reasoning_contracts.py"
    "tests/contracts/test_graph_contracts.py"
    "tests/contracts/test_invariants_contracts.py"
    "tests/contracts/test_schemas_contracts.py"
    "tests/contracts/test_ledger_contracts.py"
)

MISSING_TESTS=()
for test in "${REQUIRED_TESTS[@]}"; do
    if [ ! -f "$PROJECT_ROOT/$test" ]; then
        MISSING_TESTS+=("$test")
    fi
done

if [ ${#MISSING_TESTS[@]} -ne 0 ]; then
    echo -e "${RED}✗ FAILED: Missing contract test files${NC}"
    echo ""
    echo "The following contract test files are missing:"
    for test in "${MISSING_TESTS[@]}"; do
        echo "  - $test"
    done
    echo ""
    echo "Contract tests validate that contracts are correctly defined."
    echo "All 6 core modules must have contract tests."
    exit 2
fi

echo -e "${GREEN}✓ All 6 contract test files exist${NC}"
echo ""

# Run contract tests
echo "Step 3: Running contract tests..."
echo ""

cd "$PROJECT_ROOT"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run pytest on contract tests only
if python -m pytest tests/contracts/ -v --tb=short --maxfail=5 2>&1 | tee /tmp/gate8_output.txt; then
    echo ""
    echo -e "${GREEN}✓ All contract tests passed${NC}"
    
    # Extract test count
    TEST_COUNT=$(grep -oP '\d+(?= passed)' /tmp/gate8_output.txt | tail -1 || echo "unknown")
    echo ""
    echo "Summary:"
    echo "  - Contract files: 6/6 present"
    echo "  - Contract tests: 6/6 present"
    echo "  - Tests passed: $TEST_COUNT"
    echo ""
    echo -e "${GREEN}=================================================="
    echo "Gate 8: PASSED ✓"
    echo "==================================================${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Contract tests failed${NC}"
    echo ""
    echo "Contract tests validate that core module interfaces are correctly defined."
    echo "Failures indicate:"
    echo "  - Contract schema validation errors"
    echo "  - Missing required fields in contracts"
    echo "  - Invalid field validators"
    echo "  - Contract immutability violations"
    echo ""
    echo "To fix:"
    echo "  1. Review the test output above"
    echo "  2. Check the failing contract file"
    echo "  3. Ensure all contracts use Pydantic v2 (ConfigDict)"
    echo "  4. Verify field validators are correct"
    echo "  5. Run: python -m pytest tests/contracts/ -v"
    echo ""
    echo -e "${RED}=================================================="
    echo "Gate 8: FAILED ✗"
    echo "==================================================${NC}"
    exit 1
fi
