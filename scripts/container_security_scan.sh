#!/bin/bash
# ============================================================================
# MAHOUN Container Security Scanner - Comprehensive Vulnerability Assessment
# ============================================================================
# Purpose: Multi-tool security scanning for all MAHOUN container images
# Tools: Trivy (vulnerabilities), Grype (packages), Docker Scout (supply chain)
# Compliance: NIST, CIS benchmarks, OWASP container security guidelines
# ============================================================================

set -euo pipefail

# ============================================================================
# Configuration & Constants
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$PROJECT_ROOT/security-scan-results"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

# Container images to scan
declare -a IMAGES=(
    "mahoun/governance-kernel:latest"
    "mahoun/api-server:latest"
    "mahoun/mcp-server:latest"
)

# Security scanning tools
TRIVY_VERSION="0.50.0"
GRYPE_VERSION="0.74.0"

# Exit codes
EXIT_SUCCESS=0
EXIT_VULNERABILITY_FOUND=1
EXIT_CRITICAL_FOUND=2
EXIT_TOOL_ERROR=3

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# Logging Functions
# ============================================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_critical() {
    echo -e "${RED}[CRITICAL]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_header() {
    echo
    echo -e "${PURPLE}============================================================================${NC}"
    echo -e "${PURPLE} $1${NC}"
    echo -e "${PURPLE}============================================================================${NC}"
    echo
}

# ============================================================================
# Utility Functions
# ============================================================================
check_command() {
    local cmd="$1"
    local install_msg="$2"
    
    if ! command -v "$cmd" &> /dev/null; then
        log_error "$cmd is not installed. $install_msg"
        return 1
    fi
    return 0
}

create_results_dir() {
    mkdir -p "$RESULTS_DIR"
    log_info "Results directory: $RESULTS_DIR"
}

cleanup_old_results() {
    # Keep only last 5 scan results
    if [[ -d "$RESULTS_DIR" ]]; then
        find "$RESULTS_DIR" -name "scan-*" -type d | sort -V | head -n -5 | xargs rm -rf 2>/dev/null || true
    fi
}

# ============================================================================
# Tool Installation Functions
# ============================================================================
install_trivy() {
    log_info "Installing Trivy v${TRIVY_VERSION}..."
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        wget -qO- "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" | tar -xzf - -C /tmp
        sudo mv /tmp/trivy /usr/local/bin/
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install aquasecurity/trivy/trivy
    else
        log_error "Unsupported OS for Trivy installation"
        return 1
    fi
    
    log_success "Trivy installed successfully"
}

install_grype() {
    log_info "Installing Grype v${GRYPE_VERSION}..."
    
    curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin "v${GRYPE_VERSION}"
    
    log_success "Grype installed successfully"
}

setup_tools() {
    log_header "Setting Up Security Scanning Tools"
    
    # Check Docker
    if ! check_command "docker" "Please install Docker: https://docs.docker.com/get-docker/"; then
        exit $EXIT_TOOL_ERROR
    fi
    
    # Install Trivy if not present
    if ! check_command "trivy" ""; then
        install_trivy || exit $EXIT_TOOL_ERROR
    fi
    
    # Install Grype if not present  
    if ! check_command "grype" ""; then
        install_grype || exit $EXIT_TOOL_ERROR
    fi
    
    # Update vulnerability databases
    log_info "Updating vulnerability databases..."
    trivy image --download-db-only
    grype db update
    
    log_success "All scanning tools ready"
}

# ============================================================================
# Image Analysis Functions
# ============================================================================
analyze_image_with_trivy() {
    local image="$1"
    local output_dir="$2"
    
    log_info "Running Trivy scan on $image..."
    
    # Comprehensive vulnerability scan
    trivy image \
        --severity HIGH,CRITICAL \
        --format json \
        --output "$output_dir/trivy-vulnerabilities.json" \
        "$image"
    
    # Configuration scan (Dockerfile best practices)
    trivy config \
        --format json \
        --output "$output_dir/trivy-config.json" \
        "$PROJECT_ROOT"
    
    # Secret detection
    trivy fs \
        --scanners secret \
        --format json \
        --output "$output_dir/trivy-secrets.json" \
        "$PROJECT_ROOT"
    
    # Generate human-readable report
    trivy image \
        --severity HIGH,CRITICAL \
        --format table \
        --output "$output_dir/trivy-report.txt" \
        "$image"
    
    # Check for critical vulnerabilities
    local critical_count
    critical_count=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$output_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
    
    local high_count
    high_count=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$output_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
    
    log_info "Trivy results for $image: $critical_count CRITICAL, $high_count HIGH vulnerabilities"
    
    # Return exit code based on findings
    if [[ "$critical_count" -gt 0 ]]; then
        return $EXIT_CRITICAL_FOUND
    elif [[ "$high_count" -gt 0 ]]; then
        return $EXIT_VULNERABILITY_FOUND
    else
        return $EXIT_SUCCESS
    fi
}

analyze_image_with_grype() {
    local image="$1"
    local output_dir="$2"
    
    log_info "Running Grype scan on $image..."
    
    # Package vulnerability scan
    grype "$image" \
        --scope all-layers \
        --output json \
        --file "$output_dir/grype-vulnerabilities.json"
    
    # Generate human-readable report
    grype "$image" \
        --scope all-layers \
        --output table \
        --file "$output_dir/grype-report.txt"
    
    # Generate SARIF for CI/CD integration
    grype "$image" \
        --scope all-layers \
        --output sarif \
        --file "$output_dir/grype-results.sarif"
    
    # Check severity levels
    local critical_count
    critical_count=$(jq '[.matches[]? | select(.vulnerability.severity == "Critical")] | length' "$output_dir/grype-vulnerabilities.json" 2>/dev/null || echo "0")
    
    local high_count
    high_count=$(jq '[.matches[]? | select(.vulnerability.severity == "High")] | length' "$output_dir/grype-vulnerabilities.json" 2>/dev/null || echo "0")
    
    log_info "Grype results for $image: $critical_count Critical, $high_count High vulnerabilities"
    
    if [[ "$critical_count" -gt 0 ]]; then
        return $EXIT_CRITICAL_FOUND
    elif [[ "$high_count" -gt 0 ]]; then
        return $EXIT_VULNERABILITY_FOUND
    else
        return $EXIT_SUCCESS
    fi
}

analyze_docker_best_practices() {
    local image="$1"
    local output_dir="$2"
    
    log_info "Analyzing Docker best practices for $image..."
    
    # Extract dockerfile from image history
    docker history --no-trunc --format "table {{.CreatedBy}}" "$image" > "$output_dir/dockerfile-history.txt"
    
    # Analyze image layers
    docker inspect "$image" > "$output_dir/image-inspect.json"
    
    # Check image size
    local image_size
    image_size=$(docker images "$image" --format "table {{.Size}}" | tail -1)
    echo "Image size: $image_size" >> "$output_dir/image-analysis.txt"
    
    # Security context analysis
    local user
    user=$(docker inspect "$image" --format='{{.Config.User}}' 2>/dev/null || echo "root")
    echo "User context: $user" >> "$output_dir/image-analysis.txt"
    
    # Exposed ports
    local ports
    ports=$(docker inspect "$image" --format='{{range $p, $conf := .Config.ExposedPorts}}{{$p}} {{end}}' 2>/dev/null || echo "none")
    echo "Exposed ports: $ports" >> "$output_dir/image-analysis.txt"
    
    # Volume mounts
    local volumes
    volumes=$(docker inspect "$image" --format='{{range $v := .Config.Volumes}}{{$v}} {{end}}' 2>/dev/null || echo "none")
    echo "Declared volumes: $volumes" >> "$output_dir/image-analysis.txt"
    
    log_success "Docker analysis completed for $image"
}

# ============================================================================
# Security Policy Validation
# ============================================================================
validate_security_policies() {
    local image="$1"
    local output_dir="$2"
    
    log_info "Validating security policies for $image..."
    
    local policy_violations=0
    local policy_report="$output_dir/security-policy-report.txt"
    
    echo "MAHOUN Container Security Policy Validation Report" > "$policy_report"
    echo "=================================================" >> "$policy_report"
    echo "Image: $image" >> "$policy_report"
    echo "Timestamp: $(date)" >> "$policy_report"
    echo >> "$policy_report"
    
    # Check 1: Non-root user
    local user
    user=$(docker inspect "$image" --format='{{.Config.User}}' 2>/dev/null || echo "")
    
    if [[ -z "$user" || "$user" == "root" || "$user" == "0" ]]; then
        echo "❌ VIOLATION: Container runs as root user" >> "$policy_report"
        ((policy_violations++))
    else
        echo "✅ PASS: Container runs as non-root user ($user)" >> "$policy_report"
    fi
    
    # Check 2: No unnecessary capabilities
    local caps
    caps=$(docker inspect "$image" --format='{{.HostConfig.CapAdd}}' 2>/dev/null || echo "[]")
    
    if [[ "$caps" != "[]" && "$caps" != "<no value>" ]]; then
        echo "⚠️  WARNING: Container has additional capabilities: $caps" >> "$policy_report"
    else
        echo "✅ PASS: No additional capabilities granted" >> "$policy_report"
    fi
    
    # Check 3: Read-only root filesystem capability
    local readonly_check
    readonly_check=$(docker inspect "$image" --format='{{.HostConfig.ReadonlyRootfs}}' 2>/dev/null || echo "false")
    
    if [[ "$readonly_check" == "false" ]]; then
        echo "⚠️  INFO: Container filesystem not marked read-only (may be runtime configuration)" >> "$policy_report"
    else
        echo "✅ PASS: Root filesystem is read-only" >> "$policy_report"
    fi
    
    # Check 4: Health check defined
    local healthcheck
    healthcheck=$(docker inspect "$image" --format='{{.Config.Healthcheck.Test}}' 2>/dev/null || echo "")
    
    if [[ -z "$healthcheck" || "$healthcheck" == "<no value>" ]]; then
        echo "⚠️  WARNING: No health check defined" >> "$policy_report"
    else
        echo "✅ PASS: Health check configured" >> "$policy_report"
    fi
    
    # Check 5: Minimal attack surface (small image size)
    local size_mb
    size_mb=$(docker images "$image" --format "{{.Size}}" | sed 's/MB//' | sed 's/GB/000/' | tr -d '.' | head -c 3)
    
    if [[ "$size_mb" -gt 500 ]]; then
        echo "⚠️  WARNING: Large image size (${size_mb}MB) - consider optimization" >> "$policy_report"
    else
        echo "✅ PASS: Reasonable image size (${size_mb}MB)" >> "$policy_report"
    fi
    
    echo >> "$policy_report"
    echo "Policy violations: $policy_violations" >> "$policy_report"
    
    log_info "Security policy validation completed: $policy_violations violations"
    
    return $policy_violations
}

# ============================================================================
# Comprehensive Image Scanning
# ============================================================================
scan_image() {
    local image="$1"
    local scan_dir="$RESULTS_DIR/scan-$TIMESTAMP/$(echo "$image" | tr '/' '_' | tr ':' '_')"
    
    log_header "Scanning Container Image: $image"
    
    # Create output directory
    mkdir -p "$scan_dir"
    
    # Check if image exists
    if ! docker image inspect "$image" &>/dev/null; then
        log_error "Image $image not found. Building it first..."
        return $EXIT_TOOL_ERROR
    fi
    
    local overall_result=$EXIT_SUCCESS
    
    # Run Trivy analysis
    if analyze_image_with_trivy "$image" "$scan_dir"; then
        log_success "Trivy scan completed - no critical issues"
    else
        local trivy_result=$?
        log_warning "Trivy found vulnerabilities (exit code: $trivy_result)"
        if [[ $trivy_result -gt $overall_result ]]; then
            overall_result=$trivy_result
        fi
    fi
    
    # Run Grype analysis
    if analyze_image_with_grype "$image" "$scan_dir"; then
        log_success "Grype scan completed - no critical issues"
    else
        local grype_result=$?
        log_warning "Grype found vulnerabilities (exit code: $grype_result)"
        if [[ $grype_result -gt $overall_result ]]; then
            overall_result=$grype_result
        fi
    fi
    
    # Run Docker best practices analysis
    analyze_docker_best_practices "$image" "$scan_dir"
    
    # Validate security policies
    if validate_security_policies "$image" "$scan_dir"; then
        log_success "Security policy validation passed"
    else
        local policy_violations=$?
        log_warning "Security policy violations found: $policy_violations"
    fi
    
    # Generate summary report
    generate_image_summary "$image" "$scan_dir" $overall_result
    
    return $overall_result
}

# ============================================================================
# Report Generation
# ============================================================================
generate_image_summary() {
    local image="$1"
    local scan_dir="$2"
    local result_code="$3"
    
    local summary_file="$scan_dir/scan-summary.txt"
    
    echo "MAHOUN Container Security Scan Summary" > "$summary_file"
    echo "======================================" >> "$summary_file"
    echo "Image: $image" >> "$summary_file"
    echo "Scan Date: $(date)" >> "$summary_file"
    echo "Result Code: $result_code" >> "$summary_file"
    echo >> "$summary_file"
    
    # Trivy summary
    if [[ -f "$scan_dir/trivy-vulnerabilities.json" ]]; then
        local trivy_critical
        local trivy_high
        trivy_critical=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$scan_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
        trivy_high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$scan_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
        
        echo "Trivy Results:" >> "$summary_file"
        echo "  Critical: $trivy_critical" >> "$summary_file"
        echo "  High: $trivy_high" >> "$summary_file"
        echo >> "$summary_file"
    fi
    
    # Grype summary
    if [[ -f "$scan_dir/grype-vulnerabilities.json" ]]; then
        local grype_critical
        local grype_high
        grype_critical=$(jq '[.matches[]? | select(.vulnerability.severity == "Critical")] | length' "$scan_dir/grype-vulnerabilities.json" 2>/dev/null || echo "0")
        grype_high=$(jq '[.matches[]? | select(.vulnerability.severity == "High")] | length' "$scan_dir/grype-vulnerabilities.json" 2>/dev/null || echo "0")
        
        echo "Grype Results:" >> "$summary_file"
        echo "  Critical: $grype_critical" >> "$summary_file"
        echo "  High: $grype_high" >> "$summary_file"
        echo >> "$summary_file"
    fi
    
    # Image analysis
    if [[ -f "$scan_dir/image-analysis.txt" ]]; then
        echo "Image Analysis:" >> "$summary_file"
        cat "$scan_dir/image-analysis.txt" >> "$summary_file"
        echo >> "$summary_file"
    fi
    
    # Overall assessment
    case $result_code in
        $EXIT_SUCCESS)
            echo "✅ OVERALL RESULT: PASS - No critical vulnerabilities found" >> "$summary_file"
            ;;
        $EXIT_VULNERABILITY_FOUND)
            echo "⚠️  OVERALL RESULT: WARNING - High severity vulnerabilities found" >> "$summary_file"
            ;;
        $EXIT_CRITICAL_FOUND)
            echo "❌ OVERALL RESULT: FAIL - Critical vulnerabilities found" >> "$summary_file"
            ;;
        *)
            echo "❓ OVERALL RESULT: UNKNOWN - Scan encountered errors" >> "$summary_file"
            ;;
    esac
    
    log_info "Summary report generated: $summary_file"
}

generate_consolidated_report() {
    local scan_timestamp="$1"
    local consolidated_dir="$RESULTS_DIR/scan-$scan_timestamp"
    local consolidated_report="$consolidated_dir/consolidated-security-report.md"
    
    log_header "Generating Consolidated Security Report"
    
    mkdir -p "$consolidated_dir"
    
    cat > "$consolidated_report" << EOF
# MAHOUN Container Security Assessment Report

**Scan Date:** $(date)  
**Scan ID:** $scan_timestamp  
**Scanner Version:** Trivy v${TRIVY_VERSION}, Grype v${GRYPE_VERSION}

## Executive Summary

This report provides a comprehensive security assessment of all MAHOUN container images, including vulnerability analysis, configuration review, and security policy compliance.

## Scanned Images

EOF
    
    local overall_status="PASS"
    local total_critical=0
    local total_high=0
    
    for image in "${IMAGES[@]}"; do
        local image_safe
        image_safe=$(echo "$image" | tr '/' '_' | tr ':' '_')
        local image_dir="$consolidated_dir/$image_safe"
        
        if [[ -d "$image_dir" ]]; then
            echo "### $image" >> "$consolidated_report"
            echo >> "$consolidated_report"
            
            # Include summary if available
            if [[ -f "$image_dir/scan-summary.txt" ]]; then
                echo '```' >> "$consolidated_report"
                cat "$image_dir/scan-summary.txt" >> "$consolidated_report"
                echo '```' >> "$consolidated_report"
                echo >> "$consolidated_report"
            fi
            
            # Count vulnerabilities for overall stats
            if [[ -f "$image_dir/trivy-vulnerabilities.json" ]]; then
                local img_critical
                local img_high
                img_critical=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$image_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
                img_high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$image_dir/trivy-vulnerabilities.json" 2>/dev/null || echo "0")
                
                total_critical=$((total_critical + img_critical))
                total_high=$((total_high + img_high))
                
                if [[ $img_critical -gt 0 ]]; then
                    overall_status="CRITICAL"
                elif [[ $img_high -gt 0 && "$overall_status" != "CRITICAL" ]]; then
                    overall_status="HIGH"
                fi
            fi
        fi
    done
    
    # Add overall statistics
    cat >> "$consolidated_report" << EOF

## Overall Assessment

- **Status:** $overall_status
- **Total Critical Vulnerabilities:** $total_critical
- **Total High Vulnerabilities:** $total_high
- **Images Scanned:** ${#IMAGES[@]}

## Recommendations

EOF
    
    if [[ $total_critical -gt 0 ]]; then
        cat >> "$consolidated_report" << EOF
🚨 **CRITICAL ACTION REQUIRED**

Critical vulnerabilities were found that must be addressed before production deployment:

1. Review all critical findings in individual scan reports
2. Update base images to latest patched versions  
3. Update vulnerable packages to patched versions
4. Re-scan after remediation
5. Consider alternative packages if no patches available

EOF
    elif [[ $total_high -gt 0 ]]; then
        cat >> "$consolidated_report" << EOF
⚠️ **HIGH PRIORITY REMEDIATION**

High severity vulnerabilities should be addressed:

1. Review high severity findings
2. Plan update schedule for vulnerable components
3. Implement compensating controls where immediate patching isn't possible
4. Monitor for patches and update as soon as available

EOF
    else
        cat >> "$consolidated_report" << EOF
✅ **SECURITY POSTURE GOOD**

No critical or high severity vulnerabilities found. Continue monitoring:

1. Regularly update base images
2. Keep dependencies current
3. Re-scan weekly or after any changes
4. Monitor security advisories for used components

EOF
    fi
    
    cat >> "$consolidated_report" << EOF

## Scan Details

Individual scan results are available in the following directories:

EOF
    
    for image in "${IMAGES[@]}"; do
        local image_safe
        image_safe=$(echo "$image" | tr '/' '_' | tr ':' '_')
        echo "- \`$image\`: \`$consolidated_dir/$image_safe/\`" >> "$consolidated_report"
    done
    
    cat >> "$consolidated_report" << EOF

## Files Generated

- **Trivy Reports:** \`trivy-*.json\`, \`trivy-*.txt\`
- **Grype Reports:** \`grype-*.json\`, \`grype-*.txt\`, \`grype-*.sarif\`
- **Docker Analysis:** \`image-*.txt\`, \`dockerfile-history.txt\`
- **Policy Validation:** \`security-policy-report.txt\`
- **Summary:** \`scan-summary.txt\`

---
*Generated by MAHOUN Container Security Scanner*
EOF
    
    log_success "Consolidated report generated: $consolidated_report"
    
    # Also create a CI-friendly summary
    local ci_summary="$consolidated_dir/ci-summary.json"
    cat > "$ci_summary" << EOF
{
  "timestamp": "$scan_timestamp",
  "overall_status": "$overall_status",
  "total_critical": $total_critical,
  "total_high": $total_high,
  "images_scanned": ${#IMAGES[@]},
  "scan_passed": $([ "$overall_status" = "PASS" ] && echo "true" || echo "false")
}
EOF
    
    return $([ "$overall_status" = "PASS" ] && echo $EXIT_SUCCESS || echo $EXIT_CRITICAL_FOUND)
}

# ============================================================================
# Main Execution Flow
# ============================================================================
main() {
    log_header "MAHOUN Container Security Scanner"
    
    # Setup
    create_results_dir
    cleanup_old_results
    setup_tools
    
    local overall_exit_code=$EXIT_SUCCESS
    
    # Scan each image
    for image in "${IMAGES[@]}"; do
        if scan_image "$image"; then
            log_success "✅ $image - Security scan passed"
        else
            local scan_result=$?
            case $scan_result in
                $EXIT_VULNERABILITY_FOUND)
                    log_warning "⚠️ $image - High severity vulnerabilities found"
                    ;;
                $EXIT_CRITICAL_FOUND)
                    log_critical "❌ $image - Critical vulnerabilities found"
                    ;;
                $EXIT_TOOL_ERROR)
                    log_error "🔧 $image - Scan tool error"
                    ;;
                *)
                    log_error "❓ $image - Unknown scan error (code: $scan_result)"
                    ;;
            esac
            
            # Update overall exit code to worst case
            if [[ $scan_result -gt $overall_exit_code ]]; then
                overall_exit_code=$scan_result
            fi
        fi
        echo
    done
    
    # Generate consolidated report
    if generate_consolidated_report "$TIMESTAMP"; then
        log_success "All security assessments completed successfully"
    else
        log_warning "Security issues found - review consolidated report"
    fi
    
    # Final summary
    log_header "Scan Complete"
    case $overall_exit_code in
        $EXIT_SUCCESS)
            log_success "🎉 All images passed security scanning"
            ;;
        $EXIT_VULNERABILITY_FOUND)
            log_warning "⚠️ High severity vulnerabilities found - review required"
            ;;
        $EXIT_CRITICAL_FOUND)
            log_critical "🚨 Critical vulnerabilities found - immediate action required"
            ;;
        $EXIT_TOOL_ERROR)
            log_error "🔧 Tool errors encountered - check logs"
            ;;
    esac
    
    log_info "📁 Results location: $RESULTS_DIR/scan-$TIMESTAMP/"
    log_info "📊 Consolidated report: $RESULTS_DIR/scan-$TIMESTAMP/consolidated-security-report.md"
    
    exit $overall_exit_code
}

# ============================================================================
# Script Entry Point
# ============================================================================
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi