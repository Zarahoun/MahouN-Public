#!/bin/bash
# ============================================================================
# MAHOUN Platform - Vault Setup Script
# ============================================================================
# Initializes Vault and stores secrets securely
# ============================================================================

set -e

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
VAULT_TOKEN="${VAULT_ROOT_TOKEN:-dev-only-token}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Wait for Vault to be ready
log_info "Waiting for Vault to be ready..."
until curl -s "$VAULT_ADDR/v1/sys/health" > /dev/null; do
    sleep 2
done
log_success "Vault is ready"

# Login to Vault
export VAULT_ADDR
export VAULT_TOKEN

# Enable KV secrets engine
log_info "Enabling KV secrets engine..."
vault secrets enable -path=secret kv-v2 2>/dev/null || log_info "KV engine already enabled"

# Generate strong secrets
log_info "Generating strong secrets..."
DB_POSTGRES_PASSWORD=$(openssl rand -base64 32)
DB_NEO4J_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -hex 32)
API_KEY=$(openssl rand -base64 32)

# Store secrets in Vault
log_info "Storing secrets in Vault..."

vault kv put secret/mahoun/database/postgres \
    password="$DB_POSTGRES_PASSWORD" \
    host="postgres" \
    port="5432" \
    database="mahoun" \
    user="mahoun"

vault kv put secret/mahoun/database/neo4j \
    password="$DB_NEO4J_PASSWORD" \
    uri="bolt://neo4j:7687" \
    user="neo4j"

vault kv put secret/mahoun/database/redis \
    password="$REDIS_PASSWORD" \
    url="redis://redis:6379/0"

vault kv put secret/mahoun/security \
    jwt_secret="$JWT_SECRET" \
    api_key="$API_KEY"

log_success "Secrets stored in Vault"

# Create policy for backend service
log_info "Creating Vault policy..."
vault policy write mahoun-backend - <<EOF
path "secret/data/mahoun/*" {
  capabilities = ["read"]
}
EOF

log_success "Vault policy created"

# Enable AppRole auth
log_info "Enabling AppRole authentication..."
vault auth enable approle 2>/dev/null || log_info "AppRole already enabled"

# Create AppRole for backend
vault write auth/approle/role/mahoun-backend \
    token_policies="mahoun-backend" \
    token_ttl=1h \
    token_max_ttl=4h

# Get RoleID and SecretID
ROLE_ID=$(vault read -field=role_id auth/approle/role/mahoun-backend/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/mahoun-backend/secret-id)

log_success "AppRole configured"

# Save credentials to secure file
cat > .vault-credentials <<EOF
# MAHOUN Vault Credentials
# Keep this file secure and never commit to git!

VAULT_ADDR=$VAULT_ADDR
VAULT_ROLE_ID=$ROLE_ID
VAULT_SECRET_ID=$SECRET_ID

# For development only:
VAULT_TOKEN=$VAULT_TOKEN
EOF

chmod 600 .vault-credentials

log_success "Vault setup complete!"
echo ""
echo "Credentials saved to .vault-credentials"
echo "Add to .env:"
echo "  VAULT_ADDR=$VAULT_ADDR"
echo "  VAULT_ROLE_ID=$ROLE_ID"
echo "  VAULT_SECRET_ID=$SECRET_ID"
