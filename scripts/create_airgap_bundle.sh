#!/bin/bash
#
# MAHOUN Air-Gapped Deployment Bundle Creator
# ============================================
#
# Creates a complete offline installation package for air-gapped environments.
# No internet connection required after bundle creation.
#
# Usage:
#   ./scripts/create_airgap_bundle.sh [output_dir]
#
# Output:
#   mahoun-airgap-bundle-{version}-{date}.tar.gz
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION=$(grep -oP 'version="\K[^"]+' "$PROJECT_ROOT/pyproject.toml" || echo "1.0.0")
DATE=$(date +%Y%m%d)
OUTPUT_DIR="${1:-$PROJECT_ROOT/dist}"
BUNDLE_NAME="mahoun-airgap-bundle-${VERSION}-${DATE}"
BUNDLE_DIR="$OUTPUT_DIR/$BUNDLE_NAME"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  MAHOUN Air-Gapped Deployment Bundle Creator              ║${NC}"
echo -e "${BLUE}║  Version: $VERSION                                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Create bundle directory structure
echo -e "${YELLOW}[1/8]${NC} Creating bundle directory structure..."
mkdir -p "$BUNDLE_DIR"/{python-packages,docker-images,docs,scripts,config,checksums}

# Step 2: Download Python dependencies
echo -e "${YELLOW}[2/8]${NC} Downloading Python dependencies (offline wheels)..."
cd "$PROJECT_ROOT"
pip download -r requirements.txt -d "$BUNDLE_DIR/python-packages" --no-cache-dir
pip download -r requirements.txt -d "$BUNDLE_DIR/python-packages" --platform manylinux2014_x86_64 --only-binary=:all: --no-cache-dir || true

echo -e "${GREEN}✓${NC} Downloaded $(ls -1 "$BUNDLE_DIR/python-packages" | wc -l) Python packages"

# Step 3: Export Docker images
echo -e "${YELLOW}[3/8]${NC} Exporting Docker images..."
if command -v docker &> /dev/null; then
    # Build images first
    docker-compose -f docker-compose.prod.yml build --no-cache || echo "Warning: Docker build failed"
    
    # Export images
    docker save mahoun-app:latest -o "$BUNDLE_DIR/docker-images/mahoun-app.tar" || echo "Warning: mahoun-app export failed"
    docker save neo4j:5.15 -o "$BUNDLE_DIR/docker-images/neo4j.tar" || echo "Warning: neo4j export failed"
    docker save prom/prometheus:latest -o "$BUNDLE_DIR/docker-images/prometheus.tar" || echo "Warning: prometheus export failed"
    docker save grafana/grafana:latest -o "$BUNDLE_DIR/docker-images/grafana.tar" || echo "Warning: grafana export failed"
    
    echo -e "${GREEN}✓${NC} Exported Docker images"
else
    echo -e "${RED}✗${NC} Docker not found, skipping image export"
fi

# Step 4: Bundle documentation
echo -e "${YELLOW}[4/8]${NC} Bundling documentation..."
cp -r "$PROJECT_ROOT/docs" "$BUNDLE_DIR/docs/"
cp "$PROJECT_ROOT/README.md" "$BUNDLE_DIR/"
cp "$PROJECT_ROOT/LICENSE" "$BUNDLE_DIR/" 2>/dev/null || echo "No LICENSE file"

# Create offline HTML documentation
if command -v pandoc &> /dev/null; then
    pandoc "$PROJECT_ROOT/README.md" -o "$BUNDLE_DIR/docs/README.html" --standalone --self-contained || true
fi

echo -e "${GREEN}✓${NC} Documentation bundled"

# Step 5: Copy configuration templates
echo -e "${YELLOW}[5/8]${NC} Copying configuration templates..."
cp "$PROJECT_ROOT/.env.example" "$BUNDLE_DIR/config/env.template"
cp "$PROJECT_ROOT/docker-compose.prod.yml" "$BUNDLE_DIR/config/"
cp -r "$PROJECT_ROOT/config" "$BUNDLE_DIR/config/runtime" 2>/dev/null || true

echo -e "${GREEN}✓${NC} Configuration templates copied"

# Step 6: Copy installation scripts
echo -e "${YELLOW}[6/8]${NC} Copying installation scripts..."
cp "$SCRIPT_DIR"/*.sh "$BUNDLE_DIR/scripts/" 2>/dev/null || true
chmod +x "$BUNDLE_DIR/scripts"/*.sh 2>/dev/null || true

echo -e "${GREEN}✓${NC} Installation scripts copied"

# Step 7: Generate checksums
echo -e "${YELLOW}[7/8]${NC} Generating checksums..."
cd "$BUNDLE_DIR"
find . -type f -exec sha256sum {} \; > checksums/SHA256SUMS
echo -e "${GREEN}✓${NC} Checksums generated"

# Step 8: Create installation guide
echo -e "${YELLOW}[8/8]${NC} Creating installation guide..."
cat > "$BUNDLE_DIR/INSTALL.md" << 'EOF'
# MAHOUN Air-Gapped Installation Guide

## Prerequisites

- Linux system (Ubuntu 20.04+ or RHEL 8+)
- Python 3.11+
- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 50GB disk space

## Installation Steps

### 1. Verify Bundle Integrity

```bash
cd mahoun-airgap-bundle-*
sha256sum -c checksums/SHA256SUMS
```

### 2. Install Python Dependencies

```bash
pip install --no-index --find-links=python-packages -r ../requirements.txt
```

### 3. Load Docker Images

```bash
docker load -i docker-images/mahoun-app.tar
docker load -i docker-images/neo4j.tar
docker load -i docker-images/prometheus.tar
docker load -i docker-images/grafana.tar
```

### 4. Configure Environment

```bash
cp config/env.template .env
# Edit .env with your configuration
nano .env
```

### 5. Start Services

```bash
docker-compose -f config/docker-compose.prod.yml up -d
```

### 6. Verify Installation

```bash
curl http://localhost:8000/api/v1/reasoning/health
```

## Troubleshooting

See `docs/TROUBLESHOOTING.md` for common issues.

## Support

For air-gapped environments, refer to offline documentation in `docs/` directory.
EOF

echo -e "${GREEN}✓${NC} Installation guide created"

# Create tarball
echo ""
echo -e "${YELLOW}Creating compressed bundle...${NC}"
cd "$OUTPUT_DIR"
tar -czf "${BUNDLE_NAME}.tar.gz" "$BUNDLE_NAME"
BUNDLE_SIZE=$(du -h "${BUNDLE_NAME}.tar.gz" | cut -f1)

# Cleanup
rm -rf "$BUNDLE_NAME"

# Final summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Bundle Created Successfully!                              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Bundle:${NC}     ${BUNDLE_NAME}.tar.gz"
echo -e "  ${BLUE}Location:${NC}   $OUTPUT_DIR"
echo -e "  ${BLUE}Size:${NC}       $BUNDLE_SIZE"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Transfer bundle to air-gapped system via USB/secure media"
echo -e "  2. Extract: tar -xzf ${BUNDLE_NAME}.tar.gz"
echo -e "  3. Follow INSTALL.md instructions"
echo ""
echo -e "${GREEN}✓ Ready for air-gapped deployment${NC}"
