#!/bin/bash
#
# Gate 1: Format/Lint
# ===================
# Enforces code style with ruff
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
echo "🎨 Gate 1: Format/Lint Check"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# Check if ruff is installed
RUFF_CMD="ruff"
if [ -f "venv/bin/ruff" ]; then
    RUFF_CMD="venv/bin/ruff"
else
    # Try to find ruff dynamically using pip show in the venv
    LOCATION=$(venv/bin/pip show ruff 2>/dev/null | grep Location | awk '{print $2}')
    if [ -n "$LOCATION" ]; then
        RUFF_BIN_DIR="${LOCATION%/lib/python*/*}"/bin
        if [ -f "$RUFF_BIN_DIR/ruff" ]; then
            RUFF_CMD="$RUFF_BIN_DIR/ruff"
        fi
    fi
fi

if [ "$RUFF_CMD" = "ruff" ] && ! command -v ruff &> /dev/null; then
    echo -e "${RED}❌ ruff not found. Installing inside venv...${NC}"
    venv/bin/pip install ruff
    LOCATION=$(venv/bin/pip show ruff 2>/dev/null | grep Location | awk '{print $2}')
    if [ -n "$LOCATION" ]; then
        RUFF_BIN_DIR="${LOCATION%/lib/python*/*}"/bin
        if [ -f "$RUFF_BIN_DIR/ruff" ]; then
            RUFF_CMD="$RUFF_BIN_DIR/ruff"
        fi
    fi
fi

# Get modified and untracked python files in git workspace, excluding external folders
TRACKED_MODIFIED=$(git diff --name-only | grep '\.py$' || true)
UNTRACKED_FILES=$(git ls-files --others --exclude-standard | grep '\.py$' || true)
MODIFIED_FILES=$(echo -e "${TRACKED_MODIFIED}\n${UNTRACKED_FILES}" | grep -v '^$' | grep -v 'scratch.py' | grep -v 'orchestrator.py' || true)

if [ -n "$MODIFIED_FILES" ]; then
    echo "📋 Running ruff check on modified files..."
    echo "Files to check:"
    echo "$MODIFIED_FILES"
    echo ""
    
    # Run ruff check
    if "$RUFF_CMD" check $MODIFIED_FILES --select E,F,I,UP,N,W --ignore E501,W291,W293,UP042,N818,E402 --output-format=github; then
        echo -e "${GREEN}✓ Lint check passed${NC}"
        LINT_PASSED=true
    else
        echo -e "${RED}❌ Lint check failed${NC}"
        LINT_PASSED=false
    fi

    echo ""
    echo "📝 Running ruff format check..."
    echo ""

    # Check formatting
    if "$RUFF_CMD" format --check $MODIFIED_FILES; then
        echo -e "${GREEN}✓ Format check passed${NC}"
        FORMAT_PASSED=true
    else
        echo -e "${RED}❌ Format check failed${NC}"
        echo ""
        echo "Run this to fix:"
        echo "  $RUFF_CMD format \$MODIFIED_FILES"
        FORMAT_PASSED=false
    fi
else
    echo -e "${GREEN}✓ No modified Python files to lint or format.${NC}"
    LINT_PASSED=true
    FORMAT_PASSED=true
fi

echo ""
echo "================================================"

if [ "$LINT_PASSED" = true ] && [ "$FORMAT_PASSED" = true ]; then
    echo -e "${GREEN}✅ Gate 1: PASSED${NC}"
    echo "Code style is compliant."
    exit 0
else
    echo -e "${RED}❌ Gate 1: FAILED${NC}"
    echo ""
    echo "To fix issues:"
    echo "  $RUFF_CMD check --fix \$MODIFIED_FILES"
    echo "  $RUFF_CMD format \$MODIFIED_FILES"
    exit 1
fi






