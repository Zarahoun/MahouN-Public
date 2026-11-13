#!/usr/bin/env bash
# ============================================================================
# MAHOUN Monitoring Stack Manager - Enterprise Operations
# ============================================================================
# Purpose: Manage complete observability stack lifecycle
# Features: Deploy, health check, backup, restore, upgrade
# ============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MONITORING_DIR="${PROJECT_ROOT}/monitoring"
COMPOSE_FILE="${MONITORING_DIR}/enterprise-monitoring-stack.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "\n${MAGENTA}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║${NC} $1"
    echo -e "${MAGENTA}╚════════════════════════════════════════════════════════════╝${NC}\n"
}

check_prerequisites() {
    log_header "Checking Prerequisites"
    
    local missing=0
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        ((missing++))
    else
        log_success "Docker found: $(docker --version)"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        ((missing++))
    else
        log_success "Docker Compose found"
    fi
    
    # Check required files
    if [[ ! -f "${COMPOSE_FILE}" ]]; then
        log_error "Monitoring stack compose file not found: ${COMPOSE_FILE}"
        ((missing++))
    else
        log_success "Compose file found"
    fi
    
    if [[ $missing -gt 0 ]]; then
        log_error "Missing $missing prerequisite(s). Please install and try again."
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

# =============================================================================
# DEPLOYMENT FUNCTIONS
# =============================================================================
deploy_stack() {
    log_header "Deploying Monitoring Stack"
    
    cd "${MONITORING_DIR}"
    
    # Create necessary directories
    log_info "Creating data directories..."
    mkdir -p prometheus/{data,config,alerts,recording-rules}
    mkdir -p grafana/{data,dashboards,datasources,plugins}
    mkdir -p loki/{data,config}
    mkdir -p tempo/{data,config}
    mkdir -p alertmanager/{data,config,templates}
    
    # Pull images
    log_info "Pulling Docker images..."
    docker-compose -f enterprise-monitoring-stack.yaml pull
    
    # Start services
    log_info "Starting monitoring services..."
    docker-compose -f enterprise-monitoring-stack.yaml up -d
    
    # Wait for services
    log_info "Waiting for services to be ready..."
    sleep 10
    
    check_health
    
    log_success "Monitoring stack deployed successfully!"
    
    # Display access URLs
    echo -e "\n${GREEN}Access URLs:${NC}"
    echo -e "  Prometheus:    ${CYAN}http://localhost:9090${NC}"
    echo -e "  Grafana:       ${CYAN}http://localhost:3000${NC} (admin/admin)"
    echo -e "  Alertmanager:  ${CYAN}http://localhost:9093${NC}"
    echo -e "  Loki:          ${CYAN}http://localhost:3100${NC}"
    echo -e "  Tempo:         ${CYAN}http://localhost:3200${NC}"
}

check_health() {
    log_header "Health Check"
    
    local services=(
        "prometheus:9090/-/healthy"
        "grafana:3000/api/health"
        "loki:3100/ready"
        "tempo:3200/ready"
        "alertmanager:9093/-/healthy"
    )
    
    for service_url in "${services[@]}"; do
        local service="${service_url%%:*}"
        local url="${service_url#*:}"
        
        log_info "Checking ${service}..."
        
        if curl -sf "http://${url}" > /dev/null 2>&1; then
            log_success "${service} is healthy"
        else
            log_error "${service} is not responding"
        fi
    done
}

stop_stack() {
    log_header "Stopping Monitoring Stack"
    
    cd "${MONITORING_DIR}"
    docker-compose -f enterprise-monitoring-stack.yaml stop
    
    log_success "Monitoring stack stopped"
}

start_stack() {
    log_header "Starting Monitoring Stack"
    
    cd "${MONITORING_DIR}"
    docker-compose -f enterprise-monitoring-stack.yaml start
    
    log_success "Monitoring stack started"
    check_health
}

restart_stack() {
    log_header "Restarting Monitoring Stack"
    
    stop_stack
    sleep 5
    start_stack
}

destroy_stack() {
    log_header "Destroying Monitoring Stack"
    
    read -p "$(echo -e ${RED}Warning: This will delete all monitoring data. Continue? [y/N]${NC} )" -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Operation cancelled"
        return 0
    fi
    
    cd "${MONITORING_DIR}"
    docker-compose -f enterprise-monitoring-stack.yaml down -v
    
    log_success "Monitoring stack destroyed"
}

# =============================================================================
# BACKUP & RESTORE
# =============================================================================
backup_stack() {
    log_header "Backing Up Monitoring Stack"
    
    local backup_dir="${PROJECT_ROOT}/backups/monitoring/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "${backup_dir}"
    
    log_info "Backup location: ${backup_dir}"
    
    # Backup Prometheus data
    log_info "Backing up Prometheus..."
    docker run --rm \
        -v mahoun_prometheus_data:/source:ro \
        -v "${backup_dir}:/backup" \
        alpine \
        tar czf /backup/prometheus.tar.gz -C /source .
    
    # Backup Grafana data
    log_info "Backing up Grafana..."
    docker run --rm \
        -v mahoun_grafana_data:/source:ro \
        -v "${backup_dir}:/backup" \
        alpine \
        tar czf /backup/grafana.tar.gz -C /source .
    
    # Backup Loki data
    log_info "Backing up Loki..."
    docker run --rm \
        -v mahoun_loki_data:/source:ro \
        -v "${backup_dir}:/backup" \
        alpine \
        tar czf /backup/loki.tar.gz -C /source .
    
    # Backup configurations
    log_info "Backing up configurations..."
    tar czf "${backup_dir}/configs.tar.gz" -C "${MONITORING_DIR}" \
        prometheus/prometheus.yml \
        prometheus/alerts/ \
        prometheus/recording-rules/ \
        grafana/datasources/ \
        grafana/dashboards/ \
        loki/loki-config.yaml \
        loki/promtail-config.yaml \
        tempo/tempo-config.yaml \
        alertmanager/alertmanager.yml \
        alertmanager/templates/
    
    # Create backup manifest
    cat > "${backup_dir}/manifest.json" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stack_version": "1.0.0",
  "components": [
    "prometheus",
    "grafana",
    "loki",
    "tempo",
    "alertmanager"
  ]
}
EOF
    
    log_success "Backup completed: ${backup_dir}"
}

restore_stack() {
    log_header "Restoring Monitoring Stack"
    
    local backup_dir="$1"
    
    if [[ ! -d "${backup_dir}" ]]; then
        log_error "Backup directory not found: ${backup_dir}"
        exit 1
    fi
    
    log_warn "This will overwrite current monitoring data"
    read -p "$(echo -e ${YELLOW}Continue? [y/N]${NC} )" -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Operation cancelled"
        return 0
    fi
    
    # Stop stack
    stop_stack
    
    # Restore Prometheus
    if [[ -f "${backup_dir}/prometheus.tar.gz" ]]; then
        log_info "Restoring Prometheus..."
        docker run --rm \
            -v mahoun_prometheus_data:/target \
            -v "${backup_dir}:/backup:ro" \
            alpine \
            sh -c "rm -rf /target/* && tar xzf /backup/prometheus.tar.gz -C /target"
    fi
    
    # Restore Grafana
    if [[ -f "${backup_dir}/grafana.tar.gz" ]]; then
        log_info "Restoring Grafana..."
        docker run --rm \
            -v mahoun_grafana_data:/target \
            -v "${backup_dir}:/backup:ro" \
            alpine \
            sh -c "rm -rf /target/* && tar xzf /backup/grafana.tar.gz -C /target"
    fi
    
    # Restore Loki
    if [[ -f "${backup_dir}/loki.tar.gz" ]]; then
        log_info "Restoring Loki..."
        docker run --rm \
            -v mahoun_loki_data:/target \
            -v "${backup_dir}:/backup:ro" \
            alpine \
            sh -c "rm -rf /target/* && tar xzf /backup/loki.tar.gz -C /target"
    fi
    
    # Restore configurations
    if [[ -f "${backup_dir}/configs.tar.gz" ]]; then
        log_info "Restoring configurations..."
        tar xzf "${backup_dir}/configs.tar.gz" -C "${MONITORING_DIR}"
    fi
    
    # Start stack
    start_stack
    
    log_success "Restore completed"
}

# =============================================================================
# STATUS & LOGS
# =============================================================================
show_status() {
    log_header "Monitoring Stack Status"
    
    cd "${MONITORING_DIR}"
    docker-compose -f enterprise-monitoring-stack.yaml ps
}

show_logs() {
    local service="${1:-}"
    
    cd "${MONITORING_DIR}"
    
    if [[ -z "${service}" ]]; then
        docker-compose -f enterprise-monitoring-stack.yaml logs --tail=100 -f
    else
        docker-compose -f enterprise-monitoring-stack.yaml logs --tail=100 -f "${service}"
    fi
}

# =============================================================================
# METRICS & DIAGNOSTICS
# =============================================================================
show_metrics() {
    log_header "Monitoring Stack Metrics"
    
    echo -e "${CYAN}Prometheus Metrics:${NC}"
    curl -s http://localhost:9090/api/v1/query?query=up | jq -r '.data.result[] | "\(.metric.job): \(.value[1])"' 2>/dev/null || echo "Prometheus not accessible"
    
    echo -e "\n${CYAN}Container Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep mahoun
}

run_diagnostics() {
    log_header "Running Diagnostics"
    
    # Check Docker daemon
    log_info "Docker daemon status:"
    docker info | grep -E "Server Version|Operating System|Total Memory"
    
    # Check volumes
    echo -e "\n${CYAN}Monitoring Volumes:${NC}"
    docker volume ls | grep mahoun
    
    # Check networks
    echo -e "\n${CYAN}Monitoring Networks:${NC}"
    docker network ls | grep mahoun
    
    # Check disk usage
    echo -e "\n${CYAN}Disk Usage:${NC}"
    docker system df
    
    # Service health
    echo -e "\n${CYAN}Service Health:${NC}"
    check_health
}

# =============================================================================
# MAIN
# =============================================================================
show_usage() {
    cat <<EOF
${GREEN}MAHOUN Monitoring Stack Manager${NC}

${CYAN}Usage:${NC}
  $0 <command> [options]

${CYAN}Commands:${NC}
  ${GREEN}deploy${NC}              Deploy the monitoring stack
  ${GREEN}start${NC}               Start stopped services
  ${GREEN}stop${NC}                Stop running services
  ${GREEN}restart${NC}             Restart all services
  ${GREEN}destroy${NC}             Remove stack and volumes
  
  ${GREEN}status${NC}              Show service status
  ${GREEN}health${NC}              Check service health
  ${GREEN}logs${NC} [service]      Show logs (all or specific service)
  ${GREEN}metrics${NC}             Show metrics summary
  ${GREEN}diagnostics${NC}         Run full diagnostics
  
  ${GREEN}backup${NC}              Backup monitoring data
  ${GREEN}restore${NC} <dir>       Restore from backup
  
  ${GREEN}help${NC}                Show this help message

${CYAN}Examples:${NC}
  $0 deploy
  $0 logs prometheus
  $0 backup
  $0 restore backups/monitoring/20240616_120000

EOF
}

main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 0
    fi
    
    local command="$1"
    shift
    
    case "${command}" in
        deploy)
            check_prerequisites
            deploy_stack
            ;;
        start)
            start_stack
            ;;
        stop)
            stop_stack
            ;;
        restart)
            restart_stack
            ;;
        destroy)
            destroy_stack
            ;;
        status)
            show_status
            ;;
        health)
            check_health
            ;;
        logs)
            show_logs "$@"
            ;;
        metrics)
            show_metrics
            ;;
        diagnostics)
            run_diagnostics
            ;;
        backup)
            backup_stack
            ;;
        restore)
            if [[ $# -eq 0 ]]; then
                log_error "Backup directory required"
                echo "Usage: $0 restore <backup_directory>"
                exit 1
            fi
            restore_stack "$1"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            log_error "Unknown command: ${command}"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
