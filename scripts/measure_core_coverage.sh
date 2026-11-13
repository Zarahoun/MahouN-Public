#!/bin/bash
#
# Measure Core Production Coverage (excluding experimental modules)
# Usage: ./scripts/measure_core_coverage.sh
#

set -e

REPO_ROOT="/home/haji/Desktop/KingMahouN"
cd "$REPO_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  MAHOUN Core Production Coverage${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Activate venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✓${NC} Virtual environment activated"
else
    echo -e "${YELLOW}⚠${NC} venv not found, using system Python"
fi

# Run core coverage
echo ""
echo -e "${BLUE}Running core production tests...${NC}"
python3 -m pytest tests/ \
    --cov=mahoun.core \
    --cov=mahoun.ledger \
    --cov=mahoun.reasoning \
    --cov=mahoun.graph \
    --cov=mahoun.orchestrator \
    --cov=mahoun.governance \
    --cov=mahoun.security \
    --cov=mahoun.crypto \
    --cov=mahoun.invariants \
    --cov=mahoun.schemas \
    --cov=mahoun.metrics \
    --cov=api \
    --cov-report=term \
    --cov-report=html:htmlcov_core \
    --cov-report=json:coverage_core.json \
    -q --tb=no

echo ""
echo -e "${GREEN}✓${NC} Core coverage measurement complete"
echo -e "  HTML Report: ${BLUE}htmlcov_core/index.html${NC}"
echo -e "  JSON Data:   ${BLUE}coverage_core.json${NC}"
echo ""
