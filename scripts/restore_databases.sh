#!/bin/bash
# ============================================================================
# MAHOUN Platform - Database Restore Script
# ============================================================================
# Restores databases from backup
# Usage: ./scripts/restore_databases.sh <backup_timestamp>
# ============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Validate input
if [ -z "$TIMESTAMP" ]; then
    log_error "Usage: $0 <backup_timestamp>"
fi

if [ ! -f "$BACKUP_DIR/manifest-${TIMESTAMP}.json" ]; then
    log_error "Backup manifest not found: $BACKUP_DIR/manifest-${TIMESTAMP}.json"
fi

log_info "Starting restore from backup: $TIMESTAMP"

# Confirmation
read -p "⚠️  This will OVERWRITE current data. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    log_error "Restore cancelled"
fi

# ============================================================================
# 1. Stop all services
# ============================================================================
log_info "Stopping services..."
docker compose down
log_success "Services stopped"

# ============================================================================
# 2. Restore Neo4j
# ============================================================================
if [ -f "$BACKUP_DIR/neo4j/neo4j-${TIMESTAMP}.dump.gz" ]; then
    log_info "Restoring Neo4j..."
    
    gunzip -c "$BACKUP_DIR/neo4j/neo4j-${TIMESTAMP}.dump.gz" > /tmp/neo4j-restore.dump
    
    docker compose up -d neo4j
    sleep 10
    
    docker cp /tmp/neo4j-restore.dump mahoun-neo4j:/tmp/
    docker exec mahoun-neo4j neo4j-admin database load neo4j \
        --from-path=/tmp/neo4j-restore.dump --overwrite-destination=true
    
    rm /tmp/neo4j-restore.dump
    log_success "Neo4j restored"
fi

# ============================================================================
# 3. Restore PostgreSQL
# ============================================================================
if [ -f "$BACKUP_DIR/postgres/postgres-${TIMESTAMP}.sql.gz" ]; then
    log_info "Restoring PostgreSQL..."
    
    docker compose up -d postgres
    sleep 10
    
    gunzip -c "$BACKUP_DIR/postgres/postgres-${TIMESTAMP}.sql.gz" | \
        docker exec -i mahoun-postgres psql -U mahoun mahoun
    
    log_success "PostgreSQL restored"
fi

# ============================================================================
# 4. Restore Redis
# ============================================================================
if [ -f "$BACKUP_DIR/redis/redis-${TIMESTAMP}.rdb.gz" ]; then
    log_info "Restoring Redis..."
    
    gunzip -c "$BACKUP_DIR/redis/redis-${TIMESTAMP}.rdb.gz" > /tmp/dump.rdb
    
    docker compose up -d redis
    sleep 5
    docker compose stop redis
    
    docker cp /tmp/dump.rdb mahoun-redis:/data/dump.rdb
    docker compose start redis
    
    rm /tmp/dump.rdb
    log_success "Redis restored"
fi

# ============================================================================
# 5. Restore ChromaDB
# ============================================================================
if [ -f "$BACKUP_DIR/chromadb/chroma-${TIMESTAMP}.tar.gz" ]; then
    log_info "Restoring ChromaDB..."
    
    docker compose up -d chromadb
    sleep 5
    
    docker cp "$BACKUP_DIR/chromadb/chroma-${TIMESTAMP}.tar.gz" \
        mahoun-chromadb:/tmp/
    
    docker exec mahoun-chromadb sh -c \
        "rm -rf /chroma/chroma/* && tar xzf /tmp/chroma-${TIMESTAMP}.tar.gz -C /"
    
    docker compose restart chromadb
    log_success "ChromaDB restored"
fi

# ============================================================================
# 6. Restore Application Data
# ============================================================================
if [ -f "$BACKUP_DIR/app-data-${TIMESTAMP}.tar.gz" ]; then
    log_info "Restoring application data..."
    tar xzf "$BACKUP_DIR/app-data-${TIMESTAMP}.tar.gz"
    log_success "Application data restored"
fi

# ============================================================================
# 7. Start all services
# ============================================================================
log_info "Starting all services..."
docker compose up -d
sleep 30

# ============================================================================
# 8. Health check
# ============================================================================
log_info "Running health checks..."
if curl -f http://localhost:8000/system/health > /dev/null 2>&1; then
    log_success "Backend is healthy"
else
    log_error "Backend health check failed"
fi

log_success "Restore completed successfully!"
log_info "Restored from backup: $TIMESTAMP"
