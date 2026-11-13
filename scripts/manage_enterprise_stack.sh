#!/bin/bash
# ============================================================================
# MAHOUN Enterprise Stack Management Script
# ============================================================================
# Purpose: Advanced operations for enterprise database stack
# Usage: ./scripts/manage_enterprise_stack.sh [command] [options]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
BACKUP_DIR="./backups"
LOG_DIR="./logs"

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check environment file
    if [[ ! -f "$ENV_FILE" ]]; then
        warn "Environment file not found. Creating from template..."
        cp .env.enterprise .env
        info "Please customize .env file with your credentials"
    fi
    
    log "✅ Prerequisites check passed"
}

create_directories() {
    log "Creating directory structure..."
    
    local dirs=(
        "data/neo4j/{data,logs,import,plugins,backups}"
        "data/postgres/{data,archive,backups}"  
        "data/redis/{data,logs}"
        "data/chromadb/{data,segments,backups}"
        "logs/{api,neo4j,postgres,redis,chromadb}"
        "backups/{neo4j,postgres,redis,chromadb}"
        "config/{neo4j,postgres,redis,chromadb}"
    )
    
    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done
    
    # Set appropriate permissions
    chmod 700 data/postgres backups/postgres
    chmod 755 data/neo4j data/redis data/chromadb
    
    log "✅ Directory structure created"
}

# ============================================================================
# STACK MANAGEMENT
# ============================================================================

start_stack() {
    local profile=${1:-""}
    
    log "Starting MAHOUN Enterprise Stack..."
    
    if [[ -n "$profile" ]]; then
        info "Using profile: $profile"
        docker-compose --profile "$profile" up -d
    else
        docker-compose up -d
    fi
    
    log "✅ Stack started successfully"
    show_status
}

stop_stack() {
    log "Stopping MAHOUN Enterprise Stack..."
    docker-compose down
    log "✅ Stack stopped successfully"
}

restart_stack() {
    log "Restarting MAHOUN Enterprise Stack..."
    stop_stack
    sleep 5
    start_stack
}

show_status() {
    log "Stack Status:"
    echo
    docker-compose ps
    echo
    
    # Health check summary
    info "Health Check Summary:"
    local services=("governance-kernel" "api-server" "redis" "neo4j" "postgres" "chromadb")
    
    for service in "${services[@]}"; do
        if docker-compose ps -q "$service" > /dev/null 2>&1; then
            local health=$(docker inspect --format='{{.State.Health.Status}}' "mahoun-${service}-enterprise" 2>/dev/null || echo "no-health-check")
            case $health in
                "healthy") echo -e "  ${GREEN}●${NC} $service: healthy" ;;
                "unhealthy") echo -e "  ${RED}●${NC} $service: unhealthy" ;;
                "starting") echo -e "  ${YELLOW}●${NC} $service: starting" ;;
                *) echo -e "  ${BLUE}●${NC} $service: running" ;;
            esac
        else
            echo -e "  ${RED}●${NC} $service: stopped"
        fi
    done
}

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

backup_databases() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    
    log "Starting enterprise backup process..."
    
    # Neo4j Backup
    backup_neo4j "$timestamp"
    
    # PostgreSQL Backup  
    backup_postgres "$timestamp"
    
    # Redis Backup
    backup_redis "$timestamp"
    
    # ChromaDB Backup
    backup_chromadb "$timestamp"
    
    log "✅ All database backups completed"
}

backup_neo4j() {
    local timestamp=$1
    local backup_file="$BACKUP_DIR/neo4j/neo4j_backup_$timestamp.tar.gz"
    
    info "Backing up Neo4j..."
    
    # Create backup using neo4j-admin
    docker-compose exec neo4j neo4j-admin database dump --database=neo4j --to-path=/backups neo4j
    
    # Compress backup
    mkdir -p "$(dirname "$backup_file")"
    docker run --rm \
        -v "mahoun_neo4j_backups_$(cat .env | grep MAHOUN_ENV | cut -d= -f2):/source" \
        -v "$BACKUP_DIR/neo4j:/dest" \
        alpine:latest \
        tar -czf "/dest/neo4j_backup_$timestamp.tar.gz" -C /source .
    
    info "✅ Neo4j backup: $backup_file"
}

backup_postgres() {
    local timestamp=$1
    local backup_file="$BACKUP_DIR/postgres/postgres_backup_$timestamp.sql.gz"
    
    info "Backing up PostgreSQL..."
    
    mkdir -p "$(dirname "$backup_file")"
    
    # Create compressed backup
    docker-compose exec postgres pg_dumpall -U mahoun_admin | gzip > "$backup_file"
    
    info "✅ PostgreSQL backup: $backup_file"
}

backup_redis() {
    local timestamp=$1
    local backup_file="$BACKUP_DIR/redis/redis_backup_$timestamp.rdb"
    
    info "Backing up Redis..."
    
    mkdir -p "$(dirname "$backup_file")"
    
    # Trigger Redis save and copy RDB file
    docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" BGSAVE
    sleep 5  # Wait for background save
    docker cp "mahoun-redis-enterprise:/data/dump.rdb" "$backup_file"
    
    info "✅ Redis backup: $backup_file"
}

backup_chromadb() {
    local timestamp=$1
    local backup_file="$BACKUP_DIR/chromadb/chromadb_backup_$timestamp.tar.gz"
    
    info "Backing up ChromaDB..."
    
    mkdir -p "$(dirname "$backup_file")"
    
    # Compress ChromaDB data directory
    docker run --rm \
        -v "mahoun_chromadb_data_$(cat .env | grep MAHOUN_ENV | cut -d= -f2):/source" \
        -v "$BACKUP_DIR/chromadb:/dest" \
        alpine:latest \
        tar -czf "/dest/chromadb_backup_$timestamp.tar.gz" -C /source .
    
    info "✅ ChromaDB backup: $backup_file"
}

# ============================================================================
# MONITORING & DIAGNOSTICS  
# ============================================================================

show_logs() {
    local service=${1:-""}
    local lines=${2:-100}
    
    if [[ -n "$service" ]]; then
        log "Showing logs for $service (last $lines lines)..."
        docker-compose logs --tail="$lines" -f "$service"
    else
        log "Showing logs for all services (last $lines lines)..."
        docker-compose logs --tail="$lines" -f
    fi
}

show_metrics() {
    log "Enterprise Stack Metrics:"
    echo
    
    # Container resource usage
    info "Container Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
    echo
    
    # Database-specific metrics
    show_database_metrics
}

show_database_metrics() {
    info "Database Metrics:"
    
    # Neo4j metrics
    if docker-compose ps -q neo4j > /dev/null 2>&1; then
        echo "📊 Neo4j:"
        docker-compose exec neo4j cypher-shell -u neo4j -p "$DB_NEO4J_PASSWORD" \
            "CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store file sizes') YIELD attributes RETURN attributes.TotalStoreSize as storeSize;" \
            2>/dev/null | grep -E "storeSize|bytes" | head -1 || echo "  Status: Running"
    fi
    
    # PostgreSQL metrics  
    if docker-compose ps -q postgres > /dev/null 2>&1; then
        echo "📊 PostgreSQL:"
        local db_size=$(docker-compose exec postgres psql -U mahoun_admin -d mahoun_enterprise -t -c \
            "SELECT pg_size_pretty(pg_database_size('mahoun_enterprise'));" 2>/dev/null | xargs || echo "Unknown")
        echo "  Database Size: $db_size"
    fi
    
    # Redis metrics
    if docker-compose ps -q redis > /dev/null 2>&1; then
        echo "📊 Redis:"
        local redis_info=$(docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" info memory 2>/dev/null | grep used_memory_human || echo "used_memory_human:Unknown")
        echo "  Memory Usage: $(echo "$redis_info" | cut -d: -f2)"
    fi
    
    # ChromaDB metrics
    if docker-compose ps -q chromadb > /dev/null 2>&1; then
        echo "📊 ChromaDB:"
        local collections=$(curl -s "http://localhost:8001/api/v1/collections" 2>/dev/null | jq length 2>/dev/null || echo "Unknown")
        echo "  Collections: $collections"
    fi
}

# ============================================================================
# MAINTENANCE OPERATIONS
# ============================================================================

cleanup_old_backups() {
    local retention_days=${1:-30}
    
    log "Cleaning up backups older than $retention_days days..."
    
    find "$BACKUP_DIR" -name "*.tar.gz" -o -name "*.sql.gz" -o -name "*.rdb" | \
        while read -r file; do
            if [[ $(find "$file" -mtime +$retention_days) ]]; then
                rm "$file"
                info "Deleted old backup: $file"
            fi
        done
    
    log "✅ Backup cleanup completed"
}

optimize_databases() {
    log "Optimizing databases..."
    
    # Neo4j optimization
    if docker-compose ps -q neo4j > /dev/null 2>&1; then
        info "Optimizing Neo4j..."
        docker-compose exec neo4j cypher-shell -u neo4j -p "$DB_NEO4J_PASSWORD" \
            "CALL db.indexes() YIELD name, type, state WHERE state <> 'ONLINE' RETURN name, state;" || true
    fi
    
    # PostgreSQL optimization
    if docker-compose ps -q postgres > /dev/null 2>&1; then
        info "Optimizing PostgreSQL..."
        docker-compose exec postgres psql -U mahoun_admin -d mahoun_enterprise -c "VACUUM ANALYZE;" || true
    fi
    
    log "✅ Database optimization completed"
}

# ============================================================================
# SECURITY OPERATIONS
# ============================================================================

security_scan() {
    log "Running security scan..."
    
    # Container vulnerability scan
    info "Scanning container images..."
    docker images --format "table {{.Repository}}:{{.Tag}}" | grep mahoun | while read -r image; do
        if command -v trivy &> /dev/null; then
            trivy image "$image" --severity HIGH,CRITICAL
        else
            warn "Trivy not installed - skipping vulnerability scan for $image"
        fi
    done
    
    # Configuration security check
    info "Checking configuration security..."
    check_security_config
    
    log "✅ Security scan completed"
}

check_security_config() {
    local issues=0
    
    # Check for default passwords
    if grep -q "change_me\|default\|password123" .env 2>/dev/null; then
        error "Default passwords detected in .env file"
        ((issues++))
    fi
    
    # Check file permissions
    if [[ $(stat -c %a .env 2>/dev/null) != "600" ]]; then
        warn "Insecure permissions on .env file (should be 600)"
        ((issues++))
    fi
    
    if [[ $issues -eq 0 ]]; then
        info "✅ Security configuration check passed"
    else
        warn "⚠️  Found $issues security issues"
    fi
}

# ============================================================================
# MAIN COMMAND INTERFACE
# ============================================================================

show_help() {
    cat << EOF
MAHOUN Enterprise Stack Management

USAGE:
    $0 <command> [options]

COMMANDS:
    start [profile]       Start the enterprise stack
                         Profiles: storage, production
    stop                 Stop the enterprise stack
    restart              Restart the enterprise stack
    status               Show stack status and health
    
    backup               Backup all databases
    restore <timestamp>  Restore from backup (timestamp format: YYYYMMDD_HHMMSS)
    
    logs [service] [lines]  Show logs (default: all services, 100 lines)
    metrics             Show performance metrics
    
    cleanup [days]      Clean up old backups (default: 30 days)
    optimize           Optimize database performance
    security-scan      Run security vulnerability scan
    
    setup              Initial setup (create directories, check prerequisites)
    
    help               Show this help message

EXAMPLES:
    $0 start storage          # Start with storage profile
    $0 backup                 # Backup all databases
    $0 logs neo4j 50         # Show Neo4j logs, last 50 lines
    $0 cleanup 7             # Remove backups older than 7 days
    $0 restore 20241215_143022  # Restore from specific backup

ENVIRONMENT:
    Copy .env.enterprise to .env and customize for your environment.
    
    Key variables:
    - MAHOUN_ENV: Environment (development/production)
    - DB_*_PASSWORD: Database passwords (CHANGE THESE!)
    - *_PORT: Service ports
    - *_MEMORY_LIMIT: Resource limits

EOF
}

main() {
    case "${1:-help}" in
        start)
            check_prerequisites
            create_directories
            start_stack "${2:-}"
            ;;
        stop)
            stop_stack
            ;;
        restart)
            restart_stack
            ;;
        status)
            show_status
            ;;
        backup)
            backup_databases
            ;;
        logs)
            show_logs "${2:-}" "${3:-100}"
            ;;
        metrics)
            show_metrics
            ;;
        cleanup)
            cleanup_old_backups "${2:-30}"
            ;;
        optimize)
            optimize_databases
            ;;
        security-scan)
            security_scan
            ;;
        setup)
            check_prerequisites
            create_directories
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "Unknown command: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"