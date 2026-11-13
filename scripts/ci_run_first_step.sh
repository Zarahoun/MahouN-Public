#!/bin/bash
#
# CI Runner: First Step (All Mandatory Gates)
# ============================================
# Runs Gates 0-6 in sequence
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CI_DIR="${PROJECT_ROOT}/ci/first_step"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Start timer
START_TIME=$(date +%s)

echo -e "${BLUE}"
echo "================================================"
echo "🔒 MAHOUN Heavy Lock - First Step CI"
echo "================================================"
echo -e "${NC}"
echo ""

# Track results
GATES_PASSED=0
GATES_FAILED=0
declare -A GATE_RESULTS
declare -A GATE_DURATIONS

run_gate() {
    local gate_num=$1
    local gate_name=$2
    local gate_script=$3
    
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Gate $gate_num: $gate_name${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    gate_start=$(date +%s)
    
    if bash "$gate_script"; then
        gate_end=$(date +%s)
        gate_duration=$((gate_end - gate_start))
        
        GATE_RESULTS[$gate_num]="PASSED"
        GATE_DURATIONS[$gate_num]=$gate_duration
        ((GATES_PASSED++))
        
        echo ""
        echo -e "${GREEN}✅ Gate $gate_num PASSED (${gate_duration}s)${NC}"
        return 0
    else
        gate_end=$(date +%s)
        gate_duration=$((gate_end - gate_start))
        
        GATE_RESULTS[$gate_num]="FAILED"
        GATE_DURATIONS[$gate_num]=$gate_duration
        ((GATES_FAILED++))
        
        echo ""
        echo -e "${RED}❌ Gate $gate_num FAILED (${gate_duration}s)${NC}"
        return 1
    fi
}

# Run all gates
CONTINUE=true

if [ "$CONTINUE" = true ]; then
    if ! run_gate 0 "Repo Integrity" "${CI_DIR}/gate_0_integrity.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 1 "Format/Lint" "${CI_DIR}/gate_1_lint.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 2 "Type Safety" "${CI_DIR}/gate_2_types.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 3 "Phase-1 Reality Tests" "${CI_DIR}/gate_3_reality.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 4 "Anti-Mock Proof" "${CI_DIR}/gate_4_antimock.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 5 "Determinism Proof" "${CI_DIR}/gate_5_determinism.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    if ! run_gate 6 "Artifact + Traceability" "${CI_DIR}/gate_6_artifacts.sh"; then
        CONTINUE=false
    fi
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    run_gate 7 "Architecture Boundaries" "${CI_DIR}/gate_7_architecture.sh"
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    run_gate 8 "Contract Validation" "${CI_DIR}/gate_8_contracts.sh"
    echo ""
fi

if [ "$CONTINUE" = true ]; then
    run_gate 9 "Governance Validation" "${CI_DIR}/gate_9_governance.sh"
    echo ""
fi

# End timer
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

# Summary
echo -e "${BLUE}"
echo "================================================"
echo "📊 CI SUMMARY"
echo "================================================"
echo -e "${NC}"
echo ""

# Show results table
echo "Gate Results:"
echo "----------------------------------------"
for gate in 0 1 2 3 4 5 6 7 8 9; do
    result=${GATE_RESULTS[$gate]:-"SKIPPED"}
    duration=${GATE_DURATIONS[$gate]:-"0"}
    
    if [ "$result" = "PASSED" ]; then
        echo -e "  Gate $gate: ${GREEN}✅ PASSED${NC} (${duration}s)"
    elif [ "$result" = "FAILED" ]; then
        echo -e "  Gate $gate: ${RED}❌ FAILED${NC} (${duration}s)"
    else
        echo -e "  Gate $gate: ${YELLOW}⏭️  SKIPPED${NC}"
    fi
done
echo "----------------------------------------"
echo ""

echo "Statistics:"
echo "  Passed: $GATES_PASSED"
echo "  Failed: $GATES_FAILED"
echo "  Total Duration: ${TOTAL_DURATION}s"
echo ""

# Final verdict
if [ $GATES_FAILED -eq 0 ]; then
    echo -e "${GREEN}"
    echo "================================================"
    echo "✅ ALL GATES PASSED - READY TO MERGE"
    echo "================================================"
    echo -e "${NC}"
    exit 0
else
    echo -e "${RED}"
    echo "================================================"
    echo "❌ $GATES_FAILED GATE(S) FAILED - FIX BEFORE MERGE"
    echo "================================================"
    echo -e "${NC}"
    exit 1
fi






