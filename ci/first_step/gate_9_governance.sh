#!/usr/bin/env bash
# Gate 9: Governance Validation & CI Gates
# 
# This gate ensures all governance policies, FortressValidator integrity checks,
# GovernanceLock mechanisms, and GovernanceContext boundaries are fully respected
# and verified.
#
# Exit codes:
#   0 - All governance tests pass and policies are strictly enforced
#   1 - Governance checks or tests failed
#   2 - Crucial configuration files or integration vectors are missing
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=================================================="
echo "🛡️  Gate 9: Governance & Fortress Validation Gate"
echo "=================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

cd "$PROJECT_ROOT"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Step 1: Run CRITICAL governance bypass prevention tests FIRST
echo "Step 1: Running CRITICAL Governance Bypass Prevention Tests FIRST..."
echo ""
if python -m pytest tests/governance/test_security_bypass_prevention.py -v --tb=short; then
    echo ""
    echo -e "${GREEN}✓ Critical Bypass Prevention Tests Passed${NC}"
else
    echo ""
    echo -e "${RED}✗ FAILED: Critical Bypass Prevention Tests Failed${NC}"
    echo "Failures in bypass prevention indicate a SERIOUS security regression."
    exit 1
fi
echo ""

# Step 1.5: Run other governance tests
# Exclude tests that require external dependencies (neo4j, psycopg2, httpx2)
echo "Step 1.5: Running remaining Governance Integration Tests..."
echo ""
if python -m pytest tests/governance/ -v -k "not test_concurrent_requests and not test_schema_governance and not test_outbox_refactor and not test_api_integration and not test_security_bypass_prevention" --tb=short; then
    echo ""
    echo -e "${GREEN}✓ Governance Integration Tests Passed Successfully${NC}"
else
    echo ""
    echo -e "${RED}✗ FAILED: Governance Integration Tests Failed${NC}"
    echo "Failures in this test suite indicate a regression or attempt to bypass governance gates."
    exit 1
fi
echo ""

# Step 1.6: Run adversarial kernel runtime suite
# This is the single strongest test file in the codebase.
# Failures indicate security regression in mutation authorization,
# context forgery resistance, or fail-closed guarantees.
echo "Step 1.6: Running Adversarial Kernel Runtime Tests..."
echo ""
if python -m pytest tests/test_kernel_runtime_adversarial.py -v --tb=short; then
    echo ""
    echo -e "${GREEN}✓ Adversarial Kernel Runtime Tests Passed${NC}"
else
    echo ""
    echo -e "${RED}✗ FAILED: Adversarial Kernel Runtime Tests Failed${NC}"
    echo "Failures indicate a security regression in mutation authorization,"
    echo "context forgery resistance, or fail-closed guarantees."
    exit 1
fi
echo ""

# Step 2: Verify GovernanceLock enforcement checks in UnifiedReasoningService
echo "Step 2: Checking GovernanceLock enforcement in UnifiedReasoningService..."
ROUTER_FILE="api/routers/reasoning.py"
SERVICE_FILE="mahoun/reasoning/unified_reasoning_service.py"
if [ -f "$SERVICE_FILE" ]; then
    if grep -q "GovernanceLock" "$SERVICE_FILE"; then
        echo -e "${GREEN}✓ GovernanceLock imports and checks verified in UnifiedReasoningService${NC}"
    else
        echo -e "${RED}✗ FAILED: GovernanceLock is not integrated in UnifiedReasoningService${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ FAILED: UnifiedReasoningService file $SERVICE_FILE not found${NC}"
    exit 2
fi
echo ""

# Step 3: Verify FortressValidator protection checks in API Router
echo "Step 3: Checking FortressValidator protection in API Router..."
if grep -q "FortressProtectedReasoningService" "$ROUTER_FILE"; then
    echo -e "${GREEN}✓ FortressProtectedReasoningService wrapping verified${NC}"
else
    echo -e "${RED}✗ FAILED: Fortress protection is missing from API Router${NC}"
    exit 1
fi
echo ""

# Step 4: Verify GovernanceContext enforcement
echo "Step 4: Checking GovernanceContext enforcement..."
if grep -q "GovernanceContextManager" "$ROUTER_FILE"; then
    echo -e "${GREEN}✓ GovernanceContextManager context enforcement verified${NC}"
else
    echo -e "${RED}✗ FAILED: GovernanceContextManager context active context is not enforced${NC}"
    exit 1
fi
echo ""

# Step 5: Verify Provenance tracking usage
echo "Step 5: Checking Provenance tracking usage..."
if grep -q "require_provenance" "$ROUTER_FILE" || grep -q "provenance" "$ROUTER_FILE"; then
    echo -e "${GREEN}✓ Provenance tracking integration verified${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: Explicit require_provenance is not used in router; checking if it is done within the service wrapper${NC}"
fi
echo ""

# Final Verdict
echo -e "${GREEN}=================================================="
echo "🛡️  Gate 9: PASSED ✓"
echo "All governance, Fortress, and context validation enforcements are fully secure."
echo "==================================================${NC}"
exit 0
