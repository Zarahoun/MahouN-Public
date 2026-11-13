#!/bin/bash
#
# Gate 8: Mypy Non-Regression
# ============================
# Ensures no new mypy errors are introduced
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
echo "🔍 Gate 8: Mypy Non-Regression Check"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# Run non-regression check
python3 ci/mypy/check_mypy_non_regression.py

EXIT_CODE=$?

echo ""
echo "================================================"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Gate 8: PASSED${NC}"
    echo "No new mypy errors introduced."
    exit 0
else
    echo -e "${RED}❌ Gate 8: FAILED${NC}"
    echo ""
    echo "New mypy errors detected!"
    echo "Fix errors or update baseline if intentional:"
    echo "  make mypy-baseline"
    exit 1
fi

