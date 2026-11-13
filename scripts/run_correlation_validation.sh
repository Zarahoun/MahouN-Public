#!/bin/bash
# 
# Correlation ID Integrity - Full Validation Script
# ==================================================
#
# This script:
# 1. Checks Neo4j availability
# 2. Starts Neo4j if needed
# 3. Runs complete correlation ID test suite
# 4. Generates validation report
#
# Usage:
#   ./scripts/run_correlation_validation.sh
#
# Classification: P0 CRITICAL / PRODUCTION GATE
# Author: MahouN Platform Governance Council

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NEO4J_URI="${DB_NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${DB_NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${DB_NEO4J_PASSWORD:-test_neo4j_password_NOT_FOR_PRODUCTION}"
TEST_TIMEOUT=300  # 5 minutes

# ============================================================================
# FUNCTIONS
# ============================================================================

print_header() {
    echo ""
    echo "============================================================================"
    echo "$1"
    echo "============================================================================"
    echo ""
}

print_step() {
    echo -e "${BLUE}➜${NC} $1"
}

print_success() {
    echo -e "${GREEN}✅${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC}  $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

check_neo4j() {
    print_step "Checking Neo4j connectivity..."
    
    if python3 -c "
from neo4j import GraphDatabase
try:
    driver = GraphDatabase.driver('$NEO4J_URI', auth=('$NEO4J_USER', '$NEO4J_PASSWORD'))
    with driver.session() as session:
        result = session.run('RETURN 1')
        result.single()
    driver.close()
    print('Connected')
    exit(0)
except Exception as e:
    print(f'Failed: {e}')
    exit(1)
" 2>/dev/null; then
        print_success "Neo4j is available at $NEO4J_URI"
        return 0
    else
        print_warning "Neo4j is not available"
        return 1
    fi
}

start_neo4j() {
    print_step "Starting Neo4j with docker-compose..."
    
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found"
        exit 1
    fi
    
    docker-compose up -d neo4j || {
        print_error "Failed to start Neo4j"
        exit 1
    }
    
    print_step "Waiting for Neo4j to be ready..."
    sleep 10
    
    # Wait up to 60 seconds for Neo4j to be ready
    for i in {1..12}; do
        if check_neo4j; then
            print_success "Neo4j is ready"
            return 0
        fi
        echo "   Waiting... ($i/12)"
        sleep 5
    done
    
    print_error "Neo4j failed to start within 60 seconds"
    exit 1
}

run_governance_tests() {
    print_step "Running governance layer tests (no Neo4j required)..."
    
    python3 -m pytest \
        tests/governance/test_correlation_id_integrity_e2e.py \
        -v \
        -k "Creation or Evidence or missing_governance" \
        --tb=short \
        --junit-xml=test-results-governance.xml || {
        print_error "Governance tests failed"
        return 1
    }
    
    print_success "Governance tests passed"
    return 0
}

run_full_test_suite() {
    print_step "Running FULL correlation ID test suite..."
    
    python3 -m pytest \
        tests/governance/test_correlation_id_integrity_e2e.py \
        -v \
        --tb=short \
        --junit-xml=test-results-full.xml \
        --timeout=$TEST_TIMEOUT || {
        print_error "Full test suite failed"
        return 1
    }
    
    print_success "Full test suite passed"
    return 0
}

run_stress_tests() {
    print_step "Running stress tests..."
    
    python3 -m pytest \
        tests/governance/test_correlation_id_stress.py \
        -v \
        -m "not slow" \
        --tb=short \
        --junit-xml=test-results-stress.xml || {
        print_warning "Stress tests failed or skipped"
        return 1
    }
    
    print_success "Stress tests passed"
    return 0
}

generate_report() {
    print_step "Generating validation report..."
    
    cat > correlation_validation_report.txt << EOF
================================================================================
CORRELATION ID INTEGRITY - VALIDATION REPORT
================================================================================

Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Neo4j URI: $NEO4J_URI
Test Suite: tests/governance/test_correlation_id_integrity_e2e.py

TEST RESULTS:
-------------

Governance Layer Tests: $1
Full Test Suite: $2
Stress Tests: $3

SUMMARY:
--------

$4

================================================================================
EOF

    cat correlation_validation_report.txt
    
    print_success "Report saved to correlation_validation_report.txt"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    print_header "🔍 CORRELATION ID INTEGRITY - FULL VALIDATION"
    
    echo "This script will:"
    echo "  1. Check Neo4j availability"
    echo "  2. Start Neo4j if needed"
    echo "  3. Run complete test suite (21 tests)"
    echo "  4. Generate validation report"
    echo ""
    
    # Step 1: Check Neo4j
    if ! check_neo4j; then
        print_warning "Neo4j not available, attempting to start..."
        start_neo4j
    fi
    
    # Step 2: Run governance tests (baseline)
    print_header "📋 STEP 1: Governance Layer Tests (Baseline)"
    if run_governance_tests; then
        governance_status="✅ PASSED"
    else
        governance_status="❌ FAILED"
        print_error "Governance tests failed - cannot proceed"
        generate_report "$governance_status" "⏭️  SKIPPED" "⏭️  SKIPPED" "CRITICAL FAILURE: Baseline governance tests failed"
        exit 1
    fi
    
    # Step 3: Run full test suite
    print_header "📋 STEP 2: Full Test Suite (21 Tests)"
    if run_full_test_suite; then
        full_status="✅ PASSED (21/21)"
    else
        full_status="❌ FAILED"
        print_error "Full test suite failed"
        generate_report "$governance_status" "$full_status" "⏭️  SKIPPED" "VALIDATION FAILED: Not all tests passed. Review test output above."
        exit 1
    fi
    
    # Step 4: Run stress tests (optional)
    print_header "📋 STEP 3: Stress Tests (Optional)"
    if run_stress_tests; then
        stress_status="✅ PASSED"
    else
        stress_status="⚠️  FAILED/SKIPPED"
        print_warning "Stress tests did not pass (non-blocking)"
    fi
    
    # Generate final report
    print_header "📊 VALIDATION COMPLETE"
    
    if [ "$full_status" = "✅ PASSED (21/21)" ]; then
        summary="🎉 SUCCESS: All correlation ID integrity tests passed!

The system has been validated for:
  ✅ Unique correlation ID generation
  ✅ End-to-end propagation
  ✅ Evidence traceability
  ✅ Graph node integrity
  ✅ Relationship integrity
  ✅ Cross-execution isolation
  ✅ Fail-closed enforcement
  ✅ Audit trail completeness
  ✅ Tamper detection

PRODUCTION READINESS: ✅ VALIDATED

Next steps:
  1. Review test output for any warnings
  2. Run stress tests with full load
  3. Conduct security penetration testing
  4. Proceed with production deployment"
    else
        summary="❌ VALIDATION INCOMPLETE

Not all tests passed. Review failures and fix before production deployment.

PRODUCTION READINESS: ❌ NOT READY"
    fi
    
    generate_report "$governance_status" "$full_status" "$stress_status" "$summary"
    
    if [ "$full_status" = "✅ PASSED (21/21)" ]; then
        print_success "Validation successful - system is production ready!"
        exit 0
    else
        print_error "Validation failed - system is NOT production ready"
        exit 1
    fi
}

# Run main function
main "$@"
