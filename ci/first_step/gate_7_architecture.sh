#!/bin/bash
#
# Gate 8: Architecture Boundary Enforcement
# ==========================================
# Ensures core modules do not import from non-core modules
# Enforces architectural boundaries defined in manifests
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
echo "🏛️  Gate 7: Architecture Boundary Check"
echo "================================================"
echo ""

# Check if manifests exist
if [ ! -f "${PROJECT_ROOT}/core_manifest.yaml" ]; then
    echo -e "${RED}❌ CRITICAL: core_manifest.yaml not found${NC}"
    echo "Run: Create core_manifest.yaml at project root"
    exit 1
fi

if [ ! -f "${PROJECT_ROOT}/non_core_manifest.yaml" ]; then
    echo -e "${RED}❌ CRITICAL: non_core_manifest.yaml not found${NC}"
    echo "Run: Create non_core_manifest.yaml at project root"
    exit 1
fi

echo "✓ Found architecture manifests"
echo ""

# Check if boundary checker exists
if [ ! -f "${PROJECT_ROOT}/scripts/check_boundaries.py" ]; then
    echo -e "${RED}❌ CRITICAL: scripts/check_boundaries.py not found${NC}"
    echo "Run: Create boundary checker script"
    exit 1
fi

echo "✓ Found boundary checker script"
echo ""

# Run boundary checker
echo "🔍 Scanning core modules for boundary violations..."
echo ""

cd "${PROJECT_ROOT}"

if python3 scripts/check_boundaries.py; then
    echo ""
    echo "================================================"
    echo -e "${GREEN}✅ Gate 7: PASSED${NC}"
    echo "All core modules respect architectural boundaries."
    exit 0
else
    EXIT_CODE=$?
    echo ""
    echo "================================================"
    echo -e "${RED}❌ Gate 7: FAILED${NC}"
    echo ""
    echo "Architecture boundary violations detected!"
    echo ""
    echo "How to fix:"
    echo "1. Review the violations listed above"
    echo "2. Core modules must NOT import from non-core modules"
    echo "3. Use dependency injection or protocols instead"
    echo "4. Move misplaced code to correct module"
    echo ""
    echo "Allowed core modules: reasoning, graph, invariants, schemas, ledger, core"
    echo "Forbidden imports: agents, pipelines, rag, retrieval, mcp, dashboard, etc."
    echo ""
    exit $EXIT_CODE
fi
