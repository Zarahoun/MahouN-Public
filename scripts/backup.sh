#!/bin/bash
# ============================================================================
# MAHOUN Backend - Automated Backup Script
# ============================================================================
# Backs up critical data: Neo4j, PostgreSQL, Redis, Ledger
# Usage: ./scripts/backup.sh [--remote s3://bucket/path]
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE_DIR=$(date +%Y/%m/%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
REMOTE_BACKUP=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --remote)
            REMOTE_BACKUP="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_container() {
    local container=$1
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        log_error "Container ${container} is not running!"
        return 1
    fi
    return 0
}

# Create backup directory structure
mkdir -p "${BACKUP_DIR}/${DATE_DIR}"
BACKUP_PATH="${BACKUP_DIR}/${DATE_DIR}"

log_info "Starting backup at ${TIMESTAMP}"
log_info "Backup location: ${BACKUP_PATH}"

# ============================================================================
# 1. Backup PostgreSQL (Metadata & Audit Trail)
# ============================================================================
log_info "Backing up PostgreSQL..."
if check_container "mahoun-postgres"; then
    docker exec mahoun-postgres pg_dump -U mahoun mahoun \
        --format=custom \
        --compress=9 \
        --verbose \
        > "${BACKUP_PATH}/postgres_${TIMESTAMP}.dump"
    
    # Also create SQL format for easy inspection
    docker exec mahoun-postgres pg_dump -U mahoun mahoun \
        > "${BACKUP_PATH}/postgres_${TIMESTAMP}.sql"
    
    log_info "✅ PostgreSQL backup complete"
else
    log_error "PostgreSQL backup failed - container not running"
fi

# ============================================================================
# 2. Backup Neo4j (Knowledge Graph - CRITICAL)
# ============================================================================
log_info "Backing up Neo4j..."
if check_container "mahoun-neo4j"; then
    # Stop Neo4j for consistent backup
    log_warn "Stopping Neo4j for consistent backup..."
    docker exec mahoun-neo4j neo4j stop || true
    sleep 5
    
    # Create backup
    docker exec mahoun-neo4j neo4j-admin database dump neo4j \
        --to-path=/tmp \
        --verbose
    
    # Copy backup out of container
    docker cp mahoun-neo4j:/tmp/neo4j.dump \
        "${BACKUP_PATH}/neo4j_${TIMESTAMP}.dump"
    
    # Restart Neo4j
    docker exec mahoun-neo4j neo4j start
    log_info "Waiting for Neo4j to start..."
    sleep 10
    
    log_info "✅ Neo4j backup complete"
else
    log_error "Neo4j backup failed - container not running"
fi

# ============================================================================
# 3. Backup Redis (Cache & Session State)
# ============================================================================
log_info "Backing up Redis..."
if check_container "mahoun-redis"; then
    # Trigger Redis save
    docker exec mahoun-redis redis-cli --no-auth-warning \
        -a "${REDIS_PASSWORD:-}" BGSAVE
    
    # Wait for save to complete
    sleep 5
    
    # Copy RDB file
    docker cp mahoun-redis:/data/dump.rdb \
        "${BACKUP_PATH}/redis_${TIMESTAMP}.rdb"
    
    log_info "✅ Redis backup complete"
else
    log_error "Redis backup failed - container not running"
fi

# ============================================================================
# 4. Backup Immutable Ledger (CRITICAL)
# ============================================================================
log_info "Backing up Immutable Ledger..."
if check_container "mahoun-backend"; then
    # Create tarball of ledger directory
    docker exec mahoun-backend tar -czf /tmp/ledger_${TIMESTAMP}.tar.gz \
        -C /app ledger
    
    # Copy out of container
    docker cp mahoun-backend:/tmp/ledger_${TIMESTAMP}.tar.gz \
        "${BACKUP_PATH}/"
    
    # Cleanup temp file
    docker exec mahoun-backend rm /tmp/ledger_${TIMESTAMP}.tar.gz
    
    log_info "✅ Ledger backup complete"
else
    log_error "Ledger backup failed - container not running"
fi

# ============================================================================
# 5. Backup ChromaDB (Vector Store)
# ============================================================================
log_info "Backing up ChromaDB..."
if check_container "mahoun-chromadb"; then
    # Copy ChromaDB data directory
    docker run --rm \
        --volumes-from mahoun-chromadb \
        -v "${PWD}/${BACKUP_PATH}:/backup" \
        alpine tar -czf "/backup/chromadb_${TIMESTAMP}.tar.gz" \
        -C /chroma chroma
    
    log_info "✅ ChromaDB backup complete"
else
    log_error "ChromaDB backup failed - container not running"
fi

# ============================================================================
# 6. Create Backup Manifest
# ============================================================================
log_info "Creating backup manifest..."
cat > "${BACKUP_PATH}/manifest_${TIMESTAMP}.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "date": "$(date -Iseconds)",
  "version": "$(docker exec mahoun-backend python --version 2>&1 || echo 'unknown')",
  "files": {
    "postgres_dump": "postgres_${TIMESTAMP}.dump",
    "postgres_sql": "postgres_${TIMESTAMP}.sql",
    "neo4j_dump": "neo4j_${TIMESTAMP}.dump",
    "redis_rdb": "redis_${TIMESTAMP}.rdb",
    "ledger_archive": "ledger_${TIMESTAMP}.tar.gz",
    "chromadb_archive": "chromadb_${TIMESTAMP}.tar.gz"
  },
  "checksums": {
    "postgres_dump": "$(sha256sum "${BACKUP_PATH}/postgres_${TIMESTAMP}.dump" | awk '{print $1}')",
    "neo4j_dump": "$(sha256sum "${BACKUP_PATH}/neo4j_${TIMESTAMP}.dump" | awk '{print $1}')",
    "redis_rdb": "$(sha256sum "${BACKUP_PATH}/redis_${TIMESTAMP}.rdb" | awk '{print $1}')",
    "ledger_archive": "$(sha256sum "${BACKUP_PATH}/ledger_${TIMESTAMP}.tar.gz" | awk '{print $1}')",
    "chromadb_archive": "$(sha256sum "${BACKUP_PATH}/chromadb_${TIMESTAMP}.tar.gz" | awk '{print $1}')"
  }
}
EOF

log_info "✅ Manifest created"

# ============================================================================
# 7. Calculate Backup Size
# ============================================================================
BACKUP_SIZE=$(du -sh "${BACKUP_PATH}" | awk '{print $1}')
log_info "Backup size: ${BACKUP_SIZE}"

# ============================================================================
# 8. Upload to Remote Storage (Optional)
# ============================================================================
if [[ -n "${REMOTE_BACKUP}" ]]; then
    log_info "Uploading to remote storage: ${REMOTE_BACKUP}"
    
    if command -v aws &> /dev/null; then
        aws s3 sync "${BACKUP_PATH}" "${REMOTE_BACKUP}/${DATE_DIR}/" \
            --storage-class STANDARD_IA \
            --only-show-errors
        log_info "✅ Remote backup complete"
    else
        log_warn "AWS CLI not found, skipping remote backup"
    fi
fi

# ============================================================================
# 9. Cleanup Old Backups
# ============================================================================
log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -type d -empty -delete
log_info "✅ Cleanup complete"

# ============================================================================
# Summary
# ============================================================================
echo ""
log_info "═══════════════════════════════════════════════════════"
log_info "Backup completed successfully!"
log_info "═══════════════════════════════════════════════════════"
log_info "Location: ${BACKUP_PATH}"
log_info "Size: ${BACKUP_SIZE}"
log_info "Timestamp: ${TIMESTAMP}"
log_info "═══════════════════════════════════════════════════════"
echo ""
log_info "To restore, use: ./scripts/restore.sh ${TIMESTAMP}"
