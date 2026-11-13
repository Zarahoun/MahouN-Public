#!/bin/bash
#
# Gate 4: Anti-Mock Proof
# ========================
# Verifies implementations are not stubs
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
echo "🔍 Gate 4: Anti-Mock Proof"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

VIOLATIONS=0

# Part 1: Run anti-mock tests
echo "📋 Running anti-mock test suite..."
if pytest first_step_ci_cd/test_5_anti_mock.py -v --tb=short; then
    echo -e "${GREEN}✓ Anti-mock tests passed${NC}"
else
    echo -e "${RED}❌ Anti-mock tests failed${NC}"
    ((VIOLATIONS++))
fi
echo ""

# Part 2: Check module complexity (line counts)
echo "📊 Checking module complexity..."
echo ""

# Configuration file
THRESHOLD_FILE="${SCRIPT_DIR}/complexity_thresholds.json"

# Default thresholds if config doesn't exist
if [ ! -f "$THRESHOLD_FILE" ]; then
    cat > "$THRESHOLD_FILE" << 'EOF'
{
  "mahoun/agents/base_agent.py": 500,
  "mahoun/agents/claim_agent.py": 400,
  "mahoun/reasoning/ultra_reasoning_service.py": 300,
  "output/base_generator.py": 40,
  "output/claim_generator.py": 35
}
EOF
fi

# Check each critical module
check_module_size() {
    local file=$1
    local min_lines=$2
    
    if [ ! -f "$PROJECT_ROOT/$file" ]; then
        echo -e "${YELLOW}⚠️  $file not found (skipping)${NC}"
        return 0
    fi
    
    # Count non-empty, non-comment lines
    actual_lines=$(grep -cve '^\s*$' -ve '^\s*#' "$PROJECT_ROOT/$file" || echo "0")
    
    if [ "$actual_lines" -lt "$min_lines" ]; then
        echo -e "${RED}❌ $file: $actual_lines lines (minimum: $min_lines)${NC}"
        echo "   Module shrank! Possible placeholder replacement."
        return 1
    else
        echo -e "${GREEN}✓ $file: $actual_lines lines (minimum: $min_lines)${NC}"
        return 0
    fi
}

# Check core modules
if ! check_module_size "mahoun/agents/base_agent.py" 400; then
    ((VIOLATIONS++))
fi

if ! check_module_size "mahoun/agents/claim_agent.py" 400; then
    ((VIOLATIONS++))
fi

if ! check_module_size "output/base_generator.py" 40; then
    ((VIOLATIONS++))
fi

if ! check_module_size "output/claim_generator.py" 35; then
    ((VIOLATIONS++))
fi

echo ""

# Part 3: Frontend fabrication / anti-mock extension (Phase B, Round 10).
# Catches the AIChat.tsx fabrication pattern that the Python-only AST walk
# above cannot see. Lives in a companion script for clarity; failures here
# are hard violations, identical in weight to a backend stub.
echo "🎨 Running frontend fabrication check (gate_4b)..."
if bash "${SCRIPT_DIR}/gate_4b_frontend_antimock.sh"; then
    echo -e "${GREEN}✓ Frontend antimock passed${NC}"
else
    echo -e "${RED}❌ Frontend antimock failed${NC}"
    ((VIOLATIONS++))
fi
echo ""

echo "================================================"

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✅ Gate 4: PASSED${NC}"
    echo "Implementations verified as real (not stubs)."
    exit 0
else
    echo -e "${RED}❌ Gate 4: FAILED${NC}"
    echo "Found $VIOLATIONS violation(s)."
    echo ""
    echo "Possible causes:"
    echo "- Code was replaced with placeholders"
    echo "- Module was significantly reduced"
    echo "- Anti-mock tests detected stub patterns"
    echo "- Frontend component contains a fabrication (gate_4b)"
    exit 1
fi






