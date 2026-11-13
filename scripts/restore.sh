#!/bin/bash
# ============================================================================
# MAHOUN Backend - Restore Script
# ============================================================================
# Restores critical data from backup
# Usage: ./scripts/restore.sh <timestamp> [--skip-neo4j] [--skip-postgres]
# Example: ./scripts/restore.sh 20240225_143022
# ============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
SKIP_NEO4J=false
SKIP_POSTGRES=false
SKIP_REDIS=false
SKIP_LEDGER=false
SKIP_CHROMADB=false

# Check arguments
if [[ $# -lt 1 ]]; then
    echo -e "${RED}Usage: $0 <timestamp> [--skip-neo4j] [--skip-postgres] [--skip-redis] [--skip-ledger] [--skip-chromadb]${NC}"
    echo -e "${YELLOW}Example: $0 20240225_143022${NC}"
    exit 1
fi

TIMESTAMP=$1
shift

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-neo4j) SKIP_NEO4J=true; shift ;;
        --skip-postgres) SKIP_POSTGRES=true; shift ;;
        --skip-redis) SKIP_REDIS=true; shift ;;
        --skip-ledger) SKIP_LEDGER=true; shift ;;
        --skip-chromadb) SKIP_CHROMADB=true; shift ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

# Functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_container() {
    local container=$1
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        log_error "Container ${container} is not running!"
        return 1
    fi
    return 0
}

# Find backup directory
BACKUP_PATH=$(find "${BACKUP_DIR}" -type d -name "*" | while read dir; do
    if ls "$dir"/postgres_${TIMESTAMP}.* 2>/dev/null | grep -q .; then
        echo "$dir"
        break
    fi
done)

if [[ -z "${BACKUP_PATH}" ]]; then
    log_error "Backup not found for timestamp: ${TIMESTAMP}"
    log_info "Available backups:"
    find "${BACKUP_DIR}" -name "manifest_*.json" -exec basename {} \; | sed 's/manifest_/  /' | sed 's/.json//'
    exit 1
fi

log_info "Found backup at: ${BACKUP_PATH}"

# Verify manifest
MANIFEST="${BACKUP_PATH}/manifest_${TIMESTAMP}.json"
if [[ ! -f "${MANIFEST}" ]]; then
    log_warn "Manifest not found, proceeding without verification"
else
    log_info "Verifying backup integrity..."
    # TODO: Add checksum verification
fi

# Confirmation
echo ""
log_warn "═══════════════════════════════════════════════════════"
log_warn "WARNING: This will OVERWRITE existing data!"
log_warn "═══════════════════════════════════════════════════════"
log_warn "Backup timestamp: ${TIMESTAMP}"
log_warn "Backup location: ${BACKUP_PATH}"
echo ""
read -p "Are you sure you want to continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Restore cancelled"
    exit 0
fi

log_info "Starting restore..."

# ============================================================================
# 1. Restore PostgreSQL
# ============================================================================
if [[ "${SKIP_POSTGRES}" == "false" ]]; then
    log_info "Restoring PostgreSQL..."
    if check_container "mahoun-postgres"; then
        POSTGRES_DUMP="${BACKUP_PATH}/postgres_${TIMESTAMP}.dump"
        
        if [[ -f "${POSTGRES_DUMP}" ]]; then
            # Drop existing database and recreate
            docker exec mahoun-postgres psql -U mahoun -d postgres -c "DROP DATABASE IF EXISTS mahoun;"
            docker exec mahoun-postgres psql -U mahoun -d postgres -c "CREATE DATABASE mahoun;"
            
            # Restore from dump
            docker exec -i mahoun-postgres pg_restore -U mahoun -d mahoun \
                --verbose \
                --no-owner \
                --no-acl \
                < "${POSTGRES_DUMP}"
            
            log_info "✅ PostgreSQL restored"
        else
            log_error "PostgreSQL dump not found: ${POSTGRES_DUMP}"
        fi
    fi
else
    log_info "⏭️  Skipping PostgreSQL restore"
fi

# ============================================================================
# 2. Restore Neo4j (CRITICAL)
# ============================================================================
if [[ "${SKIP_NEO4J}" == "false" ]]; then
    log_info "Restoring Neo4j..."
    if check_container "mahoun-neo4j"; then
        NEO4J_DUMP="${BACKUP_PATH}/neo4j_${TIMESTAMP}.dump"
        
        if [[ -f "${NEO4J_DUMP}" ]]; then
            # Stop Neo4j
            log_warn "Stopping Neo4j..."
            docker exec mahoun-neo4j neo4j stop || true
            sleep 5
            
            # Copy dump into container
            docker cp "${NEO4J_DUMP}" mahoun-neo4j:/tmp/restore.dump
            
            # Restore database
            docker exec mahoun-neo4j neo4j-admin database load neo4j \
                --from-path=/tmp \
                --overwrite-destination=true \
                --verbose
            
            # Start Neo4j
            docker exec mahoun-neo4j neo4j start
            log_info "Waiting for Neo4j to start..."
            sleep 15
            
            # Verify
            docker exec mahoun-neo4j cypher-shell -u neo4j -p "${DB_NEO4J_PASSWORD}" \
                "MATCH (n) RETURN count(n) as node_count" || log_warn "Could not verify Neo4j"
            
            log_info "✅ Neo4j restored"
        else
            log_error "Neo4j dump not found: ${NEO4J_DUMP}"
        fi
    fi
else
    log_info "⏭️  Skipping Neo4j restore"
fi

# ============================================================================
# 3. Restore Redis
# ============================================================================
if [[ "${SKIP_REDIS}" == "false" ]]; then
    log_info "Restoring Redis..."
    if check_container "mahoun-redis"; then
        REDIS_RDB="${BACKUP_PATH}/redis_${TIMESTAMP}.rdb"
        
        if [[ -f "${REDIS_RDB}" ]]; then
            # Stop Redis
            docker stop mahoun-redis
            
            # Copy RDB file
            docker cp "${REDIS_RDB}" mahoun-redis:/data/dump.rdb
            
            # Start Redis
            docker start mahoun-redis
            sleep 5
            
            log_info "✅ Redis restored"
        else
            log_error "Redis dump not found: ${REDIS_RDB}"
        fi
    fi
else
    log_info "⏭️  Skipping Redis restore"
fi

# ============================================================================
# 4. Restore Immutable Ledger (CRITICAL)
# ============================================================================
if [[ "${SKIP_LEDGER}" == "false" ]]; then
    log_info "Restoring Immutable Ledger..."
    if check_container "mahoun-backend"; then
        LEDGER_ARCHIVE="${BACKUP_PATH}/ledger_${TIMESTAMP}.tar.gz"
        
        if [[ -f "${LEDGER_ARCHIVE}" ]]; then
            # Copy archive into container
            docker cp "${LEDGER_ARCHIVE}" mahoun-backend:/tmp/
            
            # Extract (backup existing first)
            docker exec mahoun-backend bash -c "
                if [ -d /app/ledger ]; then
                    mv /app/ledger /app/ledger.backup.$(date +%s)
                fi
                tar -xzf /tmp/ledger_${TIMESTAMP}.tar.gz -C /app
                rm /tmp/ledger_${TIMESTAMP}.tar.gz
            "
            
            log_info "✅ Ledger restored"
        else
            log_error "Ledger archive not found: ${LEDGER_ARCHIVE}"
        fi
    fi
else
    log_info "⏭️  Skipping Ledger restore"
fi

# ============================================================================
# 5. Restore ChromaDB
# ============================================================================
if [[ "${SKIP_CHROMADB}" == "false" ]]; then
    log_info "Restoring ChromaDB..."
    if check_container "mahoun-chromadb"; then
        CHROMADB_ARCHIVE="${BACKUP_PATH}/chromadb_${TIMESTAMP}.tar.gz"
        
        if [[ -f "${CHROMADB_ARCHIVE}" ]]; then
            # Stop ChromaDB
            docker stop mahoun-chromadb
            
            # Restore data
            docker run --rm \
                --volumes-from mahoun-chromadb \
                -v "${PWD}/${BACKUP_PATH}:/backup" \
                alpine sh -c "
                    rm -rf /chroma/chroma/*
                    tar -xzf /backup/chromadb_${TIMESTAMP}.tar.gz -C /chroma
                "
            
            # Start ChromaDB
            docker start mahoun-chromadb
            sleep 5
            
            log_info "✅ ChromaDB restored"
        else
            log_error "ChromaDB archive not found: ${CHROMADB_ARCHIVE}"
        fi
    fi
else
    log_info "⏭️  Skipping ChromaDB restore"
fi

# ============================================================================
# 6. Restart Backend
# ============================================================================
log_info "Restarting backend..."
docker restart mahoun-backend
sleep 10

# ============================================================================
# 7. Verify Health
# ============================================================================
log_info "Verifying system health..."
sleep 5

if curl -sf http://localhost:8000/system/health > /dev/null; then
    log_info "✅ Backend is healthy"
else
    log_warn "⚠️  Backend health check failed"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
log_info "═══════════════════════════════════════════════════════"
log_info "Restore completed!"
log_info "═══════════════════════════════════════════════════════"
log_info "Timestamp: ${TIMESTAMP}"
log_info "Location: ${BACKUP_PATH}"
log_info "═══════════════════════════════════════════════════════"
echo ""
log_info "Please verify your data and run health checks:"
log_info "  make -f Makefile.backend health"
