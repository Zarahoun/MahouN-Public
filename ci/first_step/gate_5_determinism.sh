#!/bin/bash
#
# Gate 5: Determinism Proof
# ==========================
# Ensures tests produce identical results on repeated runs
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
echo "🎲 Gate 5: Determinism Proof"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# Set deterministic environment
export PYTHONHASHSEED=0
export MAHOUN_NO_EXTERNAL_CALLS=1
export MAHOUN_TEST_MODE=1

echo "🔄 Running tests (1st run)..."
if pytest first_step_ci_cd/ \
    -q \
    --tb=no \
    --junit-xml=/tmp/gate5_run1.xml \
    > /tmp/gate5_output1.txt 2>&1; then
    RUN1_EXIT=0
else
    RUN1_EXIT=$?
fi

# Extract summary from run 1
RUN1_SUMMARY=$(grep -E "passed|failed|error" /tmp/gate5_output1.txt | tail -1 || echo "")
echo "Run 1 result: $RUN1_SUMMARY"
echo ""

# Small delay to ensure different timestamps
sleep 2

echo "🔄 Running tests (2nd run)..."
if pytest first_step_ci_cd/ \
    -q \
    --tb=no \
    --junit-xml=/tmp/gate5_run2.xml \
    > /tmp/gate5_output2.txt 2>&1; then
    RUN2_EXIT=0
else
    RUN2_EXIT=$?
fi

# Extract summary from run 2
RUN2_SUMMARY=$(grep -E "passed|failed|error" /tmp/gate5_output2.txt | tail -1 || echo "")
echo "Run 2 result: $RUN2_SUMMARY"
echo ""

# Compare exit codes
if [ $RUN1_EXIT -ne $RUN2_EXIT ]; then
    echo -e "${RED}❌ Exit codes differ: $RUN1_EXIT vs $RUN2_EXIT${NC}"
    DETERMINISTIC=false
else
    echo -e "${GREEN}✓ Exit codes match: $RUN1_EXIT${NC}"
    DETERMINISTIC=true
fi

# Compare test counts
RUN1_COUNT=$(grep -oP '\d+(?= passed)' /tmp/gate5_output1.txt | tail -1 || echo "0")
RUN2_COUNT=$(grep -oP '\d+(?= passed)' /tmp/gate5_output2.txt | tail -1 || echo "0")

if [ "$RUN1_COUNT" != "$RUN2_COUNT" ]; then
    echo -e "${RED}❌ Test counts differ: $RUN1_COUNT vs $RUN2_COUNT${NC}"
    DETERMINISTIC=false
else
    echo -e "${GREEN}✓ Test counts match: $RUN1_COUNT${NC}"
fi

# Compare junit XML hashes
if [ -f /tmp/gate5_run1.xml ] && [ -f /tmp/gate5_run2.xml ]; then
    # Remove timestamps from XML before hashing
    sed 's/timestamp="[^"]*"/timestamp=""/g' /tmp/gate5_run1.xml | sed 's/time="[^"]*"/time=""/g' > /tmp/gate5_run1_clean.xml
    sed 's/timestamp="[^"]*"/timestamp=""/g' /tmp/gate5_run2.xml | sed 's/time="[^"]*"/time=""/g' > /tmp/gate5_run2_clean.xml
    
    HASH1=$(md5sum /tmp/gate5_run1_clean.xml | cut -d' ' -f1)
    HASH2=$(md5sum /tmp/gate5_run2_clean.xml | cut -d' ' -f1)
    
    if [ "$HASH1" != "$HASH2" ]; then
        echo -e "${RED}❌ Test results differ (hash mismatch)${NC}"
        echo "   Hash 1: $HASH1"
        echo "   Hash 2: $HASH2"
        
        # Show diff
        echo ""
        echo "Differences:"
        diff /tmp/gate5_run1_clean.xml /tmp/gate5_run2_clean.xml | head -20 || true
        
        DETERMINISTIC=false
    else
        echo -e "${GREEN}✓ Test results identical (hash match)${NC}"
    fi
fi

echo ""
echo "================================================"

if [ "$DETERMINISTIC" = true ] && [ $RUN1_EXIT -eq 0 ]; then
    echo -e "${GREEN}✅ Gate 5: PASSED${NC}"
    echo "Tests are deterministic (identical results on repeated runs)."
    exit 0
else
    echo -e "${RED}❌ Gate 5: FAILED${NC}"
    echo ""
    if [ "$DETERMINISTIC" = false ]; then
        echo "Tests are NON-DETERMINISTIC!"
        echo ""
        echo "Common causes:"
        echo "- Using random.random() without seed"
        echo "- Using time.time() or datetime.now() in assertions"
        echo "- Network calls (should be mocked)"
        echo "- File system dependencies"
        echo "- Dictionary/set iteration order"
        echo ""
        echo "Fix by:"
        echo "- Mock random with fixed seed"
        echo "- Use freezegun for time-based tests"
        echo "- Mock all external calls"
        echo "- Use OrderedDict or sorted()"
    fi
    exit 1
fi






